import sqlite3
from datetime import datetime

import pytest

from improv_troupe.domain import CastMember, OpeningSnapshot, Season, SeasonStatus, arm_season, transition_season
from improv_troupe.infrastructure import (
    DataRoots,
    OptimisticConcurrencyError,
    PathConfigurationError,
    SQLiteDatabase,
    SeasonRepository,
    safe_path,
)


def test_data_roots_are_siblings_and_safe_paths_cannot_escape(tmp_path):
    roots = DataRoots.from_root(tmp_path / "data")
    assert roots.state.name == "state"
    assert roots.private.name == "private"
    assert roots.public.name == "public"
    assert safe_path(roots.private, "seasons/S01/season.md") == (
        roots.private / "seasons/S01/season.md"
    )
    with pytest.raises(PathConfigurationError):
        safe_path(roots.private, "../public/leak.md")
    with pytest.raises(PathConfigurationError):
        DataRoots(
            root=roots.root,
            state=roots.state,
            private=roots.public,
            public=roots.public,
        ).validate()


def test_sqlite_migration_is_idempotent_and_enables_wal_and_foreign_keys(tmp_path):
    database = SQLiteDatabase(tmp_path / "state" / "improv.sqlite3")
    database.migrate()
    database.migrate()

    connection = database.connect()
    try:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 6
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"seasons", "schedule_slots", "runs", "diaries", "domain_events", "artifact_outbox"} <= tables
    finally:
        connection.close()


def test_sqlite_rejects_a_second_nonterminal_season(tmp_path):
    database = SQLiteDatabase(tmp_path / "improv.sqlite3")
    database.migrate()
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO seasons(season_id, season_number, status, payload_json, created_at, updated_at) "
            "VALUES ('S01', 1, 'RUNNING', '{}', 'now', 'now')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO seasons(season_id, season_number, status, payload_json, created_at, updated_at) "
                "VALUES ('S02', 2, 'DRAFT', '{}', 'now', 'now')"
            )


def test_sqlite_natural_keys_protect_duplicate_slots_and_outbox_artifacts(tmp_path):
    database = SQLiteDatabase(tmp_path / "improv.sqlite3")
    database.migrate()
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO seasons(season_id, season_number, status, payload_json, created_at, updated_at) "
            "VALUES ('S01', 1, 'SEASON_COMPLETE', '{}', 'now', 'now')"
        )
        connection.execute(
            "INSERT INTO schedule_slots(slot_id, season_id, day_number, slot_number, run_number, "
            "scheduled_local, scheduled_utc, utc_offset) "
            "VALUES ('S01-run-01', 'S01', 1, 1, 1, 'local', 'utc', '-07:00')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO schedule_slots(slot_id, season_id, day_number, slot_number, run_number, "
                "scheduled_local, scheduled_utc, utc_offset) "
                "VALUES ('duplicate', 'S01', 1, 1, 2, 'local', 'utc', '-07:00')"
            )
        connection.execute(
            "INSERT INTO artifact_outbox(outbox_id, artifact_key, visibility, relative_path, content, created_at) "
            "VALUES ('artifact-1', 'S01/season.md', 'private', 'S01/season.md', '# Season', 'now')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO artifact_outbox(outbox_id, artifact_key, visibility, relative_path, content, created_at) "
                "VALUES ('artifact-2', 'S01/season.md', 'private', 'S01/season.md', '# Duplicate', 'now')"
            )


def test_season_repository_survives_reopen_and_checks_optimistic_versions(tmp_path):
    database = SQLiteDatabase(tmp_path / "improv.sqlite3")
    database.migrate()
    repository = SeasonRepository(database)
    draft = Season(season_id="S01", season_number=1)
    repository.create(draft)

    awaiting_green = transition_season(draft, SeasonStatus.AWAITING_GREEN).model_copy(
        update={"preflight_passed": True}
    )
    repository.save(awaiting_green, expected_version=0)

    opening = OpeningSnapshot(
        set="The Observatory",
        setting="A remote orbital station",
        cast=["MARA", "JONAS"],
        world_rules=["Promises persist."],
    )
    armed = arm_season(
        awaiting_green,
        green_at=datetime.fromisoformat("2026-08-20T07:00:00-07:00"),
        opening=opening,
        cast=[CastMember(character_id="mara", name="MARA"), CastMember(character_id="jonas", name="JONAS")],
    )
    repository.save(armed, expected_version=1)

    reopened = SeasonRepository(tmp_path / "improv.sqlite3").get("S01")
    assert reopened.status is SeasonStatus.ARMED
    assert len(reopened.schedule) == 21
    assert [member.name for member in reopened.cast] == ["MARA", "JONAS"]

    with pytest.raises(OptimisticConcurrencyError):
        repository.save(armed.model_copy(update={"status": SeasonStatus.RUNNING, "version": 2}), expected_version=1)
