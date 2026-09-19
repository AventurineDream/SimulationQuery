import asyncio
from datetime import datetime, timezone

from improv_troupe.application import DurableWorkflowWorker, SceneRunError
from improv_troupe.clock import VirtualClock
from improv_troupe.domain import ScheduleSlot, Season
from improv_troupe.engine.transcript import Transcript
from improv_troupe.infrastructure import RecordRepository, SQLiteDatabase, WorkQueue, SeasonRepository, ScheduleRepository


class _FakeScene:
    def __init__(self, database, run_id, order):
        self.records = RecordRepository(database)
        self.run_id = run_id
        self.order = order

    async def execute(self):
        self.order.append(self.run_id)
        self.records.update_run_status(
            run_id=self.run_id,
            status="COMPLETED",
            completion_reason="fake_complete",
            expected_status="RUNNING",
        )
        return type("Result", (), {"reason": "fake_complete", "turns": 0, "transcript": Transcript()})()


def _setup(tmp_path, *, run_count=2, first_status="QUEUED", season_status="DRAFT"):
    database = SQLiteDatabase(tmp_path / "state" / "improv.sqlite3")
    database.migrate()
    SeasonRepository(database).create(
        Season(season_id="S01", season_number=1, status=season_status)
    )
    records = RecordRepository(database)
    queue = WorkQueue(database)
    for index in range(run_count):
        slot_number = index + 1
        local = datetime.fromisoformat(f"2026-08-21T{6 + (slot_number - 1) * 6:02d}:00-07:00")
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
        status = first_status if index == 0 else "QUEUED"
        records.insert_run(
            run_id=slot.slot_id,
            season_id="S01",
            slot_id=slot.slot_id,
            status=status,
        )
        queue.enqueue(
            work_id=f"work:{slot.slot_id}",
            natural_key=f"run:{slot.slot_id}",
            kind="RUN_SCENE",
            payload={"run_id": slot.slot_id, "season_id": "S01"},
            available_at=slot.scheduled_utc.isoformat(),
        )
    return database


def test_worker_processes_due_runs_in_original_order_and_records_delay(tmp_path):
    database = _setup(tmp_path)
    clock = VirtualClock(datetime(2026, 8, 21, 20, tzinfo=timezone.utc))
    order = []
    worker = DurableWorkflowWorker(
        database=database,
        clock=clock,
        scene_factory=lambda payload: _FakeScene(database, payload["run_id"], order),
    )

    assert asyncio.run(worker.drain_due()) == 2
    assert order == ["S01-run-01", "S01-run-02"]
    rows = database.connection.execute(
        "SELECT run_id, status, delay, actual_started_at, actual_completed_at "
        "FROM runs ORDER BY run_id"
    ).fetchall()
    assert [(row["status"], row["delay"]) for row in rows] == [
        ("COMPLETED", "+07:00:00"),
        ("COMPLETED", "+01:00:00"),
    ]
    assert all(row["actual_started_at"] and row["actual_completed_at"] for row in rows)
    assert database.connection.execute(
        "SELECT COUNT(*) FROM work_items WHERE status = 'COMPLETED'"
    ).fetchone()[0] == 2


def test_worker_promotes_armed_season_when_first_scene_starts(tmp_path):
    database = _setup(tmp_path, run_count=1, season_status="ARMED")
    clock = VirtualClock(datetime(2026, 8, 21, 13, tzinfo=timezone.utc))
    worker = DurableWorkflowWorker(
        database=database,
        clock=clock,
        scene_factory=lambda payload: _FakeScene(database, payload["run_id"], []),
    )

    assert asyncio.run(worker.drain_due()) == 1
    assert SeasonRepository(database).get("S01").status.value == "RUNNING"


def test_worker_does_not_run_later_scene_while_earlier_run_is_unresolved(tmp_path):
    database = _setup(tmp_path, run_count=2, first_status="INTERRUPTED")
    # Only make the later item available so the worker must inspect the earlier run.
    database.connection.execute(
        "UPDATE work_items SET status = 'COMPLETED' WHERE work_id = 'work:S01-run-01'"
    )
    database.connection.commit()
    clock = VirtualClock(datetime(2026, 8, 21, 20, tzinfo=timezone.utc))
    order = []
    worker = DurableWorkflowWorker(
        database=database,
        clock=clock,
        scene_factory=lambda payload: _FakeScene(database, payload["run_id"], order),
    )

    assert asyncio.run(worker.drain_due()) == 1
    assert order == []
    item = database.connection.execute(
        "SELECT status FROM work_items WHERE work_id = 'work:S01-run-02'"
    ).fetchone()
    assert item["status"] == "QUEUED"


def test_creator_retry_priority_precedes_older_due_later_work(tmp_path):
    database = _setup(tmp_path, run_count=2)
    queue = WorkQueue(database)
    queue.enqueue(
        work_id="work:retry:S01-run-01:creator",
        natural_key="retry:S01-run-01:creator",
        kind="RUN_SCENE",
        payload={"run_id": "S01-run-01", "season_id": "S01"},
        available_at="2026-08-21T20:00:00+00:00",
        priority=-100,
    )
    clock = VirtualClock(datetime(2026, 8, 21, 20, tzinfo=timezone.utc))
    claimed = queue.claim_due(
        worker_id="retry-test",
        now=clock.now().isoformat(),
        lease_until="2026-08-21T20:05:00+00:00",
    )

    assert claimed["work_id"] == "work:retry:S01-run-01:creator"


def test_later_day_scene_waits_for_earlier_day_closure(tmp_path):
    database = _setup(tmp_path, run_count=2)
    records = RecordRepository(database)
    records.insert_day(season_id="S01", day_number=1, original_date="2026-08-21")
    records.update_run_status(
        run_id="S01-run-01",
        status="COMPLETED",
        completion_reason="test_complete",
        expected_status="QUEUED",
    )
    database.connection.execute(
        "UPDATE work_items SET status = 'COMPLETED' WHERE work_id = 'work:S01-run-01'"
    )
    database.connection.execute(
        "UPDATE schedule_slots SET day_number = 2 WHERE slot_id = 'S01-run-02'"
    )
    database.connection.commit()
    clock = VirtualClock(datetime(2026, 8, 22, 12, tzinfo=timezone.utc))
    worker = DurableWorkflowWorker(
        database=database,
        clock=clock,
        scene_factory=lambda payload: _FakeScene(database, payload["run_id"], []),
    )

    assert asyncio.run(worker.drain_due()) == 1
    assert database.connection.execute(
        "SELECT status FROM work_items WHERE work_id = 'work:S01-run-02'"
    ).fetchone()[0] == "QUEUED"


def test_worker_can_close_a_rejected_scene_without_an_automatic_retry(tmp_path):
    database = _setup(tmp_path, run_count=1)
    clock = VirtualClock(datetime(2026, 8, 21, 13, tzinfo=timezone.utc))

    class RejectedScene:
        async def execute(self):
            raise SceneRunError("orchestrator_repeated_narration")

    worker = DurableWorkflowWorker(
        database=database,
        clock=clock,
        scene_factory=lambda payload: RejectedScene(),
        retry_non_transport_failures=False,
    )

    assert asyncio.run(worker.drain_due()) == 1
    assert worker.results[0].status == "REJECTED_FAILURE"
    assert database.connection.execute("SELECT status FROM runs").fetchone()[0] == "INTERRUPTED"
    assert database.connection.execute("SELECT status FROM work_items").fetchone()[0] == "COMPLETED"
