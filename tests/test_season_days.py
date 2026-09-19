import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from improv_troupe.application import (
    DiaryActor,
    ModelCallExecutor,
    SceneActor,
    SceneRunResult,
    SeasonDayCoordinator,
)
from improv_troupe.clock import VirtualClock
from improv_troupe.domain import (
    CastMember,
    HiddenSeasonPlan,
    OpeningSnapshot,
    RoleSheet,
    ScheduleSlot,
    Season,
)
from improv_troupe.engine.transcript import Transcript
from improv_troupe.infrastructure import (
    DataRoots,
    EventRepository,
    RecordRepository,
    SQLiteDatabase,
    ScheduleRepository,
    SeasonRepository,
)
from improv_troupe.llm import ScriptedFakeClient, ScriptedStream


def _diary_response(character_id: str, *, slot: int = 1) -> ScriptedStream:
    return ScriptedStream(
        (
            f"<DIARY_SLOT>{slot}</DIARY_SLOT><WRITE_NOW>true</WRITE_NOW>"
            f"<DIARY_TEXT>{character_id} remembers the impossible door.</DIARY_TEXT>"
            "<EVIDENCE_REFS>1</EVIDENCE_REFS>",
        )
    )


def _fidelity_response() -> ScriptedStream:
    return ScriptedStream(
        (
            "<DECISION>ACCEPT</DECISION>"
            "<SUMMARY>The diary remains within the accepted scene.</SUMMARY>",
        )
    )


def test_day_coordinator_accepts_diaries_and_directs_next_day_after_third_run(tmp_path):
    roots = DataRoots.from_root(tmp_path / "data")
    roots.prepare()
    database = SQLiteDatabase(roots.state / "improv.sqlite3")
    database.migrate()
    names = ["Mara", "Nox", "Iris", "Sol"]
    cast = [CastMember(character_id=name.lower(), name=name) for name in names]
    opening = OpeningSnapshot(
        set="A house that remembers",
        setting="A science-fantasy threshold",
        cast=names,
        world_rules=["No actor-on-actor violence."],
    )
    plan = HiddenSeasonPlan(
        premise="The door is waiting for a name.",
        role_sheets=[RoleSheet(character_id=member.character_id) for member in cast],
    )
    SeasonRepository(database).create(
        Season(
            season_id="S01",
            season_number=1,
            status="RUNNING",
            opening=opening,
            private_plan=plan,
            cast=cast,
        )
    )
    records = RecordRepository(database)
    local_base = datetime.fromisoformat("2026-08-21T06:00:00-07:00")
    for slot_number in (1, 2, 3):
        local = local_base.replace(hour=6 + (slot_number - 1) * 6)
        slot = ScheduleSlot(
            slot_id=f"S01-run-{slot_number:02d}",
            season_id="S01",
            day_number=1,
            slot_number=slot_number,
            run_number=slot_number,
            scheduled_local=local,
            scheduled_utc=local.astimezone(timezone.utc),
            utc_offset="-07:00",
        )
        ScheduleRepository(database).add(slot)
        records.insert_run(
            run_id=slot.slot_id,
            season_id="S01",
            slot_id=slot.slot_id,
            status="COMPLETED",
        )

    clock = VirtualClock(datetime(2026, 8, 21, 20, tzinfo=timezone.utc))
    actors = tuple(
        SceneActor(
            character_id=member.character_id,
            name=member.name,
            role_sheet=RoleSheet(character_id=member.character_id),
            executor=ModelCallExecutor(
                database=database,
                client=ScriptedFakeClient(
                    (
                        [
                            ScriptedStream(("truncated diary",)),
                            _diary_response(member.character_id, slot=3),
                        ]
                        if member.character_id == "mara"
                        else [_diary_response(member.character_id)]
                    )
                ),
                clock=clock,
                audit_root=roots.private,
                backend="fake",
                model="actor-8b-test",
            ),
        )
        for member in cast
    )
    orchestrator = ModelCallExecutor(
        database=database,
        client=ScriptedFakeClient(
            [
                *[_fidelity_response() for _ in range(4)],
                ScriptedStream(
                    ("<NARRATION>The house opens one room farther.</NARRATION>"
                     "<COMPLETE>false</COMPLETE>",)
                ),
            ]
        ),
        clock=clock,
        audit_root=roots.private,
        backend="fake",
        model="orchestrator-20b-test",
    )
    stage_path = roots.private / "runs" / "S01-run-01" / "scene" / "round-1.md"
    stage_path.parent.mkdir(parents=True, exist_ok=True)
    stage_path.write_text(
        "A warm impossible door opens after Mara names it.", encoding="utf-8"
    )
    records.insert_turn(
        turn_id="S01-run-01:stage:1",
        run_id="S01-run-01",
        round_number=1,
        character_id="__orchestrator__",
        disposition="NARRATION_ACCEPT",
        content_path=str(stage_path),
    )
    EventRepository(database).append(
        event_id="S01-run-01:orchestrator:1",
        natural_key="S01-run-01:orchestrator:1",
        aggregate_type="run",
        aggregate_id="S01-run-01",
        event_type="OrchestratorRoundAccepted",
        payload={
            "round_number": 1,
            "canon_updates": ["Mara named the warm impossible door."],
        },
    )
    scene = SimpleNamespace(actors=actors, orchestrator=orchestrator)
    scene_transcript = Transcript()
    scene_transcript.add_direction("A warm impossible door opens after Mara names it.")
    result = SceneRunResult(
        reason="complete",
        turns=1,
        transcript=scene_transcript,
    )
    coordinator = SeasonDayCoordinator(
        database=database,
        clock=clock,
        scene_factory=lambda payload: scene,
        strict_rehearsal_acceptance=True,
        review_diary_fidelity=True,
    )

    for slot_number in (1, 2, 3):
        asyncio.run(
            coordinator.after_scene(
                {
                    "season_id": "S01",
                    "run_id": f"S01-run-{slot_number:02d}",
                    "day_number": 1,
                    "slot_number": slot_number,
                },
                scene,
                result,
            )
        )

    assert database.connection.execute("SELECT closed FROM days").fetchone()[0] == 1
    assert database.connection.execute(
        "SELECT COUNT(*) FROM diaries WHERE status = 'WRITTEN'"
    ).fetchone()[0] == 4
    direction = database.connection.execute(
        "SELECT COUNT(*) FROM domain_events WHERE event_type = 'NextDayDirectionCreated'"
    ).fetchone()[0]
    assert direction == 1
    assert database.connection.execute(
        "SELECT COUNT(*) FROM work_items WHERE kind = 'CLOSE_DAY'"
    ).fetchone()[0] == 0
    prompt_path = database.connection.execute(
        "SELECT prompt_path FROM model_calls WHERE purpose = "
        "'next-day-direction:S01:day:2'"
    ).fetchone()[0]
    prompt = open(prompt_path, encoding="utf-8").read()
    assert "A warm impossible door opens" in prompt
    assert "Mara named the warm impossible door." in prompt
    assert "mara remembers the impossible door" in prompt
    assert "morning, afternoon, and evening" in prompt
    assert "overnight sleep interval" in prompt
    assert database.connection.execute(
        "SELECT COUNT(*) FROM model_calls WHERE purpose LIKE "
        "'diary:S01:mara:day:1:%'"
    ).fetchone()[0] == 2
    assert database.connection.execute(
        "SELECT COUNT(*) FROM domain_events WHERE event_type = 'DiaryFormatInvalid'"
    ).fetchone()[0] == 1
    assert database.connection.execute(
        "SELECT COUNT(*) FROM domain_events WHERE event_type = 'DiaryFidelityReviewed'"
    ).fetchone()[0] == 4
    assert database.connection.execute(
        "SELECT COUNT(*) FROM model_calls WHERE purpose LIKE 'diary-review:S01:%'"
    ).fetchone()[0] == 4

    EventRepository(database).append(
        event_id="S01:day:1:diary:mara:fidelity-replacement",
        natural_key="S01:day:1:diary:mara:fidelity-replacement",
        aggregate_type="diary",
        aggregate_id="S01:day:1:diary:mara",
        event_type="DiaryFidelityReviewed",
        payload={"review_status": "REJECTED"},
    )
    held_diaries = coordinator._closed_diary_text(
        "S01", 1, require_fidelity_review=True
    )
    assert any("mara: diary withheld pending causal-fidelity review" in text for text in held_diaries)
    assert all("mara remembers the impossible door" not in text for text in held_diaries)
