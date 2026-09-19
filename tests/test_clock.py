from datetime import datetime, timedelta, timezone

import pytest

from improv_troupe.clock import Clock, VirtualClock


def test_virtual_clock_is_injected_and_advances_without_waiting():
    clock = VirtualClock(datetime(2026, 1, 1, 12, tzinfo=timezone.utc))
    assert isinstance(clock, Clock)
    assert clock.now().hour == 12
    assert clock.advance(timedelta(hours=3)).hour == 15


def test_virtual_clock_rejects_naive_or_backwards_time():
    with pytest.raises(ValueError):
        VirtualClock(datetime(2026, 1, 1, 12))
    clock = VirtualClock(datetime(2026, 1, 1, 12, tzinfo=timezone.utc))
    with pytest.raises(ValueError):
        clock.advance(timedelta(seconds=-1))
