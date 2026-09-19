"""Clock protocols used by scheduling and deterministic workflow tests.

Production code can use :class:`SystemClock`; workflow tests should use
:class:`VirtualClock` so no test needs to wait for wall-clock time.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Minimal clock boundary for application services."""

    def now(self) -> datetime:
        """Return the current timezone-aware instant."""


class SystemClock:
    """Read the current UTC time from the system clock."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class VirtualClock:
    """A manually advanced, deterministic clock for tests and simulations."""

    def __init__(self, current: datetime):
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("VirtualClock requires a timezone-aware datetime")
        self._current = current

    def now(self) -> datetime:
        return self._current

    def set(self, current: datetime) -> None:
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("VirtualClock requires a timezone-aware datetime")
        self._current = current

    def advance(self, amount: timedelta) -> datetime:
        if amount.total_seconds() < 0:
            raise ValueError("VirtualClock cannot move backwards")
        self._current += amount
        return self._current
