from pathlib import Path

import pytest

from improv_troupe.application import (
    CommandBus,
    CommandError,
    CommandRequestConflict,
    ControlSeason,
    CreateSeason,
    EnterRecovery,
    GreenSeason,
    PreflightSeason,
    ReviseOpening,
    ResolveRecovery,
    SetWellnessPolicy,
    TransitionSeason,
)
from improv_troupe.application.fake_workflow import FakeWorkflowWorker
from improv_troupe.clock import VirtualClock
from datetime import datetime, timedelta

from improv_troupe.domain import CastMember, OpeningSnapshot, SeasonStatus


def _bus(tmp_path: Path) -> CommandBus:
    return CommandBus(tmp_path / "state" / "improv.sqlite3")


def _revise_opening(
    bus: CommandBus,
    *,
    cast_names: tuple[str, ...] = ("MARA",),
    request_id: str = "opening",
):
    opening = OpeningSnapshot(
        set="Observatory",
        setting="Orbit",
        cast=list(cast_names),
        world_rules=["Promises persist."],
    )
    cast = tuple(
        CastMember(character_id=name.lower(), name=name) for name in cast_names
    )
    return bus.execute(
        ReviseOpening(
            request_id=request_id,
            season_id="S01",
            opening=opening,
            cast=cast,
        )
    )


def _preflight(bus: CommandBus, request_id: str = "preflight"):
    return bus.execute(
        PreflightSeason(
            request_id=request_id,
            season_id="S01",
            checks={"models": True, "storage": True, "scheduler": True},
            model_manifest={"actor": "candidate-8b", "orchestrator": "candidate-20b"},
        )
    )


def test_create_and_transition_commands_are_typed_and_durable(tmp_path):
    bus = _bus(tmp_path)

    created = bus.execute(
        CreateSeason(
            request_id="req-create",
            season_id="S01",
            season_number=1,
            title="The Observatory",
        )
    )
    assert created.payload["status"] == "DRAFT"
    assert created.payload["version"] == 0

    awaiting = bus.execute(
        TransitionSeason(
            request_id="req-awaiting",
            season_id="S01",
            target=SeasonStatus.AWAITING_GREEN,
        )
    )
    assert awaiting.payload["status"] == "AWAITING_GREEN"
    assert awaiting.payload["version"] == 1


def test_wellness_policy_is_a_replay_safe_season_command(tmp_path):
    bus = _bus(tmp_path)
    bus.execute(CreateSeason(request_id="create", season_id="S01", season_number=1))

    changed = bus.execute(
        SetWellnessPolicy(
            request_id="manual-review",
            season_id="S01",
            auto_tap_out=False,
        )
    )
    replay = bus.execute(
        SetWellnessPolicy(
            request_id="manual-review",
            season_id="S01",
            auto_tap_out=False,
        )
    )

    assert changed.payload["auto_tap_out"] is False
    assert changed.payload["version"] == 1
    assert replay.replayed
    assert bus.seasons.get("S01").auto_tap_out is False
    event = bus.database.connection.execute(
        "SELECT payload_json FROM domain_events WHERE event_type = 'WellnessPolicyChanged'"
    ).fetchone()
    assert '"manual_review": true' in event["payload_json"]


def test_replaying_same_request_returns_saved_response_without_second_transition(tmp_path):
    bus = _bus(tmp_path)
    command = CreateSeason(request_id="req-1", season_id="S01", season_number=1)
    first = bus.execute(command)
    second = bus.execute(command)

    assert not first.replayed
    assert second.replayed
    assert second.payload == first.payload
    assert len(bus.seasons.list_all()) == 1


def test_reusing_request_id_for_different_intent_is_rejected(tmp_path):
    bus = _bus(tmp_path)
    bus.execute(CreateSeason(request_id="req-1", season_id="S01", season_number=1))

    with pytest.raises(CommandRequestConflict):
        bus.execute(CreateSeason(request_id="req-1", season_id="S02", season_number=2))


def test_request_journal_and_command_effects_commit_atomically(tmp_path, monkeypatch):
    bus = _bus(tmp_path)

    def fail_store(**_kwargs):
        raise RuntimeError("simulated journal failure")

    monkeypatch.setattr(bus.requests, "store", fail_store)
    with pytest.raises(RuntimeError, match="simulated journal failure"):
        bus.execute(CreateSeason(request_id="req-atomic", season_id="S01", season_number=1))

    assert bus.seasons.list_all() == []
    assert bus.database.connection.execute("SELECT COUNT(*) FROM domain_events").fetchone()[0] == 0
    assert bus.requests.get("req-atomic") is None


def test_blank_request_id_is_rejected_before_mutation(tmp_path):
    bus = _bus(tmp_path)
    with pytest.raises(CommandError):
        bus.execute(CreateSeason(request_id=" ", season_id="S01", season_number=1))


def test_green_snapshots_opening_and_enqueues_all_pilot_runs(tmp_path):
    bus = _bus(tmp_path)
    bus.execute(CreateSeason(request_id="create", season_id="S01", season_number=1))
    bus.execute(
        TransitionSeason(
            request_id="awaiting",
            season_id="S01",
            target=SeasonStatus.AWAITING_GREEN,
        )
    )
    _revise_opening(bus, cast_names=("MARA", "JONAS"))
    _preflight(bus)
    result = bus.execute(
        GreenSeason(
            request_id="green",
            season_id="S01",
            green_at=datetime.fromisoformat("2026-08-20T07:00:00-07:00"),
            opening=OpeningSnapshot(
                set="Observatory",
                setting="Orbit",
                cast=["MARA", "JONAS"],
                world_rules=["Promises persist."],
            ),
            cast=(
                CastMember(character_id="mara", name="MARA"),
                CastMember(character_id="jonas", name="JONAS"),
            ),
        )
    )
    assert result.payload["status"] == "ARMED"
    assert result.payload["run_count"] == 21
    connection = bus.database.connection
    assert connection.execute("SELECT COUNT(*) FROM work_items").fetchone()[0] == 21
    assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 21


def test_opening_revision_is_versioned_and_only_exposes_creator_fields(tmp_path):
    bus = _bus(tmp_path)
    bus.execute(CreateSeason(request_id="create", season_id="S01", season_number=1))
    revised = _revise_opening(bus)
    assert set(revised.payload["opening"]) == {"set", "setting", "cast", "world_rules"}
    assert "model_manifest" not in revised.payload
    assert revised.payload["opening_version"] == 1
    assert bus.database.connection.execute(
        "SELECT COUNT(*) FROM season_opening_versions"
    ).fetchone()[0] == 1


def test_revision_invalidates_preflight_before_green(tmp_path):
    bus = _bus(tmp_path)
    bus.execute(CreateSeason(request_id="create", season_id="S01", season_number=1))
    _revise_opening(bus)
    _preflight(bus)
    bus.execute(
        TransitionSeason(
            request_id="awaiting", season_id="S01", target=SeasonStatus.AWAITING_GREEN
        )
    )
    _revise_opening(bus, request_id="opening-2")
    with pytest.raises(CommandError, match="preflight"):
        bus.execute(
            GreenSeason(
                request_id="green",
                season_id="S01",
                green_at=datetime.fromisoformat("2026-08-20T07:00:00-07:00"),
                opening=OpeningSnapshot(
                    set="Observatory",
                    setting="Orbit",
                    cast=["MARA"],
                    world_rules=["Promises persist."],
                ),
                cast=(CastMember(character_id="mara", name="MARA"),),
            )
        )


def test_green_is_rejected_until_preflight_passes(tmp_path):
    bus = _bus(tmp_path)
    bus.execute(CreateSeason(request_id="create", season_id="S01", season_number=1))
    bus.execute(
        TransitionSeason(
            request_id="awaiting", season_id="S01", target=SeasonStatus.AWAITING_GREEN
        )
    )
    _revise_opening(bus)
    with pytest.raises(CommandError, match="preflight"):
        bus.execute(
            GreenSeason(
                request_id="green",
                season_id="S01",
                green_at=datetime.fromisoformat("2026-08-20T07:00:00-07:00"),
                opening=OpeningSnapshot(set="Observatory", setting="Orbit", cast=["MARA"]),
                cast=(CastMember(character_id="mara", name="MARA"),),
            )
        )
    passed = _preflight(bus)
    assert passed.payload["preflight_passed"] is True


def test_failed_preflight_does_not_mutate_the_season(tmp_path):
    bus = _bus(tmp_path)
    bus.execute(CreateSeason(request_id="create", season_id="S01", season_number=1))
    _revise_opening(bus)
    with pytest.raises(CommandError, match="checks failed"):
        bus.execute(
            PreflightSeason(
                request_id="preflight-failed",
                season_id="S01",
                checks={"models": False},
                model_manifest={"actor": "candidate-8b"},
            )
        )
    season = bus.seasons.get("S01")
    assert not season.preflight_passed
    assert season.version == 1


def test_control_command_uses_domain_transition_rules(tmp_path):
    bus = _bus(tmp_path)
    bus.execute(CreateSeason(request_id="create", season_id="S01", season_number=1))
    bus.execute(
        TransitionSeason(
            request_id="awaiting",
            season_id="S01",
            target=SeasonStatus.AWAITING_GREEN,
        )
    )
    _revise_opening(bus)
    _preflight(bus)
    bus.execute(
        GreenSeason(
            request_id="green",
            season_id="S01",
            green_at=datetime.fromisoformat("2026-08-20T07:00:00-07:00"),
            opening=OpeningSnapshot(
                set="Observatory",
                setting="Orbit",
                cast=["MARA"],
                world_rules=["Promises persist."],
            ),
            cast=(CastMember(character_id="mara", name="MARA"),),
        )
    )
    paused = bus.execute(
        ControlSeason(
            request_id="pause",
            season_id="S01",
            target=SeasonStatus.PAUSED,
        )
    )
    assert paused.payload["status"] == "PAUSED"
    queued_before_resume = bus.database.connection.execute(
        "SELECT COUNT(*) FROM work_items WHERE kind = 'RUN_SCENE' AND status = 'QUEUED'"
    ).fetchone()[0]
    resumed = bus.execute(
        ControlSeason(
            request_id="resume",
            season_id="S01",
            target=SeasonStatus.RUNNING,
        )
    )
    assert resumed.payload["status"] == "RUNNING"
    assert bus.database.connection.execute(
        "SELECT COUNT(*) FROM work_items WHERE kind = 'RUN_SCENE' AND status = 'QUEUED'"
    ).fetchone()[0] == queued_before_resume
    bus.execute(
        ControlSeason(
            request_id="pause-again",
            season_id="S01",
            target=SeasonStatus.PAUSED,
        )
    )

    closing = bus.execute(
        ControlSeason(
            request_id="close",
            season_id="S01",
            target=SeasonStatus.CLOSING,
        )
    )
    assert closing.payload["status"] == "CLOSING"
    assert bus.database.connection.execute(
        "SELECT COUNT(*) FROM work_items WHERE kind = 'BUILD_HANDOFF'"
    ).fetchone()[0] == 1
    completed = bus.execute(
        TransitionSeason(
            request_id="complete",
            season_id="S01",
            target=SeasonStatus.SEASON_COMPLETE,
        )
    )
    assert completed.payload["status"] == "SEASON_COMPLETE"
    second = bus.execute(
        CreateSeason(request_id="create-2", season_id="S02", season_number=2)
    )
    assert second.payload["status"] == "DRAFT"

    with pytest.raises(Exception):
        bus.execute(
            ControlSeason(
                request_id="invalid",
                season_id="S01",
                target=SeasonStatus.PUBLISHED,
            )
        )


def test_recovery_retry_and_skip_are_explicit_creator_decisions(tmp_path):
    bus = _bus(tmp_path)
    bus.execute(CreateSeason(request_id="create", season_id="S01", season_number=1))
    bus.execute(
        TransitionSeason(
            request_id="awaiting", season_id="S01", target=SeasonStatus.AWAITING_GREEN
        )
    )
    _revise_opening(bus)
    _preflight(bus)
    bus.execute(
        GreenSeason(
            request_id="green",
            season_id="S01",
            green_at=datetime.fromisoformat("2026-08-20T07:00:00-07:00"),
            opening=OpeningSnapshot(
                set="Observatory",
                setting="Orbit",
                cast=["MARA"],
                world_rules=["Promises persist."],
            ),
            cast=(CastMember(character_id="mara", name="MARA"),),
        )
    )
    bus.execute(
        ControlSeason(request_id="run", season_id="S01", target=SeasonStatus.RUNNING)
    )
    entered = bus.execute(
        EnterRecovery(
            request_id="recover-1",
            season_id="S01",
            run_id="S01-run-01",
        )
    )
    assert entered.payload["status"] == "RECOVERY_REQUIRED"
    retried = bus.execute(
        ResolveRecovery(
            request_id="retry", season_id="S01", run_id="S01-run-01", decision="retry"
        )
    )
    assert retried.payload["decision"] == "retry"
    assert retried.payload["status"] == "RUNNING"
    bus.execute(
        EnterRecovery(
            request_id="recover-2",
            season_id="S01",
            run_id="S01-run-02",
        )
    )
    skipped = bus.execute(
        ResolveRecovery(
            request_id="skip", season_id="S01", run_id="S01-run-02", decision="skip"
        )
    )
    assert skipped.payload["decision"] == "skip"
    assert skipped.payload["status"] == "RUNNING"


def test_recovery_retry_accepts_armed_legacy_season(tmp_path):
    bus = _bus(tmp_path)
    bus.execute(CreateSeason(request_id="create", season_id="S01", season_number=1))
    bus.execute(
        TransitionSeason(
            request_id="awaiting", season_id="S01", target=SeasonStatus.AWAITING_GREEN
        )
    )
    _revise_opening(bus)
    _preflight(bus)
    bus.execute(
        GreenSeason(
            request_id="green",
            season_id="S01",
            green_at=datetime.fromisoformat("2026-08-20T07:00:00-07:00"),
            opening=OpeningSnapshot(
                set="Observatory",
                setting="Orbit",
                cast=["MARA"],
                world_rules=["Promises persist."],
            ),
            cast=(CastMember(character_id="mara", name="MARA"),),
        )
    )
    bus.records.update_run_status(
        run_id="S01-run-01",
        status="RECOVERY_REQUIRED",
        completion_reason="actor_output_invalid:mara",
        expected_status="QUEUED",
    )
    bus.records.insert_recovery(
        recovery_id="recovery:S01:S01-run-01:1",
        season_id="S01",
        run_id="S01-run-01",
        status="RECOVERY_REQUIRED",
        created_at="2026-08-21T13:00:00+00:00",
    )

    retried = bus.execute(
        ResolveRecovery(
            request_id="retry-armed",
            season_id="S01",
            run_id="S01-run-01",
            decision="retry",
        )
    )

    assert retried.payload["decision"] == "retry"
    assert retried.payload["status"] == "RUNNING"


def test_recovery_decision_is_rejected_without_an_entered_recovery(tmp_path):
    bus = _bus(tmp_path)
    bus.execute(CreateSeason(request_id="create", season_id="S01", season_number=1))
    with pytest.raises(CommandError, match="require a season in recovery"):
        bus.execute(
            ResolveRecovery(
                request_id="invalid-recovery",
                season_id="S01",
                run_id="S01-run-01",
                decision="skip",
            )
        )


def test_fake_worker_claims_due_work_once_and_leaves_future_work_queued(tmp_path):
    bus = _bus(tmp_path)
    bus.execute(CreateSeason(request_id="create", season_id="S01", season_number=1))
    bus.execute(
        TransitionSeason(
            request_id="awaiting", season_id="S01", target=SeasonStatus.AWAITING_GREEN
        )
    )
    _revise_opening(bus)
    _preflight(bus)
    green = bus.execute(
        GreenSeason(
            request_id="green",
            season_id="S01",
            green_at=datetime.fromisoformat("2026-08-20T07:00:00-07:00"),
            opening=OpeningSnapshot(
                set="Observatory",
                setting="Orbit",
                cast=["MARA"],
                world_rules=["Promises persist."],
            ),
            cast=(CastMember(character_id="mara", name="MARA"),),
        )
    )
    clock = VirtualClock(datetime.fromisoformat(green.payload["first_run_at"]))
    worker = FakeWorkflowWorker(bus.database, clock)

    assert worker.drain_due(limit=1) == 1
    assert worker.drain_due(limit=1) == 0
    assert len(worker.completed) == 1

    clock.advance(timedelta(hours=6))
    assert worker.drain_due(limit=1) == 1
