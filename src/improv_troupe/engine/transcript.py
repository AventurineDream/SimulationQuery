"""The running record of a scene, and how it renders as a script."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Turn:
    speaker: str  # actor name, or "STAGE" for directions/opening beat
    text: str
    kind: str = "line"  # "line" | "direction"


@dataclass
class Transcript:
    turns: list[Turn] = field(default_factory=list)

    def add_line(self, speaker: str, text: str) -> Turn:
        turn = Turn(speaker=speaker, text=text, kind="line")
        self.turns.append(turn)
        return turn

    def add_direction(self, text: str) -> Turn:
        turn = Turn(speaker="STAGE", text=text, kind="direction")
        self.turns.append(turn)
        return turn

    @property
    def line_count(self) -> int:
        return sum(1 for t in self.turns if t.kind == "line")

    def script_view(self) -> str:
        """Plain-text script the actors read as context each turn."""
        out: list[str] = []
        for turn in self.turns:
            if turn.kind == "direction":
                out.append(f"[{turn.text}]")
            else:
                out.append(f"{turn.speaker}: {turn.text}")
        return "\n".join(out)
