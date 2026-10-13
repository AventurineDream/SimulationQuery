"""Deterministic and interaction checks for the optional visual sampler."""

from __future__ import annotations

import pytest

pytest.importorskip("textual")

from demos.textual_background_sampler import (  # noqa: E402
    BACKGROUND_SPECS,
    BackgroundCanvas,
    BackgroundSampler,
    render_frame,
)


@pytest.mark.parametrize("mode", BACKGROUND_SPECS)
def test_each_background_renders_a_deterministic_frame(mode: str) -> None:
    first = render_frame(mode, frame=7, width=32, height=8)
    second = render_frame(mode, frame=7, width=32, height=8)

    assert first.plain == second.plain
    assert first.cell_len == 32 * 8
    assert first.plain.count("\n") == 7


def test_unknown_background_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown background mode"):
        render_frame("unknown", frame=0, width=10, height=4)


@pytest.mark.asyncio
async def test_sampler_switches_modes_and_advances_at_a_bounded_rate(monkeypatch) -> None:
    scheduled = []

    def capture_interval(self, interval, callback, **kwargs):
        scheduled.append((interval, callback))

    # Drive the application's timer callback explicitly. Textual key dispatch
    # may take several frames, so elapsed wall time is not a stable assertion.
    monkeypatch.setattr(BackgroundCanvas, "set_interval", capture_interval)
    app = BackgroundSampler()
    async with app.run_test(size=(64, 20)) as pilot:
        assert len(scheduled) == 1
        interval, advance = scheduled[0]
        assert interval == pytest.approx(1 / 12)
        assert app._canvas.mode == "dust"
        assert app._canvas.frame_number == 0

        await pilot.press("2")
        assert app._canvas.mode == "fractal"
        assert app._canvas.frame_number == 0

        advance()
        advance()
        assert app._canvas.frame_number == 2

        await pilot.press("space")
        paused_at = app._canvas.frame_number
        advance()
        advance()
        assert app._canvas.frame_number == paused_at

        await pilot.press("3")
        assert app._canvas.mode == "signal"
        assert app._canvas.frame_number == 0
        await pilot.press("space")
        advance()
        assert app._canvas.frame_number == 1
