"""Always-on service lifecycle and operator status for the Linux host.

The service is intentionally independent of Proxmox.  A VM or LXC container
can run the same process as long as its configured data root is persistent.
SQLite remains the operational source of truth; the dashboard is not required
for scheduling, catch-up, or recovery polling.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping

from ..clock import Clock, SystemClock
from ..engine.transcript import Transcript
from ..infrastructure import (
    ArtifactOutboxRepository,
    ArtifactProjector,
    DataRoots,
    RecordRepository,
    SQLiteDatabase,
)
from .recovery import (
    RecoveryTimerResult,
    RecoveryTimerService,
    WAITING_FOR_MODEL_WINDOW,
)
from .scene_runner import SceneRunError, SceneRunResult
from .worker import DurableWorkflowWorker, WorkResult


class ServiceStartupError(RuntimeError):
    """Raised when the service cannot safely start with its configured state."""


@dataclass(frozen=True)
class ServicePaths:
    """Persistent paths used by one service instance."""

    data_root: Path
    roots: DataRoots
    database_path: Path

    @classmethod
    def from_root(cls, root: str | Path) -> "ServicePaths":
        roots = DataRoots.from_root(root)
        return cls(
            data_root=roots.root,
            roots=roots,
            database_path=roots.state / "improv.sqlite3",
        )

    def prepare(self) -> None:
        """Create the private/state/public siblings with safe permissions."""
        self.roots.prepare()


@dataclass(frozen=True)
class ServiceCycleResult:
    """Observable work performed during one service poll."""

    projected_artifacts: int
    promoted_recoveries: tuple[RecoveryTimerResult, ...]
    processed_items: int
    results: tuple[WorkResult, ...]


@dataclass
class LinuxService:
    """Run the durable worker independently of the dashboard connection."""

    paths: ServicePaths
    database: SQLiteDatabase
    worker: DurableWorkflowWorker
    clock: Clock = field(default_factory=SystemClock)
    poll_interval_seconds: float = 5.0
    _started: bool = field(default=False, init=False, repr=False)
    projector: ArtifactProjector = field(init=False)

    def __post_init__(self) -> None:
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self.projector = ArtifactProjector(
            self.paths.roots,
            ArtifactOutboxRepository(self.database),
        )

    def startup(self) -> None:
        """Prepare storage, apply migrations, and fail closed on corruption."""
        self.paths.prepare()
        self.database.migrate()
        integrity = self.database.connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ServiceStartupError(f"SQLite integrity check failed: {integrity}")
        self._started = True

    async def run_once(self, *, limit: int | None = None) -> ServiceCycleResult:
        """Project committed files, poll recovery, and drain due work once."""
        if not self._started:
            self.startup()
        projected = self.projector.project_pending()
        promoted: list[RecoveryTimerResult] = []
        if self.worker.recovery is not None:
            promoted = self.worker.recovery.poll(now=self.clock.now())
        before = len(self.worker.results)
        processed = await self.worker.drain_due(limit=limit)
        return ServiceCycleResult(
            projected_artifacts=projected,
            promoted_recoveries=tuple(promoted),
            processed_items=processed,
            results=tuple(self.worker.results[before:]),
        )

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        """Poll until asked to stop; systemd can restart after an unexpected error."""
        if not self._started:
            self.startup()
        stop = stop_event or asyncio.Event()
        while not stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.poll_interval_seconds)
            except asyncio.TimeoutError:
                pass


def build_linux_service(
    *,
    paths: ServicePaths,
    scene_factory: Callable[[Mapping[str, object]], object],
    database: SQLiteDatabase | None = None,
    clock: Clock | None = None,
    worker_id: str = "improv-worker",
    poll_interval_seconds: float = 5.0,
    recovery_wait_window: timedelta = WAITING_FOR_MODEL_WINDOW,
    auto_retry_timeouts: bool = False,
    timeout_retry_max_attempts: int = 3,
    post_scene: Callable[[Mapping[str, object], object, object], object] | None = None,
    close_day: Callable[[Mapping[str, object]], object] | None = None,
) -> LinuxService:
    """Construct the service around an injected scene runtime.

    The injection point keeps final actor/orchestrator model selection out of
    the storage/service boundary.  The CLI uses the dry-run factory until the
    live model manifest is selected and wired.
    """
    service_clock = clock or SystemClock()
    database = database or SQLiteDatabase(paths.database_path)
    recovery = RecoveryTimerService(
        database=database,
        clock=service_clock,
        wait_window=recovery_wait_window,
    )
    worker = DurableWorkflowWorker(
        database=database,
        clock=service_clock,
        scene_factory=scene_factory,
        worker_id=worker_id,
        recovery=recovery,
        auto_retry_timeouts=auto_retry_timeouts,
        timeout_retry_max_attempts=timeout_retry_max_attempts,
        post_scene=post_scene,
        close_day=close_day,
    )
    return LinuxService(
        paths=paths,
        database=database,
        worker=worker,
        clock=service_clock,
        poll_interval_seconds=poll_interval_seconds,
    )


def read_service_status(
    database: SQLiteDatabase,
    *,
    paths: ServicePaths | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Return a readable, JSON-safe operational snapshot without story text."""
    current = _utc(now or SystemClock().now())
    connection = database.connection
    schema_row = connection.execute(
        "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
    ).fetchone()
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    seasons = []
    for row in connection.execute(
        "SELECT season_id, season_number, title, status, version, updated_at, payload_json "
        "FROM seasons ORDER BY season_number, season_id"
    ):
        season_id = str(row["season_id"])
        try:
            season_payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError):
            season_payload = {}
        auto_tap_out = bool(season_payload.get("auto_tap_out", True))
        season_run_counts = _count_for_season(connection, "runs", "status", season_id)
        season_diary_counts = _count_for_season(connection, "diaries", "status", season_id)
        cast = [
            {
                "character_id": str(cast_row["character_id"]),
                "name": str(cast_row["name"]),
                "status": str(cast_row["status"]),
                "distress_signal_count": int(cast_row["distress_signal_count"]),
            }
            for cast_row in connection.execute(
                "SELECT character_id, name, status, distress_signal_count "
                "FROM cast_members WHERE season_id = ? ORDER BY character_id",
                (season_id,),
            )
        ]
        next_run = connection.execute(
            "SELECT r.run_id, r.status, r.turn_count, r.delay, s.day_number, "
            "s.slot_number, s.run_number, s.scheduled_local, s.scheduled_utc "
            "FROM runs r JOIN schedule_slots s ON s.slot_id = r.slot_id "
            "WHERE r.season_id = ? AND r.status NOT IN ('COMPLETED', 'SKIPPED') "
            "ORDER BY s.run_number LIMIT 1",
            (season_id,),
        ).fetchone()
        seasons.append(
            {
                "season_id": season_id,
                "season_number": int(row["season_number"]),
                "title": row["title"],
                "status": str(row["status"]),
                "version": int(row["version"]),
                "updated_at": str(row["updated_at"]),
                "wellness_policy": (
                    "AUTOMATIC_TAP_OUT" if auto_tap_out else "MANUAL_REVIEW"
                ),
                "next_run": _run_summary(next_run) if next_run is not None else None,
                "run_counts": season_run_counts,
                "diary_counts": season_diary_counts,
                "cast": cast,
            }
        )

    run_counts = _count_by(connection, "runs", "status")
    work_counts = _count_by(connection, "work_items", "status")
    due_work = connection.execute(
        "SELECT COUNT(*) FROM work_items WHERE status = 'QUEUED' AND available_at <= ?",
        (current.isoformat(),),
    ).fetchone()[0]
    recoveries = []
    for row in connection.execute(
        "SELECT rr.recovery_id, rr.season_id, rr.run_id, rr.status, rr.decision, "
        "rr.created_at, rr.resolved_at, r.status AS run_status, r.delay, "
        "s.scheduled_local, s.scheduled_utc "
        "FROM recovery_requests rr "
        "JOIN runs r ON r.run_id = rr.run_id "
        "JOIN schedule_slots s ON s.slot_id = r.slot_id "
        "WHERE rr.status IN ('WAITING_FOR_MODEL', 'RECOVERY_REQUIRED') "
        "ORDER BY rr.created_at, rr.recovery_id"
    ):
        recoveries.append(
            {
                "recovery_id": str(row["recovery_id"]),
                "season_id": str(row["season_id"]),
                "run_id": str(row["run_id"]),
                "status": str(row["status"]),
                "run_status": str(row["run_status"]),
                "decision": row["decision"],
                "created_at": str(row["created_at"]),
                "resolved_at": row["resolved_at"],
                "delay": row["delay"],
                "scheduled_local": str(row["scheduled_local"]),
                "scheduled_utc": str(row["scheduled_utc"]),
            }
        )

    unread = connection.execute(
        "SELECT COUNT(*) FROM notifications WHERE read_at IS NULL"
    ).fetchone()[0]
    pending_outbox = connection.execute(
        "SELECT COUNT(*) FROM artifact_outbox WHERE status = 'PENDING'"
    ).fetchone()[0]
    publications = [
        {
            "publication_id": str(row["publication_id"]),
            "season_id": str(row["season_id"]),
            "version": int(row["version"]),
            "status": str(row["status"]),
            "eligible_diary_count": len(json.loads(row["eligible_diary_ids_json"])),
            "output_path": row["output_path"],
        }
        for row in connection.execute(
            "SELECT publication_id, season_id, version, status, eligible_diary_ids_json, output_path "
            "FROM publications ORDER BY season_id, version"
        )
    ]
    active = [
        season["season_id"]
        for season in seasons
        if season["status"]
        in {
            "ARMED",
            "RUNNING",
            "PAUSED",
            "RECOVERY_REQUIRED",
            "CLOSING",
        }
    ]
    result: dict[str, object] = {
        "database": str(database.path),
        "schema_version": int(schema_row[0]),
        "integrity": str(integrity),
        "checked_at": current.isoformat(),
        "active_season_ids": active,
        "seasons": seasons,
        "runs": {"total": sum(run_counts.values()), "by_status": run_counts},
        "work": {
            "total": sum(work_counts.values()),
            "by_status": work_counts,
            "due_queued": int(due_work),
        },
        "recoveries": recoveries,
        "notifications": {"unread": int(unread)},
        "artifact_outbox": {"pending": int(pending_outbox)},
        "publications": publications,
    }
    if paths is not None:
        result["data_root"] = str(paths.data_root)
        result["state_root"] = str(paths.roots.state)
        result["private_root"] = str(paths.roots.private)
        result["public_root"] = str(paths.roots.public)
    return result


@dataclass
class DryRunSceneFactory:
    """Infrastructure-only scene factory for accelerated service tests."""

    database: SQLiteDatabase

    def __call__(self, payload: Mapping[str, object]) -> "DryRunScene":
        run_id = str(payload["run_id"])
        return DryRunScene(self.database, run_id)


@dataclass
class DryRunScene:
    database: SQLiteDatabase
    run_id: str

    async def execute(self) -> SceneRunResult:
        records = RecordRepository(self.database)
        run = records.get_run(self.run_id)
        if run is None:
            raise SceneRunError("unknown_run")
        if str(run["status"]) != "COMPLETED":
            records.update_run_status(
                run_id=self.run_id,
                status="COMPLETED",
                completion_reason="service_dry_run",
                expected_status="RUNNING",
            )
        return SceneRunResult(
            reason="service_dry_run",
            turns=0,
            transcript=Transcript(),
        )


def _count_by(connection, table: str, column: str) -> dict[str, int]:
    rows = connection.execute(
        f"SELECT {column}, COUNT(*) AS count FROM {table} GROUP BY {column} ORDER BY {column}"
    ).fetchall()
    return {str(row[0]): int(row[1]) for row in rows}


def _count_for_season(
    connection,
    table: str,
    column: str,
    season_id: str,
) -> dict[str, int]:
    """Count a known operational status column for one season."""
    rows = connection.execute(
        f"SELECT {column}, COUNT(*) AS count FROM {table} "
        "WHERE season_id = ? GROUP BY "
        f"{column} ORDER BY {column}",
        (season_id,),
    ).fetchall()
    return {str(row[0]): int(row[1]) for row in rows}


def _run_summary(row) -> dict[str, object]:
    return {
        "run_id": str(row["run_id"]),
        "status": str(row["status"]),
        "day_number": int(row["day_number"]),
        "slot_number": int(row["slot_number"]),
        "run_number": int(row["run_number"]),
        "turn_count": int(row["turn_count"]),
        "delay": row["delay"],
        "scheduled_local": str(row["scheduled_local"]),
        "scheduled_utc": str(row["scheduled_utc"]),
    }


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


__all__ = [
    "DryRunSceneFactory",
    "LinuxService",
    "ServiceCycleResult",
    "ServicePaths",
    "ServiceStartupError",
    "build_linux_service",
    "read_service_status",
]
