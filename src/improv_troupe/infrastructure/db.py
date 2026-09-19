"""SQLite operational state for the durable season workflow."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA_VERSION = 6


def _migration_path(version: int, root: Path | None = None) -> Path:
    """Resolve one numbered migration without assuming its descriptive suffix."""
    if version < 1:
        raise ValueError("migration version must be positive")
    migration_root = root or Path(__file__).parent / "migrations"
    matches = sorted(migration_root.glob(f"{version:03d}_*.sql"))
    if len(matches) != 1:
        raise RuntimeError(
            f"migration {version:03d} requires exactly one packaged SQL file; "
            f"found {len(matches)}"
        )
    return matches[0]


class SQLiteDatabase:
    """A SQLite connection with explicit migration and transaction boundaries."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = self._open()
        self._transaction_depth = 0
        self._nested_transaction_failed = False

    def _open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def connect(self) -> sqlite3.Connection:
        """Open another configured connection for isolated reads or tests."""
        return self._open()

    def migrate(self) -> None:
        """Apply each packaged schema migration exactly once."""
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {
            row[0]
            for row in self.connection.execute("SELECT version FROM schema_migrations")
        }
        for version in range(1, SCHEMA_VERSION + 1):
            if version in applied:
                continue
            migration_path = _migration_path(version)
            self.connection.executescript(migration_path.read_text(encoding="utf-8"))
            self._ensure_compatibility_columns()
            self.connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) "
                "VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
                (version,),
            )
            self.connection.commit()
        self._ensure_compatibility_columns()

    def _ensure_compatibility_columns(self) -> None:
        """Add columns needed by the durable aggregate snapshot if absent."""
        columns = {
            row[1] for row in self.connection.execute("PRAGMA table_info(seasons)")
        }
        if "payload_json" not in columns:
            self.connection.execute(
                "ALTER TABLE seasons ADD COLUMN payload_json TEXT NOT NULL DEFAULT '{}'"
            )
        model_columns = {
            row[1] for row in self.connection.execute("PRAGMA table_info(model_calls)")
        }
        for name, definition in {
            "finish_reason": "TEXT",
            "cancelled": "INTEGER NOT NULL DEFAULT 0",
            "error_type": "TEXT",
            "usage_json": "TEXT",
        }.items():
            if name not in model_columns:
                self.connection.execute(
                    f"ALTER TABLE model_calls ADD COLUMN {name} {definition}"
                )
        work_columns = {
            row[1] for row in self.connection.execute("PRAGMA table_info(work_items)")
        }
        if "priority" not in work_columns:
            self.connection.execute(
                "ALTER TABLE work_items ADD COLUMN priority INTEGER NOT NULL DEFAULT 0"
            )
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS publication_checks (
                publication_id TEXT PRIMARY KEY,
                wellness_confirmed INTEGER NOT NULL DEFAULT 0,
                privacy_reviewed INTEGER NOT NULL DEFAULT 0,
                consent_confirmed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (publication_id) REFERENCES publications(publication_id)
            );
            CREATE TABLE IF NOT EXISTS publication_diary_reviews (
                publication_id TEXT NOT NULL,
                diary_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (publication_id, diary_id),
                FOREIGN KEY (publication_id) REFERENCES publications(publication_id),
                FOREIGN KEY (diary_id) REFERENCES diaries(diary_id)
            );
            """
        )
        self.connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Yield one re-entrant write transaction and roll it back on failure.

        Repositories intentionally own their small transaction boundaries, but
        application commands sometimes need to compose several repositories
        atomically. Nested callers therefore reuse the outer transaction and
        never commit independently. A failure in any nested scope poisons the
        outer transaction even if an intermediate caller catches the original
        exception.
        """
        if self._transaction_depth:
            self._transaction_depth += 1
            try:
                yield self.connection
            except BaseException:
                self._nested_transaction_failed = True
                raise
            finally:
                self._transaction_depth -= 1
            return

        self._transaction_depth = 1
        self._nested_transaction_failed = False
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            yield self.connection
            if self._nested_transaction_failed:
                raise sqlite3.OperationalError("nested transaction failed")
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise
        finally:
            self._transaction_depth = 0
            self._nested_transaction_failed = False

    def close(self) -> None:
        self.connection.close()


# Compatibility name used by the first Gate 2 test harness.
SQLiteStore = SQLiteDatabase
