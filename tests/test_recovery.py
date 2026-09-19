import asyncio
from datetime import datetime, timedelta, timezone

from improv_troupe.application import (
    DurableWorkflowWorker,
    RecoveryTimerService,
    SceneRunError,
)
from improv_troupe.clock import VirtualClock
from improv_troupe.domain import ScheduleSlot, Season
from improv_troupe.infrastructure import RecordRepository, SQLiteDatabase, ScheduleRepository, SeasonRepository, WorkQueue


def _setup(tmp_path, *, season_status="RUNNING"):
    database = SQLiteDatabase(tmp_path / "state" / "improv.sqlite3")
    database.migrate()
    SeasonRepository(database).create(
        Season(season_id="S01", season_number=1, status=season_status)
    )
    local = datetime.fromisoformat("2026-08-21T06:00:00-07:00")
    slot = ScheduleSlot(
        slot_id="S01-run-01",
        season_id="S01",
        day_number=1,
        slot_number=1,
        run_number=1,
        scheduled_local=local,
        scheduled_utc=local.astimezone(timezone.utc),
        utc_offset="-07:00",
    )
    ScheduleRepository(database).add(slot)
    RecordRepository(database).insert_run(
        run_id=slot.slot_id,
        season_id="S01",
        slot_id=slot.slot_id,
        status="QUEUED",
    )
    WorkQueue(database).enqueue(
        work_id="work:S01-run-01",
        natural_key="run:S01-run-01",
        kind="RUN_SCENE",
        payload={"run_id": slot.slot_id, "season_id": "S01"},
        available_at=slot.scheduled_utc.isoformat(),
    )
    return database


def test_model_failure_waits_four_hours_then_requires_creator_recovery(tmp_path):
    database = _setup(tmp_path)
    clock = VirtualClock(datetime(2026, 8, 21, 13, tzinfo=timezone.utc))
    timer = RecoveryTimerService(database=database, clock=clock)
    records = RecordRepository(database)
    records.update_run_status(
        run_id="S01-run-01",
        status="INTERRUPTED",
        completion_reason="backend_timeout",
        expected_status="QUEUED",
    )

    waiting = timer.begin_waiting(
        season_id="S01", run_id="S01-run-01", reason="actor_call_failed"
    )

    assert waiting.status == "WAITING_FOR_MODEL"
    assert waiting.available_at.hour == 17
    assert records.get_run("S01-run-01")["status"] == "WAITING_FOR_MODEL"
    assert timer.poll() == []

    clock.advance(waiting.available_at - clock.now())
    promoted = timer.poll()

    assert promoted[0].status == "RECOVERY_REQUIRED"
    assert records.get_run("S01-run-01")["status"] == "RECOVERY_REQUIRED"
    assert SeasonRepository(database).get("S01").status.value == "RECOVERY_REQUIRED"
    assert database.connection.execute(
        "SELECT kind FROM notifications WHERE kind = 'RECOVERY_REQUIRED'"
    ).fetchone()[0] == "RECOVERY_REQUIRED"


def test_zero_wait_promotes_on_the_next_poll_without_automatic_retry(tmp_path):
    database = _setup(tmp_path)
    clock = VirtualClock(datetime(2026, 8, 21, 13, tzinfo=timezone.utc))
    timer = RecoveryTimerService(
        database=database,
        clock=clock,
        wait_window=timedelta(0),
    )
    records = RecordRepository(database)
    records.update_run_status(
        run_id="S01-run-01",
        status="INTERRUPTED",
        completion_reason="backend_timeout",
        expected_status="QUEUED",
    )

    waiting = timer.begin_waiting(
        season_id="S01", run_id="S01-run-01", reason="actor_call_failed"
    )
    promoted = timer.poll()

    assert waiting.status == "WAITING_FOR_MODEL"
    assert len(promoted) == 1
    assert promoted[0].status == "RECOVERY_REQUIRED"
    assert records.get_run("S01-run-01")["status"] == "RECOVERY_REQUIRED"
    assert database.connection.execute(
        "SELECT status FROM recovery_requests"
    ).fetchone()[0] == "RECOVERY_REQUIRED"


def test_model_failure_from_armed_season_promotes_season_to_recovery(tmp_path):
    database = _setup(tmp_path, season_status="ARMED")
    clock = VirtualClock(datetime(2026, 8, 21, 13, tzinfo=timezone.utc))
    timer = RecoveryTimerService(database=database, clock=clock)
    records = RecordRepository(database)
    records.update_run_status(
        run_id="S01-run-01",
        status="INTERRUPTED",
        completion_reason="backend_timeout",
        expected_status="QUEUED",
    )

    waiting = timer.begin_waiting(
        season_id="S01", run_id="S01-run-01", reason="actor_call_failed"
    )
    clock.advance(waiting.available_at - clock.now())
    timer.poll()

    assert SeasonRepository(database).get("S01").status.value == "RECOVERY_REQUIRED"


def test_worker_routes_scene_failure_into_waiting_timer(tmp_path):
    database = _setup(tmp_path)
    clock = VirtualClock(datetime(2026, 8, 21, 13, tzinfo=timezone.utc))
    timer = RecoveryTimerService(database=database, clock=clock)

    class FailingScene:
        async def execute(self):
            raise SceneRunError("orchestrator_call_failed")

    worker = DurableWorkflowWorker(
        database=database,
        clock=clock,
        scene_factory=lambda payload: FailingScene(),
        recovery=timer,
    )

    assert asyncio.run(worker.drain_due()) == 1
    assert worker.results[0].status == "WAITING_FOR_MODEL"
    assert database.connection.execute("SELECT status FROM runs").fetchone()[0] == "WAITING_FOR_MODEL"
    assert database.connection.execute("SELECT status FROM work_items").fetchone()[0] == "COMPLETED"


def test_worker_auto_retries_only_a_bounded_transport_timeout(tmp_path):
    database = _setup(tmp_path)
    clock = VirtualClock(datetime(2026, 8, 21, 13, tzinfo=timezone.utc))
    timer = RecoveryTimerService(database=database, clock=clock)

    class TimingOutScene:
        async def execute(self):
            raise SceneRunError("actor_call_failed", error_type="ReadTimeout")

    worker = DurableWorkflowWorker(
        database=database,
        clock=clock,
        scene_factory=lambda payload: TimingOutScene(),
        recovery=timer,
        auto_retry_timeouts=True,
        timeout_retry_max_attempts=3,
    )

    assert asyncio.run(worker.drain_due()) == 1
    assert worker.results[0].status == "AUTO_RETRY_TIMEOUT"
    assert database.connection.execute("SELECT status FROM runs").fetchone()[0] == "INTERRUPTED"
    assert database.connection.execute("SELECT status FROM work_items").fetchone()[0] == "QUEUED"
    assert database.connection.execute("SELECT COUNT(*) FROM recovery_requests").fetchone()[0] == 0

    clock.advance(timedelta(minutes=1))
    assert asyncio.run(worker.drain_due()) == 1
    clock.advance(timedelta(minutes=1))
    assert asyncio.run(worker.drain_due()) == 1
    assert worker.results[-1].status == "WAITING_FOR_MODEL"
    assert database.connection.execute("SELECT status FROM runs").fetchone()[0] == "WAITING_FOR_MODEL"
