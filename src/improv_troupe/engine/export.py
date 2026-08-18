"""Render a finished transcript to a clean script.md."""

from __future__ import annotations

from datetime import datetime, timezone

from ..domain import ProductionPlan
from .orchestrator import ActorRuntime
from .transcript import Transcript


def to_markdown(
    plan: ProductionPlan,
    transcript: Transcript,
    runtimes: list[ActorRuntime] | None = None,
) -> str:
    out: list[str] = [f"# {plan.title}"]
    if plan.logline:
        out.append(f"\n_{plan.logline}_")

    out.append("")
    out.append(f"**Setting.** {plan.scene.setting}")
    out.append(f"\n**Premise.** {plan.scene.premise}")
    if plan.scene.tone or plan.scene.genre:
        bits = [b for b in (plan.scene.genre, plan.scene.tone) if b]
        out.append(f"\n**Tone.** {' — '.join(bits)}")

    out.append("\n---\n")

    for turn in transcript.turns:
        if turn.kind == "direction":
            out.append(f"*{turn.text}*\n")
        else:
            out.append(f"**{turn.speaker}.** {turn.text}\n")

    out.append("---\n")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    footer = f"_Improvised by an AI troupe · {transcript.line_count} lines · {stamp}_"
    out.append(footer)
    if runtimes:
        cast = ", ".join(f"{r.name} ({r.model})" for r in runtimes)
        out.append(f"\n_Cast: {cast}_")

    return "\n".join(out) + "\n"
