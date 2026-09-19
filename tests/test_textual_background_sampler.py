"""Deterministic and interaction checks for the optional visual sampler."""

from __future__ import annotations

import pytest

pytest.importorskip("textual")

from demos.textual_background_sampler import (  # noqa: E402
    BACKGROUND_SPECS,
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
async def test_sampler_switches_modes_and_advances_at_a_bounded_rate() -> None:
    app = BackgroundSampler()
    async with app.run_test(size=(64, 20)) as pilot:
        assert app._canvas.mode == "dust"
        assert app._canvas.frame_number == 0

        await pilot.press("2")
        assert app._canvas.mode == "fractal"
        # The app's 12fps timer may legitimately fire during key dispatch.
        assert 0 <= app._canvas.frame_number <= 1

        await pilot.pause(0.20)
        assert 1 <= app._canvas.frame_number <= 4

        await pilot.press("space")
        paused_at = app._canvas.frame_number
        await pilot.pause(0.20)
        assert app._canvas.frame_number == paused_at

        await pilot.press("3")
        assert app._canvas.mode == "signal"
