"""Deterministic Gate 3 work-dispatch harness.

This intentionally executes queue items as no-op work. It proves durable
claim/complete behavior without pretending that scenes or model calls exist
before their later implementation gates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta, timezone
from typing import Any

from ..clock import Clock
from ..infrastructure import SQLiteDatabase, WorkQueue


@dataclass
class FakeWorkflowWorker:
    """Claim due work once and complete it deterministically."""

    database: SQLiteDatabase
    clock: Clock
    worker_id: str = "fake-worker"
    completed: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.queue = WorkQueue(self.database)

    def drain_due(self, *, limit: int | None = None) -> int:
        count = 0
        while limit is None or count < limit:
            now = self.clock.now().astimezone(timezone.utc)
            row = self.queue.claim_due(
                worker_id=self.worker_id,
                now=now.isoformat(),
                lease_until=(now + timedelta(minutes=5)).isoformat(),
            )
            if row is None:
                break
            if not self.queue.complete(work_id=row["work_id"], worker_id=self.worker_id):
                raise RuntimeError(f"fake worker lost lease for {row['work_id']}")
            self.completed.append(dict(row))
            count += 1
        return count
