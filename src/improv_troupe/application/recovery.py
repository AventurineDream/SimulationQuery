"""Bounded model-wait recovery before creator-controlled decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..clock import Clock
from ..domain import SeasonStatus, transition_season
from ..infrastructure import EventRepository, RecordRepository, SeasonRepository, SQLiteDatabase


WAITING_FOR_MODEL_WINDOW = timedelta(hours=4)


@dataclass(frozen=True)
class RecoveryTimerResult:
    season_id: str
    run_id: str
    recovery_id: str
    status: str
    available_at: datetime


@dataclass
class RecoveryTimerService:
    """Move model failures through a durable four-hour waiting state."""

    database: SQLiteDatabase
    clock: Clock
    wait_window: timedelta = WAITING_FOR_MODEL_WINDOW
    records: RecordRepository = field(init=False)
    seasons: SeasonRepository = field(init=False)
    events: EventRepository = field(init=False)

    def __post_init__(self) -> None:
        if self.wait_window.total_seconds() < 0:
            raise ValueError("wait_window must be non-negative")
        self.records = RecordRepository(self.database)
        self.seasons = SeasonRepository(self.database)
        self.events = EventRepository(self.database)

    def begin_waiting(self, *, season_id: str, run_id: str, reason: str) -> RecoveryTimerResult:
        """Create one waiting request and make the run explicitly wait for model recovery."""
        now = _utc(self.clock.now())
        existing = self.records.get_recovery(run_id)
        if existing is not None and str(existing["status"]) in {
            "WAITING_FOR_MODEL",
            "RECOVERY_REQUIRED",
        }:
            available = _parse(existing["created_at"]) + self.wait_window
            return RecoveryTimerResult(
                season_id=season_id,
                run_id=run_id,
                recovery_id=str(existing["recovery_id"]),
                status=str(existing["status"]),
                available_at=available,
            )
        count = self.database.connection.execute(
            "SELECT COUNT(*) FROM recovery_requests WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        recovery_id = f"recovery:{season_id}:{run_id}:{int(count) + 1}"
        run = self.records.get_run(run_id)
        if run is None:
            raise ValueError(f"unknown run: {run_id}")
        with self.database.transaction():
            if str(run["status"]) != "WAITING_FOR_MODEL":
                self.records.update_run_status(
                    run_id=run_id,
                    status="WAITING_FOR_MODEL",
                    completion_reason=reason,
                    expected_status=str(run["status"]),
                )
            self.records.insert_recovery(
                recovery_id=recovery_id,
                season_id=season_id,
                run_id=run_id,
                status="WAITING_FOR_MODEL",
                created_at=now.isoformat(),
            )
            self.events.append(
                event_id=f"{recovery_id}:waiting",
                natural_key=f"{recovery_id}:waiting",
                aggregate_type="run",
                aggregate_id=run_id,
                event_type="WaitingForModel",
                payload={
                    "season_id": season_id,
                    "recovery_id": recovery_id,
                    "available_at": (now + self.wait_window).isoformat(),
                    "reason": reason,
                },
            )
            self.records.insert_notification(
                notification_id=f"notification:{recovery_id}:waiting",
                kind="MODEL_WAITING",
                season_id=season_id,
                payload={"run_id": run_id, "available_at": (now + self.wait_window).isoformat()},
            )
        return RecoveryTimerResult(
            season_id=season_id,
            run_id=run_id,
            recovery_id=recovery_id,
            status="WAITING_FOR_MODEL",
            available_at=now + self.wait_window,
        )

    def poll(self, *, now: datetime | None = None) -> list[RecoveryTimerResult]:
        """Promote expired waits to explicit recovery-required state."""
        current = _utc(now or self.clock.now())
        promoted: list[RecoveryTimerResult] = []
        for request in self.records.list_waiting_recovery():
            available = _parse(request["created_at"]) + self.wait_window
            if current < available:
                continue
            run_id = str(request["run_id"])
            run = self.records.get_run(run_id)
            if run is not None and str(run["status"]) == "WAITING_FOR_MODEL":
                self.records.update_run_status(
                    run_id=run_id,
                    status="RECOVERY_REQUIRED",
                    completion_reason="model_wait_expired",
                    expected_status="WAITING_FOR_MODEL",
                )
            season = self.seasons.get(str(request["season_id"]))
            if season.status in {SeasonStatus.ARMED, SeasonStatus.RUNNING}:
                recovering = transition_season(season, SeasonStatus.RECOVERY_REQUIRED)
                self.seasons.update(recovering, expected_version=season.version)
            recovery_id = str(request["recovery_id"])
            self.records.update_recovery(
                recovery_id=recovery_id,
                status="RECOVERY_REQUIRED",
            )
            self.events.append(
                event_id=f"{recovery_id}:required",
                natural_key=f"{recovery_id}:required",
                aggregate_type="run",
                aggregate_id=run_id,
                event_type="RecoveryRequired",
                payload={"recovery_id": recovery_id, "available_at": available.isoformat()},
            )
            self.records.insert_notification(
                notification_id=f"notification:{recovery_id}:required",
                kind="RECOVERY_REQUIRED",
                season_id=str(request["season_id"]),
                payload={"run_id": run_id, "recovery_id": recovery_id},
            )
            promoted.append(
                RecoveryTimerResult(
                    season_id=str(request["season_id"]),
                    run_id=run_id,
                    recovery_id=recovery_id,
                    status="RECOVERY_REQUIRED",
                    available_at=available,
                )
            )
        return promoted


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse(value: str) -> datetime:
    return _utc(datetime.fromisoformat(value))


__all__ = ["RecoveryTimerResult", "RecoveryTimerService", "WAITING_FOR_MODEL_WINDOW"]
