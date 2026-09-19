import sqlite3
from datetime import datetime, timezone

import pytest

from improv_troupe.domain import (
    Diary,
    DiaryStatus,
    OpeningSnapshot,
    Publication,
    ScheduleSlot,
    Season,
)
from improv_troupe.infrastructure.artifact_projector import (
    ArtifactProjectionError,
    ArtifactProjector,
)
from improv_troupe.infrastructure.db import SQLiteStore, _migration_path
from improv_troupe.infrastructure.filesystem import DataRoots, PathBoundaryError
from improv_troupe.infrastructure.repositories import (
    ArtifactOutboxRepository,
    EventRepository,
    ModelCallRepository,
    RecordRepository,
    RepositoryConflict,
    ScheduleRepository,
    SeasonRepository,
    WorkQueue,
)


def _slot() -> ScheduleSlot:
    local = datetime.fromisoformat("2026-08-21T06:00:00-07:00")
    scheduled_utc = local.astimezone(timezone.utc)
    return ScheduleSlot(
        slot_id="S01-run-01",
        season_id="S01",
        day_number=1,
        slot_number=1,
        run_number=1,
        scheduled_local=local,
        scheduled_utc=scheduled_utc,
        utc_offset="-07:00",
    )


def _store(tmp_path):
    store = SQLiteStore(tmp_path / "state" / "improv.sqlite3")
    store.migrate()
    return store


def test_migrations_are_idempotent_and_enable_wal_foreign_keys(tmp_path):
    store = _store(tmp_path)
    store.migrate()
    store.migrate()
    assert store.connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert store.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert [
        row[0]
        for row in store.connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )
    ] == [1, 2, 3, 4, 5, 6]
    assert store.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    store.close()


def test_numbered_migration_resolution_requires_exactly_one_file(tmp_path):
    migration = tmp_path / "002_dashboard_records.sql"
    migration.write_text("SELECT 1;", encoding="utf-8")
    assert _migration_path(2, tmp_path) == migration

    duplicate = tmp_path / "002_duplicate.sql"
    duplicate.write_text("SELECT 2;", encoding="utf-8")
    with pytest.raises(RuntimeError, match="requires exactly one"):
        _migration_path(2, tmp_path)
    with pytest.raises(RuntimeError, match="found 0"):
        _migration_path(3, tmp_path)
    with pytest.raises(ValueError, match="must be positive"):
        _migration_path(0, tmp_path)


def test_causal_turn_migration_preserves_legacy_rows_as_derived_evidence(tmp_path):
    database_path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.executescript(_migration_path(1).read_text(encoding="utf-8"))
    connection.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    connection.execute("INSERT INTO schema_migrations VALUES (1, '2026-08-01T00:00:00Z')")
    connection.execute(
        "INSERT INTO seasons(season_id, season_number, status, created_at, updated_at) "
        "VALUES ('S01', 1, 'SEASON_COMPLETE', 'now', 'now')"
    )
    connection.execute(
        "INSERT INTO schedule_slots(slot_id, season_id, day_number, slot_number, run_number, "
        "scheduled_local, scheduled_utc, utc_offset) VALUES "
        "('S01-run-01', 'S01', 1, 1, 1, 'local', 'utc', '-07:00')"
    )
    connection.execute(
        "INSERT INTO runs(run_id, season_id, slot_id, status) "
        "VALUES ('S01-run-01', 'S01', 'S01-run-01', 'COMPLETED')"
    )
    connection.execute(
        "INSERT INTO turns(turn_id, run_id, round_number, character_id, disposition) "
        "VALUES ('legacy-stage', 'S01-run-01', 1, 'stage', 'NARRATION_ACCEPT')"
    )
    connection.commit()
    connection.close()

    store = SQLiteStore(database_path)
    store.migrate()
    legacy = store.connection.execute(
        "SELECT accepted_sequence, caused_by_turn_id, accepted_at FROM turns "
        "WHERE turn_id = 'legacy-stage'"
    ).fetchone()
    assert tuple(legacy) == (None, None, None)

    sequence = RecordRepository(store).insert_turn(
        turn_id="new-actor",
        run_id="S01-run-01",
        round_number=1,
        character_id="mara",
        disposition="ACCEPT",
    )
    row = store.connection.execute(
        "SELECT accepted_sequence, caused_by_turn_id, accepted_at FROM turns "
        "WHERE turn_id = 'new-actor'"
    ).fetchone()
    assert sequence == 2
    assert row["accepted_sequence"] == 2
    assert row["caused_by_turn_id"] == "legacy-stage"
    assert row["accepted_at"] is not None


def test_roots_reject_overlap_and_path_escape(tmp_path):
    roots = DataRoots.from_root(tmp_path / "data")
    assert roots.path("private", "seasons/S01/season.md").parent.name == "S01"
    with pytest.raises(PathBoundaryError):
        roots.path("public", "../private/leak.md")
    with pytest.raises(PathBoundaryError):
        DataRoots(root=roots.root, state=roots.state, private=roots.public, public=roots.public).validate()


def test_natural_keys_and_optimistic_versions_are_enforced(tmp_path):
    store = _store(tmp_path)
    seasons = SeasonRepository(store)
    season = Season(season_id="S01", season_number=1)
    seasons.create(season)
    with pytest.raises(RepositoryConflict):
        seasons.create(season)
    newer = season.model_copy(update={"version": 1})
    seasons.update(newer, expected_version=0)
    with pytest.raises(RepositoryConflict):
        seasons.update(newer.model_copy(update={"version": 2}), expected_version=0)

    schedule = ScheduleRepository(store)
    schedule.add(_slot())
    with pytest.raises(RepositoryConflict):
        schedule.add(_slot())
    records = RecordRepository(store)
    records.insert_run(run_id="S01-run-01", season_id="S01", slot_id="S01-run-01", status="SCHEDULED")
    with pytest.raises(RepositoryConflict):
        records.insert_run(run_id="S01-run-duplicate", season_id="S01", slot_id="S01-run-01", status="SCHEDULED")
    records.insert_turn(
        turn_id="turn-1",
        run_id="S01-run-01",
        round_number=1,
        character_id="mara",
        disposition="ACCEPT",
    )
    with pytest.raises(RepositoryConflict):
        records.insert_turn(
            turn_id="turn-duplicate",
            run_id="S01-run-01",
            round_number=1,
            character_id="mara",
            disposition="ACCEPT",
        )
    records.insert_diary(
        Diary(
            diary_id="S01-d1-mara",
            season_id="S01",
            character_id="mara",
            day_number=1,
            status=DiaryStatus.WRITTEN,
        )
    )
    with pytest.raises(RepositoryConflict):
        records.insert_diary(
            Diary(
                diary_id="S01-d1-mara-duplicate",
                season_id="S01",
                character_id="mara",
                day_number=1,
            )
        )
    publication = Publication(
        publication_id="publication-1", season_id="S01", version=1
    )
    records.insert_publication(publication)
    with pytest.raises(RepositoryConflict):
        records.insert_publication(publication.model_copy(update={"publication_id": "publication-duplicate"}))
    store.close()


def test_database_rejects_a_second_active_season_transactionally(tmp_path):
    store = _store(tmp_path)
    seasons = SeasonRepository(store)
    seasons.create(Season(season_id="S01", season_number=1, status="ARMED"))
    with pytest.raises(RepositoryConflict):
        seasons.create(Season(season_id="S02", season_number=2, status="RUNNING"))
    store.close()


def test_event_work_and_outbox_keys_are_idempotent(tmp_path):
    store = _store(tmp_path)
    events = EventRepository(store)
    event = dict(
        event_id="evt-1",
        natural_key="turn:S01-run-01:1",
        aggregate_type="run",
        aggregate_id="S01-run-01",
        event_type="TurnAccepted",
        payload={"character_id": "mara"},
    )
    assert events.append(**event)
    assert not events.append(**{**event, "event_id": "evt-duplicate"})
    queue = WorkQueue(store)
    work = dict(
        work_id="work-1",
        natural_key="run:S01-run-01",
        kind="RUN_SCENE",
        payload={"run_id": "S01-run-01"},
        available_at="2026-08-21T06:00:00+00:00",
    )
    assert queue.enqueue(**work)
    assert not queue.enqueue(**{**work, "work_id": "work-duplicate"})
    outbox = ArtifactOutboxRepository(store)
    item = dict(
        outbox_id="artifact-1",
        artifact_key="private:S01/run-01.md",
        visibility="private",
        relative_path="seasons/S01/run-01.md",
        content="# Run 1\n",
    )
    assert outbox.enqueue(**item)
    assert not outbox.enqueue(**{**item, "outbox_id": "artifact-duplicate"})
    store.close()


def test_model_call_attempts_are_immutable_and_finish_with_normalized_metadata(tmp_path):
    store = _store(tmp_path)
    calls = ModelCallRepository(store)
    calls.create(
        call_id="call-1",
        run_id=None,
        purpose="actor_turn",
        attempt=1,
        status="STREAMING",
        backend="fake",
        model="candidate-8b",
        started_at="2026-08-21T06:00:00+00:00",
        prompt_path="audit/prompt.md",
        prompt_sha256="prompt-hash",
    )
    with pytest.raises(RepositoryConflict):
        calls.create(
            call_id="call-duplicate",
            run_id=None,
            purpose="actor_turn",
            attempt=1,
            status="STREAMING",
        )
    calls.finish(
        call_id="call-1",
        status="FAILED",
        ended_at="2026-08-21T06:00:01+00:00",
        latency_ms=1000,
        output_path="audit/output.partial.md",
        output_sha256="output-hash",
        error_type="TimeoutError",
        usage_json='{"total_tokens":12}',
    )
    row = calls.get("call-1")
    assert row["status"] == "FAILED"
    assert row["output_path"].endswith("partial.md")
    assert row["error_type"] == "TimeoutError"
    assert row["usage_json"] == '{"total_tokens":12}'
    store.close()


def test_expired_work_leases_are_reclaimable_after_restart(tmp_path):
    store = _store(tmp_path)
    queue = WorkQueue(store)
    queue.enqueue(
        work_id="work-expiring",
        natural_key="run:expiring",
        kind="RUN_SCENE",
        payload={"run_id": "S01-run-01"},
        available_at="2026-08-21T06:00:00+00:00",
    )

    first = queue.claim_due(
        worker_id="worker-a",
        now="2026-08-21T06:00:00+00:00",
        lease_until="2026-08-21T06:05:00+00:00",
    )
    assert first is not None
    assert first["lease_owner"] == "worker-a"

    reclaimed = queue.claim_due(
        worker_id="worker-b",
        now="2026-08-21T06:06:00+00:00",
        lease_until="2026-08-21T06:11:00+00:00",
    )
    assert reclaimed is not None
    assert reclaimed["lease_owner"] == "worker-b"
    assert reclaimed["attempts"] == 2
    store.close()


def test_completed_work_can_be_reopened_only_by_explicit_manual_resume(tmp_path):
    store = _store(tmp_path)
    queue = WorkQueue(store)
    queue.enqueue(
        work_id="work-manual-resume",
        natural_key="run:manual-resume",
        kind="RUN_SCENE",
        payload={"run_id": "S01-run-01"},
        available_at="2026-08-21T06:00:00+00:00",
    )
    claimed = queue.claim_due(
        worker_id="worker-a",
        now="2026-08-21T06:00:00+00:00",
        lease_until="2026-08-21T06:05:00+00:00",
    )
    assert claimed is not None
    assert queue.complete(work_id="work-manual-resume", worker_id="worker-a")
    assert queue.requeue_completed_for_manual_resume(
        work_id="work-manual-resume",
        available_at="2026-08-21T06:10:00+00:00",
    )
    row = store.connection.execute(
        "SELECT status, available_at, completed_at FROM work_items WHERE work_id = 'work-manual-resume'"
    ).fetchone()
    assert tuple(row) == ("QUEUED", "2026-08-21T06:10:00+00:00", None)
    assert not queue.requeue_completed_for_manual_resume(
        work_id="work-manual-resume",
        available_at="2026-08-21T06:10:00+00:00",
    )
    store.close()


def test_committed_outbox_projects_once_and_records_hash_metadata(tmp_path):
    store = _store(tmp_path)
    roots = DataRoots.from_root(tmp_path / "data")
    outbox = ArtifactOutboxRepository(store)
    outbox.enqueue(
        outbox_id="artifact-1",
        artifact_key="private:S01/run-01.md",
        visibility="private",
        relative_path="seasons/S01/run-01.md",
        content="# Run 1\n",
    )
    projector = ArtifactProjector(roots, outbox)
    assert projector.project_pending() == 1
    assert projector.project_pending() == 0
    row = store.connection.execute(
        "SELECT status, projected_path, sha256, byte_length FROM artifact_outbox WHERE outbox_id = ?",
        ("artifact-1",),
    ).fetchone()
    assert row["status"] == "PROJECTED"
    assert row["projected_path"].endswith("private/seasons/S01/run-01.md")
    assert row["byte_length"] == len("# Run 1\n".encode())
    store.close()


def test_projector_is_repeatable_and_never_overwrites_immutable_artifact(tmp_path):
    roots = DataRoots.from_root(tmp_path / "data")
    projector = ArtifactProjector(roots, object())
    path = projector.project_file(
        visibility="private", relative_path="seasons/S01/run.md", content="# Run\n"
    )
    assert projector.project_file(
        visibility="private", relative_path="seasons/S01/run.md", content="# Run\n"
    ) == path
    with pytest.raises(ArtifactProjectionError):
        projector.project_file(
            visibility="private", relative_path="seasons/S01/run.md", content="# Changed\n"
        )
    assert open(path, encoding="utf-8").read() == "# Run\n"
