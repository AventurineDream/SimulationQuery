"""Events emitted by the orchestrator.

The engine is UI-agnostic: it only yields these. A stdout runner, a Textual TUI,
or a future web UI all consume the same stream.
"""

from __future__ import annotations

from dataclasses import dataclass

from .transcript import Turn


@dataclass
class TurnStarted:
    index: int
    speaker: str


@dataclass
class TokenEmitted:
    speaker: str
    text: str


@dataclass
class TurnCompleted:
    index: int
    turn: Turn


@dataclass
class SceneEnded:
    reason: str  # "max_turns" | "interrupted" | ...
    line_count: int


Event = TurnStarted | TokenEmitted | TurnCompleted | SceneEnded
