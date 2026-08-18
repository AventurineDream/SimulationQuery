"""Prompt construction.

Each turn is a *fresh, stateless* call: because a different model may play each
character, we don't carry a chat history per model. Instead every actor receives
a system prompt describing their character and the scene, plus a user message
containing the whole script so far and a cue to speak next.
"""

from __future__ import annotations

from ..domain import Actor, ProductionPlan
from ..llm.client import Message
from .transcript import Transcript


def build_system_prompt(plan: ProductionPlan, actor: Actor) -> str:
    scene = plan.scene
    c = plan.constraints
    lines = [
        f"You are {actor.name}, a character in an improvised scene. Stay fully in character.",
        "",
        f"SETTING: {scene.setting}",
        f"PREMISE: {scene.premise}",
    ]
    if scene.tone or scene.genre:
        lines.append(f"TONE: {scene.tone or 'n/a'}  |  GENRE: {scene.genre or 'n/a'}")
    lines += [
        "",
        "YOUR CHARACTER:",
        actor.character_brief,
    ]
    if actor.voice_notes:
        lines.append(f"Voice: {actor.voice_notes}")
    lines += [
        "",
        "RULES:",
        f"- Respond ONLY as {actor.name}. Never write dialogue or actions for anyone else.",
        f"- Write a single turn: {c.turn_length}.",
        "- Do NOT prefix your name. Use [square brackets] for brief stage directions only.",
        "- React to what was just said and push the scene forward.",
        "- Never break character, narrate the whole scene, or mention being an AI.",
    ]
    if c.content:
        lines.append("- Content limits: " + "; ".join(c.content) + ".")
    if c.objective:
        lines.append(f"- The scene is quietly working toward: {c.objective}")
    return "\n".join(lines)


def build_user_prompt(actor: Actor, transcript: Transcript) -> str:
    script = transcript.script_view().strip() or "(The scene is about to begin.)"
    return (
        "The scene so far:\n\n"
        f"{script}\n\n"
        "---\n"
        f"It is {actor.name}'s turn. Write {actor.name}'s next line now, "
        "in character and nothing else."
    )


def build_messages(
    plan: ProductionPlan, actor: Actor, transcript: Transcript
) -> list[Message]:
    return [
        {"role": "system", "content": build_system_prompt(plan, actor)},
        {"role": "user", "content": build_user_prompt(actor, transcript)},
    ]
