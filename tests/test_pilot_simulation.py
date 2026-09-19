import asyncio
import json
from datetime import datetime, timedelta, timezone

from improv_troupe.application import (
    CommandBus,
    DurableWorkflowWorker,
    LiveSceneFactory,
    RecoveryTimerService,
    ResolveRecovery,
    SeasonDayCoordinator,
)
from improv_troupe.clock import VirtualClock
from improv_troupe.config import AppConfig, BackendConfig
from improv_troupe.domain import (
    CastMember,
    HiddenSeasonPlan,
    OpeningSnapshot,
    RoleSheet,
    Season,
    generate_schedule,
)
from improv_troupe.infrastructure import (
    DataRoots,
    RecordRepository,
    SQLiteDatabase,
    SeasonRepository,
    ScheduleRepository,
    WorkQueue,
)


class StructuredPilotClient:
    """Small deterministic client that honors the long-form output envelopes."""

    def __init__(self, *, fail_first_call=False, wellness_on_diary_call=None):
        self.calls = 0
        self.diary_calls = 0
        self.fail_first_call = fail_first_call
        self.wellness_on_diary_call = wellness_on_diary_call

    async def list_models(self):
        return ["actor-8b-test", "orchestrator-20b-test"]

    async def stream_chat(self, model, messages, **params):
        self.calls += 1
        if self.fail_first_call and self.calls == 1:
            yield "partial"
            raise TimeoutError("pilot model unavailable")
        instruction = "\n".join(message["content"] for message in messages)
        if "<NARRATION>" in instruction:
            output = (
                "<NARRATION>The impossible hotel shifts around us.</NARRATION>"
                "<NEXT_ACTOR>Mara</NEXT_ACTOR><COMPLETE>false</COMPLETE>"
            )
        elif "<DIARY_SLOT>" in instruction:
            self.diary_calls += 1
            signal = ""
            if self.diary_calls == self.wellness_on_diary_call:
                signal = "<WELLNESS_SIGNAL>The scene is too much for me right now.</WELLNESS_SIGNAL>"
            output = (
                "<DIARY_SLOT>1</DIARY_SLOT><WRITE_NOW>true</WRITE_NOW>"
                "<DIARY_TEXT>I record the next impossible clue in my own words.</DIARY_TEXT>"
                "<EVIDENCE_REFS>1</EVIDENCE_REFS>"
                f"{signal}"
            )
        else:
            output = "<ACTOR_TEXT>I follow the next impossible clue.</ACTOR_TEXT>"
        yield output


def _pilot_runtime(tmp_path, client, *, recovery_enabled=False):
    roots = DataRoots.from_root(tmp_path / "data")
    roots.prepare()
    database = SQLiteDatabase(roots.state / "improv.sqlite3")
    database.migrate()
    opening = OpeningSnapshot(
        set="The impossible hotel",
        setting="A science-fantasy hotel between train stations.",
        cast=["Mara", "Nox", "Iris", "Sol"],
        world_rules=["No actor-on-actor violence.", "No actor death."],
    )
    plan = HiddenSeasonPlan(
        premise="The hotel has invited four people to find a missing room.",
        hidden_mysteries=["The missing room is moving."],
    )
    cast_ids = {name: f"char-{index}" for index, name in enumerate(opening.cast, start=1)}
    cast = [CastMember(character_id=cast_ids[name], name=name) for name in opening.cast]
    plan = plan.model_copy(
        update={
            "role_sheets": [RoleSheet(character_id=member.character_id) for member in cast]
        }
    )
    SeasonRepository(database).create(
        Season(
            season_id="S01",
            season_number=1,
            status="RUNNING",
            opening=opening,
            private_plan=plan,
            cast=cast,
            model_manifest={
                "orchestrator": {"backend": "local", "model": "orchestrator-20b-test"},
                "actor_default": {"backend": "local", "model": "actor-8b-test"},
            },
        )
    )
    schedule = generate_schedule("S01", datetime(2026, 8, 1, 5, tzinfo=timezone.utc))
    records = RecordRepository(database)
    queue = WorkQueue(database)
    for slot in schedule:
        ScheduleRepository(database).add(slot)
        records.insert_run(
            run_id=slot.slot_id,
            season_id="S01",
            slot_id=slot.slot_id,
            status="QUEUED",
        )
        queue.enqueue(
            work_id=f"work:{slot.slot_id}",
            natural_key=f"run:{slot.slot_id}",
            kind="RUN_SCENE",
            payload={
                "season_id": "S01",
                "run_id": slot.slot_id,
                "day_number": slot.day_number,
                "slot_number": slot.slot_number,
            },
            available_at=slot.scheduled_utc.isoformat(),
            priority=slot.run_number,
        )
    clock = VirtualClock(datetime(2026, 8, 10, 12, tzinfo=timezone.utc))
    config = AppConfig(
        backends={
            "local": BackendConfig(
                base_url="http://127.0.0.1:11434/v1",
                kind="ollama",
            )
        }
    )
    factory = LiveSceneFactory(
        database=database,
        roots=roots,
        config=config,
        clock=clock,
        client_factory=lambda _: client,
    )
    coordinator = SeasonDayCoordinator(
        database=database,
        clock=clock,
        scene_factory=factory,
    )

    recovery = (
        RecoveryTimerService(database=database, clock=clock)
        if recovery_enabled
        else None
    )
    worker = DurableWorkflowWorker(
        database=database,
        clock=clock,
        scene_factory=factory,
        recovery=recovery,
        post_scene=coordinator.after_scene,
        close_day=coordinator.close_day,
    )
    return database, clock, worker, recovery


def test_accelerated_fake_worker_completes_all_21_scene_slots(tmp_path):
    client = StructuredPilotClient()
    database, _, worker, _ = _pilot_runtime(tmp_path, client)

    assert asyncio.run(worker.drain_due()) == 21
    assert len(worker.results) == 21
    assert all(result.status == "COMPLETED" for result in worker.results)
    assert database.connection.execute(
        "SELECT COUNT(*) FROM runs WHERE status = 'COMPLETED'"
    ).fetchone()[0] == 21
    assert database.connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0] == 21 * 20
    assert database.connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0] == (21 * 20) + (7 * 4) + 6
    assert database.connection.execute(
        "SELECT COUNT(*) FROM diaries WHERE status = 'WRITTEN'"
    ).fetchone()[0] == 7 * 4
    assert database.connection.execute("SELECT COUNT(*) FROM days WHERE closed = 1").fetchone()[0] == 7
    assert database.connection.execute(
        "SELECT COUNT(*) FROM domain_events WHERE event_type = 'NextDayDirectionCreated'"
    ).fetchone()[0] == 6
    assert client.calls == (21 * 20) + (7 * 4) + 6


def test_full_pilot_routes_diary_wellness_signal_to_private_audit(tmp_path):
    client = StructuredPilotClient(wellness_on_diary_call=1)
    database, _, worker, _ = _pilot_runtime(tmp_path, client)

    assert asyncio.run(worker.drain_due()) == 21
    assert database.connection.execute(
        "SELECT COUNT(*) FROM diaries WHERE status = 'PRIVATE'"
    ).fetchone()[0] == 1
    assert database.connection.execute(
        "SELECT COUNT(*) FROM diaries WHERE status = 'WRITTEN'"
    ).fetchone()[0] == (7 * 4) - 1
    wellness = database.connection.execute(
        "SELECT signal_number FROM wellness_events"
    ).fetchone()
    assert wellness["signal_number"] == 1
    cast = database.connection.execute(
        "SELECT status, distress_signal_count FROM cast_members WHERE character_id = 'char-1'"
    ).fetchone()
    assert cast["status"] == "ACTIVE"
    assert cast["distress_signal_count"] == 1
    audit_event = database.connection.execute(
        "SELECT payload_json FROM domain_events WHERE event_type = 'WellnessSignalObserved' "
        "AND aggregate_type = 'cast_member'"
    ).fetchone()
    audit_payload = json.loads(audit_event["payload_json"])
    assert "too much" in open(audit_payload["audit_path"], encoding="utf-8").read()
    event = database.connection.execute(
        "SELECT payload_json FROM domain_events WHERE event_type = 'WellnessSignalObserved' "
        "AND aggregate_type = 'diary'"
    ).fetchone()
    assert "too much" not in event["payload_json"]


def test_full_pilot_waits_for_model_then_creator_retry_completes_the_season(tmp_path):
    client = StructuredPilotClient(fail_first_call=True)
    database, clock, worker, recovery = _pilot_runtime(
        tmp_path,
        client,
        recovery_enabled=True,
    )
    assert recovery is not None

    assert asyncio.run(worker.drain_due()) == 2
    assert worker.results[0].status == "WAITING_FOR_MODEL"
    assert worker.results[1].status == "BLOCKED_BY_EARLIER_RUN"
    assert database.connection.execute(
        "SELECT status FROM runs WHERE run_id = 'S01-run-01'"
    ).fetchone()[0] == "WAITING_FOR_MODEL"

    clock.advance(timedelta(hours=4))
    promoted = recovery.poll()
    assert len(promoted) == 1
    assert promoted[0].status == "RECOVERY_REQUIRED"

    retry = CommandBus(database, clock=clock).execute(
        ResolveRecovery(
            request_id="pilot-retry",
            season_id="S01",
            run_id="S01-run-01",
            decision="retry",
        )
    )
    assert retry.payload["decision"] == "retry"
    processed = asyncio.run(worker.drain_due())
    assert processed == 21
    assert database.connection.execute(
        "SELECT COUNT(*) FROM runs WHERE status = 'COMPLETED'"
    ).fetchone()[0] == 21
    assert database.connection.execute(
        "SELECT COUNT(*) FROM recovery_requests WHERE status = 'RETRY'"
    ).fetchone()[0] == 1
