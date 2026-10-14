import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from improv_troupe.application import (
    LiveRuntimeConfigurationError,
    LiveSceneFactory,
    ModelCallExecutor,
    OrientationActor,
    OrientationService,
    SceneModelManifest,
    WellnessService,
    validate_model_manifest,
)
from improv_troupe.clock import VirtualClock
from improv_troupe.config import AppConfig, BackendConfig
from improv_troupe.domain import (
    CastMember,
    HiddenSeasonPlan,
    OpeningSnapshot,
    RoleSheet,
    ScheduleSlot,
    Season,
)
from improv_troupe.infrastructure import (
    DataRoots,
    EventRepository,
    RecordRepository,
    ScheduleRepository,
    SQLiteDatabase,
    SeasonRepository,
)
from improv_troupe.llm import ScriptedFakeClient
from improv_troupe.llm.diary_audience import DIARY_AUDIENCE_VERSION


def _setup(tmp_path, *, oriented=True):
    roots = DataRoots.from_root(tmp_path / "data")
    roots.prepare()
    database = SQLiteDatabase(roots.state / "improv.sqlite3")
    database.migrate()
    names = ["Mara", "Ivo", "Sable", "Jun"]
    cast = [
        CastMember(character_id=name.lower(), name=name)
        for name in names
    ]
    opening = OpeningSnapshot(
        set="A sealed observatory",
        setting="The last hour before the stars move",
        cast=names,
        world_rules=["The impossible may be true, but no one is forced to agree."],
    )
    plan = HiddenSeasonPlan(
        premise="Something in the observatory has begun answering questions.",
        role_sheets=[RoleSheet(character_id=member.character_id) for member in cast],
    )
    SeasonRepository(database).create(
        Season(
            season_id="S01",
            season_number=1,
            status="ARMED",
            opening=opening,
            private_plan=plan,
            cast=cast,
            model_manifest={
                "orchestrator": {"backend": "local", "model": "orchestrator-20b"},
                "actor_default": {"backend": "local", "model": "actor-8b"},
            },
        )
    )
    records = RecordRepository(database)
    first_morning = datetime.fromisoformat("2026-08-21T06:00:00-07:00")
    for run_number in range(1, 5):
        day_number = ((run_number - 1) // 3) + 1
        slot_number = ((run_number - 1) % 3) + 1
        local = first_morning + timedelta(
            days=day_number - 1,
            hours=(slot_number - 1) * 6,
        )
        run_id = f"S01-run-{run_number:02d}"
        ScheduleRepository(database).add(
            ScheduleSlot(
                slot_id=run_id,
                season_id="S01",
                day_number=day_number,
                slot_number=slot_number,
                run_number=run_number,
                scheduled_local=local,
                scheduled_utc=local.astimezone(timezone.utc),
                utc_offset="-07:00",
            )
        )
        records.insert_run(
            run_id=run_id,
            season_id="S01",
            slot_id=run_id,
            status="COMPLETED" if run_number < 4 else "QUEUED",
        )
    config = AppConfig(
        backends={
            "local": BackendConfig(
                base_url="http://127.0.0.1:11434/v1",
                kind="ollama",
            )
        }
    )
    if oriented:
        _orient(roots, database, cast)
    return roots, database, config, cast


def _orient(roots, database, cast, *, accepted=True):
    clock = VirtualClock(datetime(2026, 8, 21, tzinfo=timezone.utc))
    service = OrientationService(
        season_id="S01",
        wellness=WellnessService(
            database=database, season_id="S01", clock=clock, audit_root=roots.private,
        ),
    )
    for member in cast:
        executor = ModelCallExecutor(
            database=database,
            client=ScriptedFakeClient([f"<ACCEPTED>{str(accepted).lower()}</ACCEPTED>"]),
            clock=clock, audit_root=roots.private, backend="scripted-fake", model="actor-8b",
        )
        result = asyncio.run(service.orient(OrientationActor(member.character_id, member.name, executor)))
        assert result.accepted is accepted


@pytest.mark.parametrize("completed_actors", [0, 3])
def test_live_scene_cannot_start_with_missing_orientation(tmp_path, completed_actors):
    roots, database, config, cast = _setup(tmp_path, oriented=False)
    _orient(roots, database, cast[:completed_actors])
    clients_created = []
    factory = LiveSceneFactory(
        database=database, roots=roots, config=config,
        clock=VirtualClock(datetime(2026, 8, 21, tzinfo=timezone.utc)),
        client_factory=lambda handle: clients_created.append(handle),
    )
    # Preflight remains possible before the opening briefing; dispatch does not.
    factory.validate_season("S01")
    calls_before = database.connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0]
    with pytest.raises(LiveRuntimeConfigurationError, match="missing:.*jun"):
        factory({"season_id": "S01", "run_id": "S01-run-01"})
    assert not clients_created
    assert database.connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0] == calls_before


def test_declined_orientation_does_not_unlock_scene(tmp_path):
    roots, database, config, cast = _setup(tmp_path, oriented=False)
    _orient(roots, database, cast[:3])
    _orient(roots, database, cast[3:], accepted=False)
    factory = LiveSceneFactory(
        database=database, roots=roots, config=config,
        clock=VirtualClock(datetime(2026, 8, 21, tzinfo=timezone.utc)),
    )
    with pytest.raises(LiveRuntimeConfigurationError, match="missing: jun"):
        factory({"season_id": "S01", "run_id": "S01-run-01"})


def test_legacy_acceptance_without_briefing_receipt_does_not_unlock_scene(tmp_path):
    roots, database, config, cast = _setup(tmp_path, oriented=False)
    for member in cast:
        key = f"S01:orientation:{member.character_id}:accepted"
        EventRepository(database).append(
            event_id=key, natural_key=key, aggregate_type="cast_member",
            aggregate_id=f"S01:{member.character_id}", event_type="OrientationAccepted",
            payload={"character_id": member.character_id},
        )
    factory = LiveSceneFactory(
        database=database, roots=roots, config=config,
        clock=VirtualClock(datetime(2026, 8, 21, tzinfo=timezone.utc)),
    )
    with pytest.raises(LiveRuntimeConfigurationError, match="Do not backfill frozen season records"):
        factory({"season_id": "S01", "run_id": "S01-run-01"})


@pytest.mark.parametrize("broken_field,broken_value", [
    ("status", "TRANSPORT_FAILURE"),
    ("purpose", "orientation:OTHER:mara"),
])
def test_acceptance_must_link_to_completed_orientation_for_this_season(tmp_path, broken_field, broken_value):
    roots, database, config, _ = _setup(tmp_path)
    with database.transaction() as connection:
        # Controlled corruption of synthetic evidence must fail closed.
        connection.execute(
            f"UPDATE model_calls SET {broken_field} = ? WHERE call_id = ?",
            (broken_value, "S01:orientation:mara:a1"),
        )
    factory = LiveSceneFactory(
        database=database, roots=roots, config=config,
        clock=VirtualClock(datetime(2026, 8, 21, tzinfo=timezone.utc)),
    )
    with pytest.raises(LiveRuntimeConfigurationError, match="missing: mara"):
        factory({"season_id": "S01", "run_id": "S01-run-01"})


def test_live_scene_factory_builds_four_independent_character_sessions(tmp_path):
    roots, database, config, cast = _setup(tmp_path)
    factory = LiveSceneFactory(
        database=database,
        roots=roots,
        config=config,
        clock=VirtualClock(datetime(2026, 8, 21, tzinfo=timezone.utc)),
    )

    runner = factory({"season_id": "S01", "run_id": "S01-run-01"})

    assert len(runner.actors) == 4
    assert {actor.character_id for actor in runner.actors} == {member.character_id for member in cast}
    assert {actor.executor.model for actor in runner.actors} == {"actor-8b"}
    assert runner.orchestrator.model == "orchestrator-20b"
    assert runner.orchestrator.backend == "local"
    assert runner.orchestrator.client._timeout == 300
    assert runner.day_number == 1
    assert runner.slot_number == 1
    events = database.connection.execute(
        "SELECT payload_json FROM domain_events WHERE event_type='OrientationAccepted'"
    ).fetchall()
    assert len(events) == 4
    for event in events:
        receipt = json.loads(event["payload_json"])
        assert receipt["diary_audience_version"] == DIARY_AUDIENCE_VERSION
        call = database.connection.execute(
            "SELECT prompt_version_id,prompt_path FROM model_calls WHERE call_id = ?",
            (receipt["call_id"],),
        ).fetchone()
        assert call["prompt_version_id"] == "orientation-v2-explicit-diary-audience"
        with open(call["prompt_path"], encoding="utf-8") as prompt:
            assert "readers outside the fictional scene" in prompt.read()
    assert database.connection.execute("SELECT COUNT(*) FROM consent_decisions").fetchone()[0] == 0


def test_manifest_validation_rejects_unknown_backend_before_model_calls(tmp_path):
    _, _, config, cast = _setup(tmp_path)
    manifest = SceneModelManifest.model_validate(
        {
            "orchestrator": {"backend": "missing", "model": "orchestrator-20b"},
            "actor_default": {"backend": "local", "model": "actor-8b"},
        }
    )

    with pytest.raises(LiveRuntimeConfigurationError, match="unknown backend"):
        validate_model_manifest(
            manifest,
            actor_ids=[member.character_id for member in cast],
            config=config,
        )


def test_live_scene_factory_propagates_per_binding_params(tmp_path):
    roots, database, config, cast = _setup(tmp_path)
    season = SeasonRepository(database).get("S01")
    season.model_manifest = {
        "orchestrator": {
            "backend": "local",
            "model": "orchestrator-20b",
            "params": {"reasoning_effort": "low"},
        },
        "actors": {
            cast[0].character_id: {
                "backend": "local",
                "model": "ministral-3:8b",
                "params": {"temperature": 0.7},
            },
            cast[1].character_id: {
                "backend": "local",
                "model": "qwen3:8b",
                "params": {"reasoning_effort": "none"},
            },
            cast[2].character_id: {
                "backend": "local",
                "model": "qwen3-uncensored:8b",
                "params": {"temperature": 0.8},
            },
            cast[3].character_id: {
                "backend": "local",
                "model": "ministral-3:8b",
            },
        },
    }
    expected_version = season.version
    season.version += 1
    SeasonRepository(database).update(season, expected_version=expected_version)

    factory = LiveSceneFactory(
        database=database,
        roots=roots,
        config=config,
        clock=VirtualClock(datetime(2026, 8, 21, tzinfo=timezone.utc)),
    )
    runner = factory({"season_id": "S01", "run_id": "S01-run-01"})

    by_character = {actor.character_id: actor.executor for actor in runner.actors}
    assert by_character[cast[0].character_id].default_params == {"temperature": 0.7}
    assert by_character[cast[1].character_id].default_params == {"reasoning_effort": "none"}
    assert by_character[cast[2].character_id].model == "qwen3-uncensored:8b"
    assert runner.orchestrator.default_params == {"reasoning_effort": "low"}


def test_run_four_wakes_on_day_two_with_bounded_durable_continuity(tmp_path):
    roots, database, config, cast = _setup(tmp_path)
    records = RecordRepository(database)
    events = EventRepository(database)

    outcome_path = roots.private / "runs" / "S01-run-03" / "scene" / "round-4.md"
    outcome_path.parent.mkdir(parents=True, exist_ok=True)
    outcome_path.write_text(
        "The crew stabilizes the core and hears three knocks from below.",
        encoding="utf-8",
    )
    records.insert_turn(
        turn_id="S01-run-03:stage:4",
        run_id="S01-run-03",
        round_number=4,
        character_id="__orchestrator__",
        disposition="NARRATION_ACCEPT",
        content_path=str(outcome_path),
    )
    events.append(
        event_id="S01-run-03:orchestrator:4",
        natural_key="S01-run-03:orchestrator:4",
        aggregate_type="run",
        aggregate_id="S01-run-03",
        event_type="OrchestratorRoundAccepted",
        payload={
            "round_number": 4,
            "canon_updates": ["Three knocks came from below the stabilized core."],
        },
    )
    for index, member in enumerate(cast[:2], start=1):
        events.append(
            event_id=f"S01-run-03:turn:4:{member.character_id}",
            natural_key=f"S01-run-03:turn:4:{member.character_id}",
            aggregate_type="run",
            aggregate_id="S01-run-03",
            event_type="TurnAccepted",
            payload={
                "round_number": 4,
                "character_id": member.character_id,
                "memory_notes": [f"private memory {index}"],
            },
        )

    direction_path = roots.private / "seasons" / "S01" / "day-02" / "direction.md"
    direction_path.parent.mkdir(parents=True, exist_ok=True)
    direction_path.write_text(
        "At breakfast, let the knocking answer a harmless joke before it becomes a choice.",
        encoding="utf-8",
    )
    events.append(
        event_id="S01:direction:day:2",
        natural_key="S01:direction:day:2",
        aggregate_type="season",
        aggregate_id="S01",
        event_type="NextDayDirectionCreated",
        payload={
            "source_day_number": 1,
            "target_day_number": 2,
            "content_path": str(direction_path),
            "canon_updates": [],
        },
    )

    factory = LiveSceneFactory(
        database=database,
        roots=roots,
        config=config,
        clock=VirtualClock(datetime(2026, 8, 22, 13, tzinfo=timezone.utc)),
    )
    runner = factory({"season_id": "S01", "run_id": "S01-run-04"})

    assert runner.day_number == 2
    assert runner.slot_number == 1
    assert "overnight sleep period has passed" in runner._opening_direction()
    assert "three knocks from below" in runner.previous_shared_outcome
    assert runner.prior_accepted_canon == (
        "Three knocks came from below the stabilized core.",
    )
    by_character = {actor.character_id: actor for actor in runner.actors}
    assert by_character[cast[0].character_id].known_memory == ("private memory 1",)
    assert "private memory 2" not in by_character[cast[0].character_id].known_memory
    assert "harmless joke" in runner.private_day_direction
    assert "harmless joke" not in runner._opening_direction()
