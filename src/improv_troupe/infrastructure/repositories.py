"""Transactional Gate 2 repositories and natural-key boundaries."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..domain import CastMember, Diary, OpeningSnapshot, Publication, Season, ScheduleSlot
from .db import SQLiteDatabase


class RepositoryConflict(RuntimeError):
    """Raised when a natural key or optimistic version has already been used."""


class SeasonRepositoryError(RuntimeError):
    """Base error for durable season persistence."""


class SeasonAlreadyExistsError(SeasonRepositoryError):
    """Raised when a season ID or number is already stored."""


class SeasonNotFoundError(SeasonRepositoryError):
    """Raised when a requested season is not stored."""


class OptimisticConcurrencyError(SeasonRepositoryError):
    """Raised when a save is based on a stale aggregate version."""


def _timestamp(value: datetime | None = None) -> str:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return current.astimezone(timezone.utc).isoformat()


def _stored_timestamp(value: str | None) -> str:
    if value is None:
        return _timestamp()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("accepted_at must be an ISO 8601 timestamp") from exc
    return _timestamp(parsed)


def _status(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _store(value: SQLiteDatabase | str | Path) -> SQLiteDatabase:
    return value if isinstance(value, SQLiteDatabase) else SQLiteDatabase(value)


class SeasonRepository:
    """Persist and reload the season aggregate with optimistic versions."""

    def __init__(self, database: SQLiteDatabase | str | Path):
        self.database = _store(database)

    def create(self, season: Season, *, now: datetime | None = None) -> Season:
        timestamp = _timestamp(now)
        with self.database.transaction() as connection:
            try:
                connection.execute(
                    "INSERT INTO seasons(season_id, season_number, title, status, version, "
                    "payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        season.season_id,
                        season.season_number,
                        season.title,
                        _status(season.status),
                        season.version,
                        season.model_dump_json(),
                        timestamp,
                        timestamp,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise RepositoryConflict(season.season_id) from exc
            self._sync_children(connection, season)
        return season

    def get(self, season_id: str) -> Season:
        connection = self.database.connection
        row = connection.execute(
            "SELECT season_id, season_number, title, status, version, payload_json "
            "FROM seasons WHERE season_id = ?",
            (season_id,),
        ).fetchone()
        if row is None:
            raise SeasonNotFoundError(season_id)
        if row["payload_json"] not in (None, "", "{}"):
            return Season.model_validate_json(row["payload_json"])
        return Season(
            season_id=row["season_id"],
            season_number=row["season_number"],
            title=row["title"],
            status=row["status"],
            version=row["version"],
        )

    def list_all(self) -> list[Season]:
        """Load all season snapshots in stable season-number order."""
        rows = self.database.connection.execute(
            "SELECT season_id FROM seasons ORDER BY season_number, season_id"
        ).fetchall()
        return [self.get(row["season_id"]) for row in rows]

    def update(
        self,
        season: Season,
        *,
        expected_version: int,
        now: datetime | None = None,
    ) -> Season:
        if season.version != expected_version + 1:
            raise RepositoryConflict(
                "season version must be exactly one greater than expected_version"
            )
        timestamp = _timestamp(now)
        with self.database.transaction() as connection:
            result = connection.execute(
                "UPDATE seasons SET title = ?, status = ?, version = ?, payload_json = ?, updated_at = ? "
                "WHERE season_id = ? AND version = ?",
                (
                    season.title,
                    _status(season.status),
                    season.version,
                    season.model_dump_json(),
                    timestamp,
                    season.season_id,
                    expected_version,
                ),
            )
            if result.rowcount != 1:
                exists = connection.execute(
                    "SELECT 1 FROM seasons WHERE season_id = ?", (season.season_id,)
                ).fetchone()
                if exists is None:
                    raise SeasonNotFoundError(season.season_id)
                raise OptimisticConcurrencyError(season.season_id)
            self._sync_children(connection, season)
        return season

    def save(
        self,
        season: Season,
        *,
        expected_version: int,
        now: datetime | None = None,
    ) -> Season:
        """Alias for update used by the newer repository API."""
        return self.update(season, expected_version=expected_version, now=now)

    def record_opening_version(
        self,
        *,
        season_id: str,
        opening: OpeningSnapshot,
        cast: list[CastMember],
        now: datetime | None = None,
    ) -> int:
        """Append one creator-visible opening revision and return its version."""
        timestamp = _timestamp(now)
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM season_opening_versions "
                "WHERE season_id = ?",
                (season_id,),
            ).fetchone()
            version = int(row[0])
            connection.execute(
                """
                INSERT INTO season_opening_versions(
                    season_id, version, set_text, setting, cast_json, world_rules_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    season_id,
                    version,
                    opening.set,
                    opening.setting,
                    json.dumps([member.name for member in cast]),
                    json.dumps(opening.world_rules),
                    timestamp,
                ),
            )
        return version

    @staticmethod
    def _sync_children(connection: sqlite3.Connection, season: Season) -> None:
        for member in season.cast:
            connection.execute(
                """
                INSERT INTO cast_members(
                    season_id, character_id, name, status, role_sheet_version,
                    memory_version, distress_signal_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(season_id, character_id) DO UPDATE SET
                    name = excluded.name,
                    status = excluded.status,
                    role_sheet_version = excluded.role_sheet_version,
                    memory_version = excluded.memory_version,
                    distress_signal_count = excluded.distress_signal_count
                """,
                (
                    season.season_id,
                    member.character_id,
                    member.name,
                    _status(member.status),
                    member.role_sheet_version,
                    member.memory_version,
                    member.distress_signal_count,
                ),
            )
        for slot in season.schedule:
            ScheduleRepository._insert(connection, slot, allow_existing=True)


class ScheduleRepository:
    """Persist immutable schedule slots."""

    def __init__(self, database: SQLiteDatabase | str | Path):
        self.database = _store(database)

    def add(self, slot: ScheduleSlot) -> ScheduleSlot:
        with self.database.transaction() as connection:
            self._insert(connection, slot)
        return slot

    def get(self, slot_id: str) -> sqlite3.Row | None:
        return self.database.connection.execute(
            "SELECT * FROM schedule_slots WHERE slot_id = ?", (slot_id,)
        ).fetchone()

    @staticmethod
    def _insert(
        connection: sqlite3.Connection,
        slot: ScheduleSlot,
        *,
        allow_existing: bool = False,
    ) -> None:
        values = (
            slot.slot_id,
            slot.season_id,
            slot.day_number,
            slot.slot_number,
            slot.run_number,
            slot.scheduled_local.isoformat(),
            slot.scheduled_utc.isoformat(),
            slot.utc_offset,
        )
        existing = connection.execute(
            "SELECT slot_id, season_id, day_number, slot_number, run_number, scheduled_local, "
            "scheduled_utc, utc_offset FROM schedule_slots WHERE slot_id = ?",
            (slot.slot_id,),
        ).fetchone()
        if existing is not None:
            if tuple(existing) != values:
                raise RepositoryConflict(f"immutable schedule slot changed: {slot.slot_id}")
            if allow_existing:
                return
            raise RepositoryConflict(slot.slot_id)
        try:
            connection.execute(
                "INSERT INTO schedule_slots(slot_id, season_id, day_number, slot_number, run_number, "
                "scheduled_local, scheduled_utc, utc_offset) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )
        except sqlite3.IntegrityError as exc:
            raise RepositoryConflict(slot.slot_id) from exc


class RecordRepository:
    """Persist run, turn, diary, and publication natural identities."""

    def __init__(self, database: SQLiteDatabase | str | Path):
        self.database = _store(database)

    def insert_run(self, *, run_id: str, season_id: str, slot_id: str, status: str) -> None:
        self._insert(
            "INSERT INTO runs(run_id, season_id, slot_id, status) VALUES (?, ?, ?, ?)",
            (run_id, season_id, slot_id, status),
        )

    def insert_turn(
        self,
        *,
        turn_id: str,
        run_id: str,
        round_number: int,
        character_id: str,
        disposition: str,
        content_path: str | None = None,
        accepted_sequence: int | None = None,
        caused_by_turn_id: str | None = None,
        accepted_at: str | None = None,
    ) -> int:
        """Insert one accepted story record with durable causal evidence.

        Old databases intentionally keep migrated turn rows null in these
        columns. New records receive a monotonically increasing sequence at
        acceptance time. Actor and neutral records also inherit the accepted
        director beat for their round when one exists.
        """
        accepted_dispositions = {
            "ACCEPT",
            "ACCEPT_AFTER_CORRECTION",
            "NARRATION_ACCEPT",
            "NEUTRAL_INTERRUPTION",
        }
        if disposition not in accepted_dispositions:
            raise ValueError("turns may only contain accepted story dispositions")
        if accepted_sequence is not None and accepted_sequence < 1:
            raise ValueError("accepted_sequence must be positive")

        with self.database.transaction() as connection:
            if accepted_sequence is None:
                row = connection.execute(
                    "SELECT COALESCE(MAX(accepted_sequence), 0) AS maximum, "
                    "COUNT(*) AS accepted_count FROM turns WHERE run_id = ? "
                    "AND disposition IN ('ACCEPT', 'ACCEPT_AFTER_CORRECTION', "
                    "'NARRATION_ACCEPT', 'NEUTRAL_INTERRUPTION')",
                    (run_id,),
                ).fetchone()
                accepted_sequence = max(
                    int(row["maximum"] or 0), int(row["accepted_count"] or 0)
                ) + 1
            if caused_by_turn_id is None and disposition != "NARRATION_ACCEPT":
                parent = connection.execute(
                    "SELECT turn_id FROM turns WHERE run_id = ? AND round_number = ? "
                    "AND disposition = 'NARRATION_ACCEPT' "
                    "ORDER BY accepted_sequence, rowid LIMIT 1",
                    (run_id, round_number),
                ).fetchone()
                if parent is not None:
                    caused_by_turn_id = str(parent["turn_id"])
            accepted_at = _stored_timestamp(accepted_at)
            try:
                connection.execute(
                    "INSERT INTO turns(turn_id, run_id, round_number, character_id, "
                    "disposition, content_path, accepted_sequence, caused_by_turn_id, "
                    "accepted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        turn_id,
                        run_id,
                        round_number,
                        character_id,
                        disposition,
                        content_path,
                        accepted_sequence,
                        caused_by_turn_id,
                        accepted_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise RepositoryConflict(turn_id) from exc
        return accepted_sequence

    def list_turns(self, run_id: str) -> list[sqlite3.Row]:
        return list(
            self.database.connection.execute(
                "SELECT rowid AS insertion_order, * FROM turns WHERE run_id = ? "
                "ORDER BY round_number, insertion_order",
                (run_id,),
            )
        )

    def checkpoint_run(
        self,
        *,
        run_id: str,
        turn_count: int,
        expected_status: str = "RUNNING",
    ) -> None:
        with self.database.transaction() as connection:
            result = connection.execute(
                "UPDATE runs SET turn_count = ?, version = version + 1 "
                "WHERE run_id = ? AND status = ?",
                (turn_count, run_id, expected_status),
            )
            if result.rowcount != 1:
                raise RepositoryConflict(f"run checkpoint rejected: {run_id}")

    def insert_diary(self, diary: Diary) -> None:
        self._insert(
            "INSERT INTO diaries(diary_id, season_id, character_id, day_number, chosen_slot_number, "
            "status, word_count, late, content_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                diary.diary_id,
                diary.season_id,
                diary.character_id,
                diary.day_number,
                diary.chosen_slot_number,
                _status(diary.status),
                diary.word_count,
                int(diary.late),
                diary.content_path,
            ),
        )

    def insert_day(
        self, *, season_id: str, day_number: int, original_date: str
    ) -> None:
        self._insert(
            "INSERT INTO days(season_id, day_number, original_date) VALUES (?, ?, ?)",
            (season_id, day_number, original_date),
        )

    def get_day(self, *, season_id: str, day_number: int) -> sqlite3.Row | None:
        return self.database.connection.execute(
            "SELECT * FROM days WHERE season_id = ? AND day_number = ?",
            (season_id, day_number),
        ).fetchone()

    def update_day(
        self,
        *,
        season_id: str,
        day_number: int,
        cutoff_at: str,
        closed: bool,
    ) -> None:
        with self.database.transaction() as connection:
            result = connection.execute(
                "UPDATE days SET cutoff_at = ?, closed = ? "
                "WHERE season_id = ? AND day_number = ?",
                (cutoff_at, int(closed), season_id, day_number),
            )
            if result.rowcount != 1:
                raise RepositoryConflict(
                    f"unknown day: {season_id}:{day_number}"
                )

    def get_recovery(self, run_id: str) -> sqlite3.Row | None:
        return self.database.connection.execute(
            "SELECT * FROM recovery_requests WHERE run_id = ? "
            "ORDER BY created_at DESC, recovery_id DESC LIMIT 1",
            (run_id,),
        ).fetchone()

    def list_waiting_recovery(self) -> list[sqlite3.Row]:
        return list(
            self.database.connection.execute(
                "SELECT * FROM recovery_requests WHERE status = 'WAITING_FOR_MODEL' "
                "ORDER BY created_at, recovery_id"
            )
        )

    def insert_recovery(
        self,
        *,
        recovery_id: str,
        season_id: str,
        run_id: str,
        status: str,
        created_at: str,
    ) -> None:
        self._insert(
            "INSERT INTO recovery_requests(recovery_id, season_id, run_id, status, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (recovery_id, season_id, run_id, status, created_at),
        )

    def update_recovery(
        self,
        *,
        recovery_id: str,
        status: str,
        decision: str | None = None,
        resolved_at: str | None = None,
        expected_version: int | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            statement = (
                "UPDATE recovery_requests SET status = ?, decision = ?, resolved_at = ?, "
                "version = version + 1 WHERE recovery_id = ?"
            )
            parameters: tuple[object, ...] = (status, decision, resolved_at, recovery_id)
            if expected_version is not None:
                statement += " AND version = ?"
                parameters += (expected_version,)
            result = connection.execute(statement, parameters)
            if result.rowcount != 1:
                raise RepositoryConflict(f"stale or unknown recovery: {recovery_id}")

    def get_diary(
        self, *, season_id: str, character_id: str, day_number: int
    ) -> sqlite3.Row | None:
        return self.database.connection.execute(
            "SELECT * FROM diaries WHERE season_id = ? AND character_id = ? AND day_number = ?",
            (season_id, character_id, day_number),
        ).fetchone()

    def get_diary_by_id(self, diary_id: str) -> sqlite3.Row | None:
        return self.database.connection.execute(
            "SELECT * FROM diaries WHERE diary_id = ?", (diary_id,)
        ).fetchone()

    def get_cast_member(self, *, season_id: str, character_id: str) -> sqlite3.Row | None:
        return self.database.connection.execute(
            "SELECT * FROM cast_members WHERE season_id = ? AND character_id = ?",
            (season_id, character_id),
        ).fetchone()

    def update_cast_wellness(
        self,
        *,
        season_id: str,
        character_id: str,
        status: str,
        distress_signal_count: int,
    ) -> None:
        with self.database.transaction() as connection:
            result = connection.execute(
                "UPDATE cast_members SET status = ?, distress_signal_count = ? "
                "WHERE season_id = ? AND character_id = ?",
                (status, distress_signal_count, season_id, character_id),
            )
            if result.rowcount != 1:
                raise RepositoryConflict(f"unknown cast member: {season_id}:{character_id}")

    def insert_wellness_event(
        self,
        *,
        event_id: str,
        season_id: str,
        character_id: str,
        context: str,
        signal_number: int,
        observed_at: str,
        intervention: str,
    ) -> None:
        self._insert(
            "INSERT INTO wellness_events(event_id, season_id, character_id, context, "
            "signal_number, observed_at, intervention) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                season_id,
                character_id,
                context,
                signal_number,
                observed_at,
                intervention,
            ),
        )

    def insert_notification(
        self,
        *,
        notification_id: str,
        kind: str,
        season_id: str | None,
        payload: dict[str, object],
    ) -> None:
        self._insert(
            "INSERT INTO notifications(notification_id, kind, season_id, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                notification_id,
                kind,
                season_id,
                json.dumps(payload, sort_keys=True),
                _timestamp(),
            ),
        )

    def list_diaries(
        self, *, season_id: str, day_number: int | None = None
    ) -> list[sqlite3.Row]:
        statement = "SELECT * FROM diaries WHERE season_id = ?"
        parameters: tuple[object, ...] = (season_id,)
        if day_number is not None:
            statement += " AND day_number = ?"
            parameters += (day_number,)
        statement += " ORDER BY day_number, character_id"
        return list(self.database.connection.execute(statement, parameters))

    def update_diary(
        self,
        *,
        diary_id: str,
        chosen_slot_number: int | None,
        status: str,
        word_count: int | None,
        late: bool,
        content_path: str | None,
    ) -> None:
        with self.database.transaction() as connection:
            result = connection.execute(
                "UPDATE diaries SET chosen_slot_number = ?, status = ?, word_count = ?, "
                "late = ?, content_path = ? WHERE diary_id = ?",
                (
                    chosen_slot_number,
                    status,
                    word_count,
                    int(late),
                    content_path,
                    diary_id,
                ),
            )
            if result.rowcount != 1:
                raise RepositoryConflict(f"unknown diary: {diary_id}")

    def insert_publication(self, publication: Publication) -> None:
        self._insert(
            "INSERT INTO publications(publication_id, season_id, version, status, "
            "eligible_diary_ids_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                publication.publication_id,
                publication.season_id,
                publication.version,
                _status(publication.status),
                json.dumps(publication.eligible_diary_ids),
                _timestamp(),
            ),
        )

    def get_run(self, run_id: str) -> sqlite3.Row | None:
        return self.database.connection.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()

    def mark_run_started(
        self,
        *,
        run_id: str,
        started_at: str,
        delay: str,
        expected_status: str,
    ) -> None:
        with self.database.transaction() as connection:
            result = connection.execute(
                "UPDATE runs SET status = 'RUNNING', actual_started_at = "
                "COALESCE(actual_started_at, ?), delay = ?, version = version + 1 "
                "WHERE run_id = ? AND status = ?",
                (started_at, delay, run_id, expected_status),
            )
            if result.rowcount != 1:
                raise RepositoryConflict(f"run start rejected: {run_id}")

    def get_publication(self, publication_id: str) -> sqlite3.Row | None:
        return self.database.connection.execute(
            "SELECT * FROM publications WHERE publication_id = ?", (publication_id,)
        ).fetchone()

    def update_publication(
        self,
        *,
        publication_id: str,
        status: str,
        eligible_diary_ids: list[str] | None = None,
        output_path: str | None = None,
        manifest_sha256: str | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            result = connection.execute(
                "UPDATE publications SET status = ?, eligible_diary_ids_json = ?, "
                "output_path = ?, manifest_sha256 = ? WHERE publication_id = ?",
                (
                    status,
                    json.dumps(eligible_diary_ids or []),
                    output_path,
                    manifest_sha256,
                    publication_id,
                ),
            )
            if result.rowcount != 1:
                raise RepositoryConflict(f"unknown publication: {publication_id}")

    def insert_publication_check(
        self,
        *,
        publication_id: str,
        wellness_confirmed: bool,
        privacy_reviewed: bool,
        consent_confirmed: bool,
    ) -> None:
        self._insert(
            "INSERT INTO publication_checks(publication_id, wellness_confirmed, privacy_reviewed, "
            "consent_confirmed, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                publication_id,
                int(wellness_confirmed),
                int(privacy_reviewed),
                int(consent_confirmed),
                _timestamp(),
            ),
        )

    def get_publication_check(self, publication_id: str) -> sqlite3.Row | None:
        return self.database.connection.execute(
            "SELECT * FROM publication_checks WHERE publication_id = ?",
            (publication_id,),
        ).fetchone()

    def upsert_publication_diary_review(
        self,
        *,
        publication_id: str,
        diary_id: str,
        decision: str,
        reason: str | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO publication_diary_reviews(publication_id, diary_id, decision, reason, updated_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(publication_id, diary_id) DO UPDATE SET "
                "decision = excluded.decision, reason = excluded.reason, updated_at = excluded.updated_at",
                (publication_id, diary_id, decision, reason, _timestamp()),
            )

    def list_publication_diary_reviews(self, publication_id: str) -> list[sqlite3.Row]:
        return list(
            self.database.connection.execute(
                "SELECT * FROM publication_diary_reviews WHERE publication_id = ? ORDER BY diary_id",
                (publication_id,),
            )
        )
    def mark_run_completed(
        self,
        *,
        run_id: str,
        completed_at: str,
        expected_status: str = "COMPLETED",
    ) -> None:
        with self.database.transaction() as connection:
            result = connection.execute(
                "UPDATE runs SET actual_completed_at = ?, version = version + 1 "
                "WHERE run_id = ? AND status = ?",
                (completed_at, run_id, expected_status),
            )
            if result.rowcount != 1:
                raise RepositoryConflict(f"run completion rejected: {run_id}")

    def update_run_status(
        self,
        *,
        run_id: str,
        status: str,
        completion_reason: str | None = None,
        expected_status: str | None = None,
    ) -> None:
        try:
            with self.database.transaction() as connection:
                statement = (
                    "UPDATE runs SET status = ?, completion_reason = ?, version = version + 1 "
                    "WHERE run_id = ?"
                )
                parameters: tuple[object, ...] = (status, completion_reason, run_id)
                if expected_status is not None:
                    statement += " AND status = ?"
                    parameters += (expected_status,)
                result = connection.execute(statement, parameters)
                if result.rowcount != 1:
                    if self.get_run(run_id) is None:
                        raise RepositoryConflict(f"unknown run: {run_id}")
                    raise RepositoryConflict(f"unexpected run status for {run_id}")
        except sqlite3.IntegrityError as exc:
            raise RepositoryConflict(str(exc)) from exc

    def _insert(self, statement: str, parameters: tuple[object, ...]) -> None:
        try:
            with self.database.transaction() as connection:
                connection.execute(statement, parameters)
        except sqlite3.IntegrityError as exc:
            raise RepositoryConflict(str(exc)) from exc


class ModelCallRepository:
    """Persist immutable model-call attempts and their normalized dispositions."""

    def __init__(self, database: SQLiteDatabase | str | Path):
        self.database = _store(database)

    def create(
        self,
        *,
        call_id: str,
        run_id: str | None,
        purpose: str,
        attempt: int,
        status: str,
        backend: str | None = None,
        model: str | None = None,
        started_at: str | None = None,
        prompt_path: str | None = None,
        prompt_sha256: str | None = None,
        character_id: str | None = None,
        response_format_mode: str | None = None,
        prompt_version_id: str | None = None,
        schema_version_id: str | None = None,
        context_version_id: str | None = None,
        role_sheet_version_id: str | None = None,
        character_card_version_id: str | None = None,
        correction_of_call_id: str | None = None,
    ) -> None:
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO model_calls(
                        call_id, run_id, purpose, attempt, status, backend, model,
                        started_at, prompt_path, prompt_sha256, character_id,
                        response_format_mode, prompt_version_id, schema_version_id,
                        context_version_id, role_sheet_version_id,
                        character_card_version_id, correction_of_call_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        call_id,
                        run_id,
                        purpose,
                        attempt,
                        status,
                        backend,
                        model,
                        started_at,
                        prompt_path,
                        prompt_sha256,
                        character_id,
                        response_format_mode,
                        prompt_version_id,
                        schema_version_id,
                        context_version_id,
                        role_sheet_version_id,
                        character_card_version_id,
                        correction_of_call_id,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise RepositoryConflict(call_id) from exc

    def next_attempt(self, *, run_id: str | None, purpose: str) -> int:
        """Return the next immutable attempt number for one call purpose."""
        if run_id is None:
            row = self.database.connection.execute(
                "SELECT COALESCE(MAX(attempt), 0) + 1 FROM model_calls "
                "WHERE run_id IS NULL AND purpose = ?",
                (purpose,),
            ).fetchone()
        else:
            row = self.database.connection.execute(
                "SELECT COALESCE(MAX(attempt), 0) + 1 FROM model_calls "
                "WHERE run_id = ? AND purpose = ?",
                (run_id, purpose),
            ).fetchone()
        return int(row[0])

    def finish(
        self,
        *,
        call_id: str,
        status: str,
        ended_at: str,
        latency_ms: int,
        output_path: str | None = None,
        output_sha256: str | None = None,
        finish_reason: str | None = None,
        cancelled: bool = False,
        error_type: str | None = None,
        usage_json: str | None = None,
        response_format_mode: str | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            result = connection.execute(
                "UPDATE model_calls SET status = ?, ended_at = ?, latency_ms = ?, "
                "output_path = ?, output_sha256 = ?, finish_reason = ?, cancelled = ?, "
                "error_type = ?, usage_json = ?, "
                "response_format_mode = COALESCE(?, response_format_mode) WHERE call_id = ?",
                (
                    status,
                    ended_at,
                    latency_ms,
                    output_path,
                    output_sha256,
                    finish_reason,
                    int(cancelled),
                    error_type,
                    usage_json,
                    response_format_mode,
                    call_id,
                ),
            )
            if result.rowcount != 1:
                raise RepositoryConflict(f"unknown model call: {call_id}")

    def get(self, call_id: str) -> sqlite3.Row | None:
        return self.database.connection.execute(
            "SELECT * FROM model_calls WHERE call_id = ?", (call_id,)
        ).fetchone()

    def record_diagnostics(
        self,
        *,
        call_id: str,
        parse_status: str | None = None,
        validation_status: str | None = None,
        acceptance_status: str | None = None,
        render_status: str | None = None,
        parsed_path: str | None = None,
        validated_path: str | None = None,
        accepted_path: str | None = None,
        rendered_path: str | None = None,
        validator_code: str | None = None,
        validator_detail: str | None = None,
        review_turn_id: str | None = None,
    ) -> None:
        """Attach allowlisted downstream evidence to one immutable call attempt."""
        with self.database.transaction() as connection:
            result = connection.execute(
                "UPDATE model_calls SET parse_status = ?, validation_status = ?, "
                "acceptance_status = ?, render_status = ?, parsed_path = ?, "
                "validated_path = ?, accepted_path = ?, rendered_path = ?, "
                "validator_code = ?, validator_detail = ?, review_turn_id = ? "
                "WHERE call_id = ?",
                (
                    parse_status,
                    validation_status,
                    acceptance_status,
                    render_status,
                    parsed_path,
                    validated_path,
                    accepted_path,
                    rendered_path,
                    validator_code,
                    validator_detail,
                    review_turn_id,
                    call_id,
                ),
            )
            if result.rowcount != 1:
                raise RepositoryConflict(f"unknown model call: {call_id}")


class EventRepository:
    """Append immutable domain events by natural key."""

    def __init__(self, database: SQLiteDatabase | str | Path):
        self.database = _store(database)

    def append(
        self,
        *,
        event_id: str,
        natural_key: str,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO domain_events(event_id, natural_key, aggregate_type, "
                "aggregate_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    natural_key,
                    aggregate_type,
                    aggregate_id,
                    event_type,
                    json.dumps(payload, sort_keys=True),
                    _timestamp(),
                ),
            )
            return cursor.rowcount == 1

    def list_for_aggregate(self, aggregate_id: str) -> list[sqlite3.Row]:
        """Load an aggregate's immutable events in creation order."""
        return list(
            self.database.connection.execute(
                "SELECT * FROM domain_events WHERE aggregate_id = ? "
                "ORDER BY created_at, event_id",
                (aggregate_id,),
            )
        )


class CommandRequestRepository:
    """Store a request fingerprint and response for exact replay semantics."""

    def __init__(self, database: SQLiteDatabase | str | Path):
        self.database = _store(database)

    def get(self, request_id: str) -> sqlite3.Row | None:
        return self.database.connection.execute(
            "SELECT request_id, command_type, fingerprint, response_json "
            "FROM command_requests WHERE request_id = ?",
            (request_id,),
        ).fetchone()

    def store(
        self,
        *,
        request_id: str,
        command_type: str,
        fingerprint: str,
        response_json: str,
    ) -> None:
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    "INSERT INTO command_requests(request_id, command_type, fingerprint, response_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (request_id, command_type, fingerprint, response_json, _timestamp()),
                )
        except sqlite3.IntegrityError as exc:
            raise RepositoryConflict(request_id) from exc


class WorkQueue:
    """Durable natural-keyed work enqueue boundary."""

    def __init__(self, database: SQLiteDatabase | str | Path):
        self.database = _store(database)

    def enqueue(
        self,
        *,
        work_id: str,
        natural_key: str,
        kind: str,
        payload: dict[str, object],
        available_at: str,
        priority: int = 0,
    ) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO work_items(work_id, natural_key, kind, payload_json, status, "
                "available_at, priority) VALUES (?, ?, ?, ?, 'QUEUED', ?, ?)",
                (
                    work_id,
                    natural_key,
                    kind,
                    json.dumps(payload, sort_keys=True),
                    available_at,
                    priority,
                ),
            )
            return cursor.rowcount == 1

    def claim_due(
        self,
        *,
        worker_id: str,
        now: str,
        lease_until: str,
    ) -> sqlite3.Row | None:
        """Claim one due or expired work item with a durable lease."""
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM work_items WHERE available_at <= ? "
                "AND (status = 'QUEUED' OR (status = 'LEASED' AND lease_until <= ?)) "
                "ORDER BY priority, available_at, work_id LIMIT 1",
                (now, now),
            ).fetchone()
            if row is None:
                return None
            result = connection.execute(
                "UPDATE work_items SET status = 'LEASED', lease_owner = ?, lease_until = ?, "
                "attempts = attempts + 1 WHERE work_id = ? AND "
                "(status = 'QUEUED' OR (status = 'LEASED' AND lease_until <= ?))",
                (worker_id, lease_until, row["work_id"], now),
            )
            if result.rowcount != 1:
                return None
            return connection.execute(
                "SELECT * FROM work_items WHERE work_id = ?", (row["work_id"],)
            ).fetchone()

    def complete(self, *, work_id: str, worker_id: str) -> bool:
        with self.database.transaction() as connection:
            result = connection.execute(
                "UPDATE work_items SET status = 'COMPLETED', completed_at = ?, lease_owner = NULL, "
                "lease_until = NULL WHERE work_id = ? AND status = 'LEASED' AND lease_owner = ?",
                (_timestamp(), work_id, worker_id),
            )
            return result.rowcount == 1

    def release(self, *, work_id: str, worker_id: str, available_at: str) -> bool:
        with self.database.transaction() as connection:
            result = connection.execute(
                "UPDATE work_items SET status = 'QUEUED', available_at = ?, lease_owner = NULL, "
                "lease_until = NULL WHERE work_id = ? AND status = 'LEASED' AND lease_owner = ?",
                (available_at, work_id, worker_id),
            )
            return result.rowcount == 1

    def requeue_completed_for_manual_resume(self, *, work_id: str, available_at: str) -> bool:
        """Reopen one completed work receipt after an explicit operator resume.

        Normal worker failures deliberately complete their queue receipt to
        prevent unattended retries.  A rehearsal's ``--resume`` command is an
        explicit operator action, so it may reopen only that exact completed
        receipt while preserving its earlier attempts and model-call audit.
        """

        with self.database.transaction() as connection:
            result = connection.execute(
                "UPDATE work_items SET status = 'QUEUED', available_at = ?, lease_owner = NULL, "
                "lease_until = NULL, completed_at = NULL WHERE work_id = ? AND status = 'COMPLETED'",
                (available_at, work_id),
            )
            return result.rowcount == 1

    def reclaim_leased_for_manual_resume(self, *, work_id: str, available_at: str) -> bool:
        """Release an abandoned lease after an explicit operator resume."""
        with self.database.transaction() as connection:
            result = connection.execute(
                "UPDATE work_items SET status = 'QUEUED', available_at = ?, lease_owner = NULL, "
                "lease_until = NULL WHERE work_id = ? AND status = 'LEASED'",
                (available_at, work_id),
            )
            return result.rowcount == 1


class ArtifactOutboxRepository:
    """Durable artifact intents consumed by :class:`ArtifactProjector`."""

    def __init__(self, database: SQLiteDatabase | str | Path):
        self.database = _store(database)

    def enqueue(
        self,
        *,
        outbox_id: str,
        artifact_key: str,
        visibility: str,
        relative_path: str,
        content: str | bytes,
        immutable: bool = True,
    ) -> bool:
        raw = content.encode("utf-8") if isinstance(content, str) else content
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO artifact_outbox(outbox_id, artifact_key, visibility, relative_path, "
                "content, immutable, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    outbox_id,
                    artifact_key,
                    visibility,
                    relative_path,
                    raw,
                    int(immutable),
                    _timestamp(),
                ),
            )
            return cursor.rowcount == 1

    def pending(self) -> list[sqlite3.Row]:
        return list(
            self.database.connection.execute(
                "SELECT * FROM artifact_outbox WHERE status = 'PENDING' "
                "ORDER BY created_at, outbox_id"
            )
        )

    def mark_projected(self, outbox_id: str, *, path: str, sha256: str, byte_length: int) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE artifact_outbox SET status = 'PROJECTED', projected_path = ?, sha256 = ?, "
                "byte_length = ?, projected_at = ? WHERE outbox_id = ?",
                (path, sha256, byte_length, _timestamp(), outbox_id),
            )
