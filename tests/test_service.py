import asyncio
from datetime import datetime, timezone

from improv_troupe.application import (
    DryRunSceneFactory,
    ServicePaths,
    build_linux_service,
    read_service_status,
)
from improv_troupe.clock import VirtualClock
from improv_troupe.domain import ScheduleSlot, Season
from improv_troupe.infrastructure import (
    RecordRepository,
    SQLiteDatabase,
    ScheduleRepository,
    SeasonRepository,
    WorkQueue,
)


def _setup(tmp_path):
    paths = ServicePaths.from_root(tmp_path / "improv-data")
    paths.prepare()
    database = SQLiteDatabase(paths.database_path)
    database.migrate()
    SeasonRepository(database).create(Season(season_id="S01", season_number=1))
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
    return paths, database


def test_linux_service_projects_one_due_dry_run_and_reports_status(tmp_path):
    paths, database = _setup(tmp_path)
    clock = VirtualClock(datetime(2026, 8, 21, 20, tzinfo=timezone.utc))
    service = build_linux_service(
        paths=paths,
        database=database,
        scene_factory=DryRunSceneFactory(database),
        clock=clock,
    )

    cycle = asyncio.run(service.run_once())

    assert cycle.processed_items == 1
    assert cycle.results[0].status == "COMPLETED"
    status = read_service_status(database, paths=paths, now=clock.now())
    assert status["runs"] == {"total": 1, "by_status": {"COMPLETED": 1}}
    assert status["work"]["by_status"] == {"COMPLETED": 1}
    assert status["work"]["due_queued"] == 0
    assert status["seasons"][0]["next_run"] is None
    assert status["seasons"][0]["wellness_policy"] == "AUTOMATIC_TAP_OUT"


def test_linux_service_startup_is_idempotent_and_creates_persistent_roots(tmp_path):
    paths = ServicePaths.from_root(tmp_path / "new-data")
    database = SQLiteDatabase(paths.database_path)
    clock = VirtualClock(datetime(2026, 8, 21, 20, tzinfo=timezone.utc))
    service = build_linux_service(
        paths=paths,
        database=database,
        scene_factory=DryRunSceneFactory(database),
        clock=clock,
    )

    service.startup()
    service.startup()

    assert paths.database_path.exists()
    assert paths.roots.state.is_dir()
    assert paths.roots.private.is_dir()
    assert paths.roots.public.is_dir()
    assert database.connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 6
