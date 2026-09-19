"""Three small 12fps background studies for the public presentation.

This is intentionally a standalone visual sampler. It does not read season
state, call models, or import the dashboard. The renderer is procedural so the
same frame can be replayed deterministically while we choose a visual language.

Run from the repository root with::

    .venv/bin/python demos/textual_background_sampler.py

Keys:

    1 / 2 / 3    choose a background
    Space        pause / resume
    H            hide / show the small sampler label
    Q / Escape   quit
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from rich.text import Text
from textual.app import App, ComposeResult
from textual.widget import Widget
from textual.widgets import Static


DEFAULT_FPS = 12
MODE_NAMES = ("dust", "fractal", "signal")
ASCII_SHADES = " .:-=+*#%@"

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class BackgroundSpec:
    key: str
    title: str
    subtitle: str
    mood: str


BACKGROUND_SPECS: dict[str, BackgroundSpec] = {
    "dust": BackgroundSpec(
        key="dust",
        title="DUST & HALATION",
        subtitle="slow light leak / warm stock-film atmosphere",
        mood="intimate, nostalgic, human",
    ),
    "fractal": BackgroundSpec(
        key="fractal",
        title="FRACTAL BLOOM",
        subtitle="evolving Julia field / luminous recursive edges",
        mood="uncanny, alive, cosmological",
    ),
    "signal": BackgroundSpec(
        key="signal",
        title="NOCTURNE SIGNAL",
        subtitle="spectral weather / soft radar interference",
        mood="observational, technical, liminal",
    ),
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _mix(first: RGB, second: RGB, amount: float) -> RGB:
    amount = _clamp(amount)
    return tuple(
        round(a + (b - a) * amount) for a, b in zip(first, second, strict=True)
    )  # type: ignore[return-value]


def _rgb(value: RGB) -> str:
    return "#%02x%02x%02x" % value


def _gradient(stops: Sequence[RGB], size: int = 32) -> tuple[str, ...]:
    if not stops:
        raise ValueError("a gradient needs at least one color")
    if len(stops) == 1:
        return (_rgb(stops[0]),) * size

    colors: list[str] = []
    for index in range(size):
        position = index / max(size - 1, 1)
        scaled = position * (len(stops) - 1)
        left_index = min(int(scaled), len(stops) - 2)
        local_amount = scaled - left_index
        colors.append(_rgb(_mix(stops[left_index], stops[left_index + 1], local_amount)))
    return tuple(colors)


PALETTES: dict[str, tuple[str, ...]] = {
    "dust": _gradient(
        ((4, 7, 16), (25, 18, 31), (74, 35, 39), (164, 73, 48), (255, 198, 126)),
        32,
    ),
    "fractal": _gradient(
        ((3, 5, 18), (25, 13, 61), (21, 101, 126), (183, 44, 128), (255, 204, 118)),
        32,
    ),
    "signal": _gradient(
        ((3, 10, 24), (6, 36, 55), (15, 91, 105), (73, 157, 145), (220, 190, 117)),
        32,
    ),
}


def _palette_color(palette: Sequence[str], value: float) -> str:
    index = round(_clamp(value) * (len(palette) - 1))
    return palette[index]


def _shade(value: float) -> str:
    index = round(_clamp(value) * (len(ASCII_SHADES) - 1))
    return ASCII_SHADES[index]


def _noise(x: float, y: float, phase: float) -> float:
    """Cheap, deterministic film grain with no random state to reset."""

    return (
        math.sin(x * 12.9898 + y * 78.233 + phase * 1.71)
        * math.sin(x * 4.127 + y * 19.193 - phase * 0.63)
        + 1
    ) * 0.5


def _render_dust(width: int, height: int, phase: float) -> Iterable[tuple[str, str]]:
    palette = PALETTES["dust"]
    for row in range(height):
        y = row / max(height - 1, 1)
        ny = y * 2.0 - 1.0
        for column in range(width):
            x = column / max(width - 1, 1)
            nx = x * 2.0 - 1.0

            leak_x = -0.56 + 0.30 * math.sin(phase * 0.16)
            leak_y = 0.18 + 0.18 * math.cos(phase * 0.11)
            leak = math.exp(-(((nx - leak_x) / 0.46) ** 2 + ((ny - leak_y) / 1.45) ** 2))

            flare_x = 0.48 + 0.18 * math.cos(phase * 0.09)
            flare_y = -0.25 + 0.14 * math.sin(phase * 0.13)
            flare = math.exp(-(((nx - flare_x) / 0.23) ** 2 + ((ny - flare_y) / 0.72) ** 2))

            diagonal = math.exp(
                -((ny - (0.52 * nx - 0.35 * math.sin(phase * 0.12))) / 0.12) ** 2
            )
            grain = (_noise(x, y, phase) - 0.5) * 0.09
            intensity = _clamp(0.045 + leak * 0.43 + flare * 0.56 + diagonal * 0.16 + grain)

            # A few slow motes make this read as atmosphere rather than a static gradient.
            mote_seed = (column * 37 + row * 91) % 113
            mote_x = ((mote_seed * 0.071) + phase * (0.004 + mote_seed % 4 * 0.001)) % 1.0
            mote_y = (mote_seed * 0.173 + math.sin(phase * 0.07 + mote_seed) * 0.035) % 1.0
            if abs(x - mote_x) < 0.012 and abs(y - mote_y) < 0.035:
                intensity = _clamp(intensity + 0.20)

            yield _shade(intensity * 0.84), _palette_color(palette, intensity)


def _render_fractal(width: int, height: int, phase: float) -> Iterable[tuple[str, str]]:
    palette = PALETTES["fractal"]
    # A gently moving Julia constant gives us a living field without hard cuts.
    constant_x = -0.71 + 0.055 * math.sin(phase * 0.17)
    constant_y = 0.18 + 0.075 * math.cos(phase * 0.13)
    rotation = phase * 0.018
    cosine = math.cos(rotation)
    sine = math.sin(rotation)
    zoom = 1.08 + 0.12 * math.sin(phase * 0.07)
    max_iterations = 22

    for row in range(height):
        screen_y = (row / max(height - 1, 1) - 0.5) * 2.05
        for column in range(width):
            screen_x = (column / max(width - 1, 1) - 0.5) * 3.10
            zx = (screen_x * cosine - screen_y * sine) / zoom
            zy = (screen_x * sine + screen_y * cosine) / zoom
            iterations = 0
            magnitude = 0.0

            while zx * zx + zy * zy < 4.0 and iterations < max_iterations:
                zx, zy = zx * zx - zy * zy + constant_x, 2.0 * zx * zy + constant_y
                magnitude = zx * zx + zy * zy
                iterations += 1

            if iterations == max_iterations:
                intensity = 0.025 + 0.025 * math.sin(phase * 0.25 + screen_x * 2.0)
                glyph = "."
            else:
                smooth = iterations + 1.0 - math.log(max(math.log(max(magnitude, 1.0001)), 0.0001), 2)
                band = _clamp(smooth / max_iterations)
                intensity = _clamp(0.10 + band * 0.83 + 0.08 * math.sin(smooth * 1.7 + phase * 0.18))
                glyph = _shade(intensity)

            yield glyph, _palette_color(palette, intensity)


def _render_signal(width: int, height: int, phase: float) -> Iterable[tuple[str, str]]:
    palette = PALETTES["signal"]
    for row in range(height):
        y = row / max(height - 1, 1)
        ny = y * 2.0 - 1.0
        for column in range(width):
            x = column / max(width - 1, 1)
            nx = x * 2.0 - 1.0

            wave_a = 0.18 * math.sin(nx * 4.2 + phase * 0.22) + 0.11 * math.sin(nx * 10.0 - phase * 0.13)
            wave_b = 0.14 * math.sin(nx * 2.1 - phase * 0.15) + 0.07 * math.cos(nx * 14.0 + phase * 0.20)
            ridge_a = math.exp(-((ny - wave_a - 0.12) / 0.065) ** 2)
            ridge_b = math.exp(-((ny - wave_b - 0.44) / 0.11) ** 2)
            haze = math.exp(-((ny + 0.25 + 0.16 * math.sin(phase * 0.08)) / 0.70) ** 2) * 0.18
            scan = (math.sin((row + phase * 0.65) * math.pi * 0.48) + 1.0) * 0.025
            grain = (_noise(x * 1.7, y * 1.4, phase * 0.8) - 0.5) * 0.075
            intensity = _clamp(0.035 + ridge_a * 0.48 + ridge_b * 0.33 + haze + scan + grain)

            # Deliberate gaps in the ridges suggest an instrument reading rather than a landscape.
            if ridge_a > 0.20 or ridge_b > 0.19:
                glyph = "-" if column % 3 else "="
            else:
                glyph = _shade(intensity * 0.76)
            yield glyph, _palette_color(palette, intensity)


def render_frame(mode: str, frame: int, width: int, height: int, fps: int = DEFAULT_FPS) -> Text:
    """Build one deterministic Rich frame for tests, capture, or Textual."""

    if mode not in BACKGROUND_SPECS:
        raise ValueError(f"unknown background mode: {mode}")
    width = max(1, width)
    height = max(1, height)
    phase = frame / max(fps, 1)

    renderer = {
        "dust": _render_dust,
        "fractal": _render_fractal,
        "signal": _render_signal,
    }[mode]
    cells = iter(renderer(width, height, phase))
    canvas = Text(no_wrap=True, overflow="crop")
    for row in range(height):
        for _column in range(width):
            glyph, color = next(cells)
            canvas.append(glyph, style=color)
        if row < height - 1:
            canvas.append("\n")
    return canvas


class BackgroundCanvas(Widget):
    """Full-screen procedural canvas driven by a deliberately modest frame rate."""

    DEFAULT_CSS = """
    BackgroundCanvas {
        width: 1fr;
        height: 1fr;
        overflow: hidden hidden;
    }
    """

    def __init__(self, *, mode: str = "dust", fps: int = DEFAULT_FPS, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.mode = mode
        self.fps = max(1, fps)
        self.frame_number = 0
        self.paused = False

    def on_mount(self) -> None:
        self.set_interval(1 / self.fps, self._advance)

    def _advance(self) -> None:
        if not self.paused:
            self.frame_number += 1
            self.refresh()

    def set_mode(self, mode: str) -> None:
        if mode not in BACKGROUND_SPECS:
            raise ValueError(f"unknown background mode: {mode}")
        self.mode = mode
        self.frame_number = 0
        self.refresh()

    def render(self) -> Text:
        return render_frame(self.mode, self.frame_number, self.size.width, self.size.height, self.fps)


class BackgroundSampler(App[None]):
    """Interactive sampler used to choose the first public visual direction."""

    TITLE = "AI Improv Troupe — Background Studies"
    CSS = """
    Screen {
        background: #05070e;
        layers: base overlay;
    }

    #canvas {
        layer: base;
    }

    #hud {
        layer: overlay;
        dock: top;
        width: 1fr;
        height: auto;
        padding: 1 2;
        background: #05070ed9;
        color: #f4e8d0;
    }

    #controls {
        layer: overlay;
        dock: bottom;
        width: 1fr;
        height: auto;
        padding: 1 2;
        background: #05070ebf;
        color: #d4d8e5;
    }
    """

    BINDINGS = [
        ("1", "show_dust", "Dust & Halation"),
        ("2", "show_fractal", "Fractal Bloom"),
        ("3", "show_signal", "Nocturne Signal"),
        ("space", "toggle_pause", "Pause"),
        ("h", "toggle_hud", "HUD"),
        ("q", "exit_app", "Quit"),
        ("escape", "exit_app", "Quit"),
    ]

    def __init__(self, *, initial_mode: str = "dust", fps: int = DEFAULT_FPS, show_hud: bool = True) -> None:
        super().__init__()
        if initial_mode not in BACKGROUND_SPECS:
            raise ValueError(f"unknown background mode: {initial_mode}")
        self.initial_mode = initial_mode
        self.fps = max(1, fps)
        self.show_hud = show_hud

    def compose(self) -> ComposeResult:
        yield BackgroundCanvas(mode=self.initial_mode, fps=self.fps, id="canvas")
        yield Static(id="hud")
        yield Static(
            "[1] Dust & Halation   [2] Fractal Bloom   [3] Nocturne Signal    "
            "[Space] pause   [H] hide label   [Q] quit",
            id="controls",
        )

    def on_mount(self) -> None:
        self._canvas = self.query_one("#canvas", BackgroundCanvas)
        self._hud = self.query_one("#hud", Static)
        self._update_hud()
        self._apply_hud_visibility()

    def _update_hud(self) -> None:
        spec = BACKGROUND_SPECS[self._canvas.mode]
        state = "PAUSED" if self._canvas.paused else f"{self.fps} FPS"
        self._hud.update(
            f"[bold]{spec.title}[/bold]  [dim]· {spec.subtitle}[/dim]\n"
            f"[dim]mood:[/dim] {spec.mood}   [dim]state:[/dim] {state}"
        )

    def _apply_hud_visibility(self) -> None:
        self._hud.display = self.show_hud

    def _select(self, mode: str) -> None:
        self._canvas.set_mode(mode)
        self._update_hud()

    def action_show_dust(self) -> None:
        self._select("dust")

    def action_show_fractal(self) -> None:
        self._select("fractal")

    def action_show_signal(self) -> None:
        self._select("signal")

    def action_toggle_pause(self) -> None:
        self._canvas.paused = not self._canvas.paused
        self._update_hud()

    def action_toggle_hud(self) -> None:
        self.show_hud = not self.show_hud
        self._apply_hud_visibility()

    def action_exit_app(self) -> None:
        self.exit()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=MODE_NAMES, default="dust")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    parser.add_argument("--no-hud", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    BackgroundSampler(
        initial_mode=args.mode,
        fps=max(1, args.fps),
        show_hud=not args.no_hud,
    ).run()


if __name__ == "__main__":
    main()
