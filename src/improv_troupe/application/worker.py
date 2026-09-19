"""Sequential durable queue worker for production scene services."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta, timezone
from typing import Awaitable, Callable, Mapping

from ..clock import Clock
from ..domain import SeasonStatus, format_delay, transition_season
from ..infrastructure import RecordRepository, SQLiteDatabase, SeasonRepository, WorkQueue
from .recovery import RecoveryTimerService
from .scene_runner import SceneRunError, SceneRunner


@dataclass(frozen=True)
class WorkResult:
    work_id: str
    kind: str
    status: str
    run_id: str | None = None
    reason: str | None = None


@dataclass
class DurableWorkflowWorker:
    """Claim one item at a time and never run a later scene before an earlier one."""

    database: SQLiteDatabase
    clock: Clock
    scene_factory: Callable[[Mapping[str, object]], SceneRunner]
    worker_id: str = "improv-worker"
    lease_duration: timedelta = timedelta(minutes=5)
    retry_delay: timedelta = timedelta(minutes=1)
    recovery: RecoveryTimerService | None = None
    auto_retry_timeouts: bool = False
    timeout_retry_max_attempts: int = 3
    retry_non_transport_failures: bool = True
    post_scene: Callable[[Mapping[str, object], object, object], Awaitable[None]] | None = None
    close_day: Callable[[Mapping[str, object]], Awaitable[None]] | None = None
    queue: WorkQueue = field(init=False)
    records: RecordRepository = field(init=False)
    seasons: SeasonRepository = field(init=False)
    results: list[WorkResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.lease_duration.total_seconds() <= 0:
            raise ValueError("lease_duration must be positive")
        if self.retry_delay.total_seconds() <= 0:
            raise ValueError("retry_delay must be positive")
        if self.timeout_retry_max_attempts < 1:
            raise ValueError("timeout_retry_max_attempts must be positive")
        self.queue = WorkQueue(self.database)
        self.records = RecordRepository(self.database)
        self.seasons = SeasonRepository(self.database)

    async def drain_due(self, *, limit: int | None = None) -> int:
        """Process due work serially; return the number of claimed items."""
        if self.recovery is not None:
            self.recovery.poll(now=self.clock.now())
        processed = 0
        while limit is None or processed < limit:
            now = self.clock.now().astimezone(timezone.utc)
            row = self.queue.claim_due(
                worker_id=self.worker_id,
                now=now.isoformat(),
                lease_until=(now + self.lease_duration).isoformat(),
            )
            if row is None:
                break
            processed += 1
            result = await self._process(row, now)
            self.results.append(result)
            if result.status == "BLOCKED_BY_EARLIER_RUN":
                break
        return processed

    async def _process(self, row, now) -> WorkResult:
        kind = str(row["kind"])
        payload = json.loads(row["payload_json"])
        if kind == "CLOSE_DAY" and self.close_day is not None:
            await self.close_day(payload)
            self.queue.complete(work_id=row["work_id"], worker_id=self.worker_id)
            return WorkResult(str(row["work_id"]), kind, "COMPLETED")
        if kind != "RUN_SCENE":
            self.queue.complete(work_id=row["work_id"], worker_id=self.worker_id)
            return WorkResult(str(row["work_id"]), kind, "COMPLETED")
        run_id = str(payload["run_id"])
        run = self.records.get_run(run_id)
        if run is None:
            self.queue.complete(work_id=row["work_id"], worker_id=self.worker_id)
            return WorkResult(str(row["work_id"]), kind, "SKIPPED", run_id, "unknown_run")
        if str(run["status"]) == "SKIPPED":
            self.queue.complete(work_id=row["work_id"], worker_id=self.worker_id)
            return WorkResult(str(row["work_id"]), kind, "SKIPPED", run_id, "already_skipped")
        if str(run["status"]) in {"WAITING_FOR_MODEL", "RECOVERY_REQUIRED"}:
            self.queue.complete(work_id=row["work_id"], worker_id=self.worker_id)
            return WorkResult(
                str(row["work_id"]), kind, str(run["status"]), run_id, "recovery_pending"
            )
        if self._earlier_run_unresolved(run):
            self.queue.release(
                work_id=row["work_id"],
                worker_id=self.worker_id,
                available_at=(now + self.retry_delay).isoformat(),
            )
            return WorkResult(
                str(row["work_id"]),
                kind,
                "BLOCKED_BY_EARLIER_RUN",
                run_id,
            )
        if str(run["status"]) != "COMPLETED":
            self._ensure_season_running(str(run["season_id"]))
            slot = self.database.connection.execute(
                "SELECT scheduled_utc FROM schedule_slots WHERE slot_id = ?",
                (run["slot_id"],),
            ).fetchone()
            if slot is None:
                self.queue.complete(work_id=row["work_id"], worker_id=self.worker_id)
                return WorkResult(str(row["work_id"]), kind, "SKIPPED", run_id, "unknown_slot")
            scheduled = _parse_timestamp(slot["scheduled_utc"])
            self.records.mark_run_started(
                run_id=run_id,
                started_at=now.isoformat(),
                delay=format_delay(now - scheduled),
                expected_status=str(run["status"]),
            )
        try:
            scene = self.scene_factory(payload)
            scene_result = await scene.execute()
        except SceneRunError as exc:
            if (
                exc.is_transport_timeout
                and self.auto_retry_timeouts
                and int(row["attempts"]) < self.timeout_retry_max_attempts
            ):
                current = self.records.get_run(run_id)
                if current is not None and str(current["status"]) == "RUNNING":
                    self.records.update_run_status(
                        run_id=run_id,
                        status="INTERRUPTED",
                        completion_reason=exc.reason,
                        expected_status="RUNNING",
                    )
                self.queue.release(
                    work_id=row["work_id"],
                    worker_id=self.worker_id,
                    available_at=(now + self.retry_delay).isoformat(),
                )
                return WorkResult(
                    str(row["work_id"]),
                    kind,
                    "AUTO_RETRY_TIMEOUT",
                    run_id,
                    exc.reason,
                )
            if self.recovery is not None:
                self.recovery.begin_waiting(
                    season_id=str(payload["season_id"]),
                    run_id=run_id,
                    reason=exc.reason,
                )
                self.queue.complete(work_id=row["work_id"], worker_id=self.worker_id)
                return WorkResult(
                    str(row["work_id"]), kind, "WAITING_FOR_MODEL", run_id, exc.reason
                )
            if not self.retry_non_transport_failures:
                current = self.records.get_run(run_id)
                if current is not None and str(current["status"]) == "RUNNING":
                    self.records.update_run_status(
                        run_id=run_id,
                        status="INTERRUPTED",
                        completion_reason=exc.reason,
                        expected_status="RUNNING",
                    )
                self.queue.complete(work_id=row["work_id"], worker_id=self.worker_id)
                return WorkResult(
                    str(row["work_id"]), kind, "REJECTED_FAILURE", run_id, exc.reason
                )
            self.queue.release(
                work_id=row["work_id"],
                worker_id=self.worker_id,
                available_at=(now + self.retry_delay).isoformat(),
            )
            return WorkResult(str(row["work_id"]), kind, "RETRYABLE_FAILURE", run_id, exc.reason)
        if self.records.get_run(run_id)["status"] == "COMPLETED":
            self.records.mark_run_completed(
                run_id=run_id,
                completed_at=self.clock.now().astimezone(timezone.utc).isoformat(),
            )
        if self.post_scene is not None:
            await self.post_scene(payload, scene, scene_result)
        self.queue.complete(work_id=row["work_id"], worker_id=self.worker_id)
        return WorkResult(str(row["work_id"]), kind, "COMPLETED", run_id, scene_result.reason)

    def _earlier_run_unresolved(self, run) -> bool:
        current = self.database.connection.execute(
            "SELECT run_number, day_number FROM schedule_slots WHERE slot_id = ?",
            (run["slot_id"],),
        ).fetchone()
        if current is None:
            return False
        row = self.database.connection.execute(
            "SELECT COUNT(*) FROM runs r JOIN schedule_slots s ON s.slot_id = r.slot_id "
            "WHERE r.season_id = ? AND s.run_number < ? "
            "AND r.status NOT IN ('COMPLETED', 'SKIPPED')",
            (run["season_id"], current["run_number"]),
        ).fetchone()
        if int(row[0]) > 0:
            return True
        unclosed_day = self.database.connection.execute(
            "SELECT COUNT(*) FROM days WHERE season_id = ? AND day_number < ? AND closed = 0",
            (run["season_id"], current["day_number"]),
        ).fetchone()
        return int(unclosed_day[0]) > 0

    def _ensure_season_running(self, season_id: str) -> None:
        """Promote an armed season when its first due scene actually starts."""
        season = self.seasons.get(season_id)
        if season.status is not SeasonStatus.ARMED:
            return
        running = transition_season(season, SeasonStatus.RUNNING)
        self.seasons.update(running, expected_version=season.version)


def _parse_timestamp(value: str):
    from datetime import datetime

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


__all__ = ["DurableWorkflowWorker", "WorkResult"]
