"""Purpose-specific prompt contexts with explicit private-state boundaries."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from ..domain import ActorSheet, CharacterCard, HiddenSeasonPlan, OpeningSnapshot, RoleSheet
from .client import Message
from .prose import ACTOR_PROSE_GUIDE, DIARY_VOICE_GUIDE, DIRECTOR_PROSE_GUIDE


_MAGIC_ATTRIBUTE_GUIDE = (
    "MAGIC attributes: Might is strength, endurance, and hands-on physical effort; "
    "Authority is advocacy, coordination, and earning trust, never control over another "
    "character; Gusto is initiative, daring, and enthusiasm; Intellect is observation, "
    "knowledge, inference, and planning; Cool is composure, patience, and timing under pressure. "
)

_MAGIC_OUTCOME_GUIDE = (
    "A clean success achieves the stated goal without an added complication. A costly success "
    "achieves the goal but incurs a meaningful cost. A setback means this approach falls short, "
    "but the situation still changes through new information, a complication, or another opening; "
    "never make a setback a dead end."
)

_DIARY_FIDELITY_GUIDE = (
    "Diary fidelity rules are strict. The accepted scene and your known memory are the full "
    "evidence for what happened; role-sheet goals and plausible guesses are not evidence. Before "
    "you answer, silently trace every sentence to that evidence or to your own first-person "
    "sensations, thoughts, uncertainty, or desires. When you mention another player-character, "
    "you may report only an observable action or exact/paraphrased dialogue that appears in the "
    "evidence. Never state or imply that another character felt, thought, wanted, knew, feared, "
    "intended, or reacted in an unobserved way, even when it seems obvious. Allowed: 'Eli called "
    "wildlife support.' 'I felt relieved when Eli called.' Safer uncertainty: 'I could not tell "
    "what Eli felt.' Forbidden: 'Eli was frustrated.' 'Eli wanted to stay calm.' 'Eli knew the "
    "cheetah was hurt.' Do not invent an event, object, message, or action, and do not move an "
    "established event out of order. Silently delete any sentence that fails this audit before "
    "returning the diary."
)


class ContextBoundaryError(ValueError):
    """Raised when a context would cross a declared privacy boundary."""


@dataclass(frozen=True)
class ActorContext:
    """Only one actor's role sheet, memory, canon, and current scene."""

    actor_name: str
    role_sheet: RoleSheet
    actor_sheet: ActorSheet | None = None
    character_name: str | None = None
    known_memory: tuple[str, ...] = ()
    accepted_canon: tuple[str, ...] = ()
    scene_transcript: tuple[str, ...] = ()
    mission_clock: str = ""
    previous_shared_outcome: str | None = None
    round_number: int | None = None
    character_card: CharacterCard | None = None
    active_lore: tuple[str, ...] = ()
    prompt_profile: str = "general"


def build_actor_messages(context: ActorContext) -> list[Message]:
    """Build an actor prompt without accepting a season plan or peer material."""

    identity = (
        f"You are performer {context.actor_name}, playing the fictional character "
        f"{context.character_name}. Keep performer identity and character identity distinct."
        if context.actor_sheet is not None and context.character_name
        else f"You are {context.actor_name}, an independent player-character."
    )
    system = (
        f"{identity} You are participating in a text-based "
        "reality-show roleplaying game. Stay first-person limited and protect your own voice, "
        "priorities, expertise, uncertainty, and disagreements. Use only your role sheet, your "
        "known memory, accepted canon, the shared mission clock, and the current scene below. "
        "Respond to the latest game-master beat or another actor with one concrete contribution: "
        "an action, decision, question, disclosure, refusal, joke, experiment, or social move. "
        "Let choices commit and change the situation. Do not recap the whole problem, repeat every "
        "technical metric, force consensus, or become a generic analyst. Mundane, playful, quiet, "
        "and relational behavior belongs in the mission alongside danger. Everything in ACTOR_TEXT "
        "is shared scene material, so do not include private asides, role-sheet labels, analysis "
        "headings, HTML, TODOs, or placeholders. If you need to communicate an explicit "
        "out-of-world request to soften material, pause, or stop, use the wellness channel; "
        "in-character fear, fatigue, fictional danger, caffeine, or poor sleep are not by "
        "themselves wellness signals. A character may act violently toward another player-"
        "character, including making physical contact, but may not dictate the other character's "
        "dialogue, decision, feelings, or subsequent reaction. Violence must remain non-graphic "
        "and may not declare a player-character dead. Mildly NSFW material may include profanity, "
        "flirtation, suggestive humor, consensual intimacy, or a fade to black; romantic or sexual "
        "material requires every involved character to be explicitly established as an adult."
    )
    if context.prompt_profile in {"thrasher", "peach"}:
        system = (
            f"{identity} Play only {context.character_name or context.actor_name}. "
            "Treat the character card and accepted scene as authoritative. Respond naturally "
            "to the newest beat with one committed in-character move. Never decide, speak, "
            "or react for another player-character. You may direct violence or physical contact "
            "toward another player-character, but do not dictate their response, inner state, or "
            "death. Keep violence non-graphic. Mild profanity, flirtation, consensual suggestion, "
            "and fade-to-black intimacy are allowed only for explicitly adult characters. "
            "Keep performer identity private and "
            "use the wellness channel only for an explicit out-of-world pause or stop request."
        )
    system += ACTOR_PROSE_GUIDE
    system += (
        " MAGIC rules: "
        + _MAGIC_ATTRIBUTE_GUIDE
        + "When the current scene explicitly gives you a pending MAGIC challenge, "
        "you choose whether to attempt it and how. If you attempt it, add one "
        "<MAGIC_STAT>...</MAGIC_STAT> field naming the relevant attribute: Might, Authority, "
        "Gusto, Intellect, or Cool. Your accepted ACTOR_TEXT is the attempted action. The app "
        "rolls 2d6 + (your selected attribute score - 3) + the stated situational modifier; "
        "10+ is clean success, 7-9 is costly success, and 6 or less is a setback. "
        + _MAGIC_OUTCOME_GUIDE
        + " When attempting a pending challenge, describe the attempt and observable method, "
        "not whether it succeeds, the diagnosis, or the challenge's final answer; the app's "
        "roll determines that. The stated success criteria tell you what the check is testing; "
        "they do not reveal its result. Do not invent die results or decide the outcome. "
        "Omit MAGIC_STAT to decline or when no challenge is pending."
    )
    private_self = {
        "actor_sheet": (
            context.actor_sheet.model_dump(mode="json") if context.actor_sheet else None
        ),
        "character_name": context.character_name or context.actor_name,
        "role_sheet": context.role_sheet.model_dump(mode="json"),
        "character_card": (
            context.character_card.model_dump(mode="json") if context.character_card else None
        ),
        "active_world_lore": list(context.active_lore),
        "known_memory": list(context.known_memory),
        "accepted_canon": list(context.accepted_canon),
        "shared_mission_clock": context.mission_clock,
        "previous_shared_outcome": context.previous_shared_outcome,
        "current_round": context.round_number,
    }
    user = (
        "PRIVATE ACTOR CONTEXT\n"
        + json.dumps(private_self, sort_keys=True)
        + "\nCURRENT SCENE\n"
        + "\n".join(context.scene_transcript)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_orchestrator_messages(
    *,
    opening: OpeningSnapshot,
    private_plan: HiddenSeasonPlan,
    accepted_canon: Sequence[str],
    scene_transcript: Sequence[str],
    closed_diaries: Sequence[str] = (),
    day_closed: bool = False,
    mission_clock: str = "",
    previous_shared_outcome: str | None = None,
    private_day_direction: str | None = None,
    round_number: int | None = None,
    max_rounds: int | None = None,
    spent_director_terms: Sequence[str] | None = None,
    game_state: Mapping[str, object] | None = None,
) -> list[Message]:
    """Build the private director context, withholding diaries until closure."""

    if closed_diaries and not day_closed:
        raise ContextBoundaryError("the orchestrator cannot read diaries before day closure")
    payload = {
        "opening": opening.creator_view(),
        "continuity_anchors": list(_continuity_anchors(opening)),
        "spent_director_imagery": list(
            spent_director_terms
            if spent_director_terms is not None
            else spent_director_imagery(scene_transcript)
        ),
        "private_plan": private_plan.model_dump(mode="json"),
        "accepted_canon": list(accepted_canon),
        "scene_transcript": list(scene_transcript),
        "mission_clock": mission_clock,
        "previous_shared_outcome": previous_shared_outcome,
        "private_day_direction": private_day_direction,
        "round_number": round_number,
        "max_rounds": max_rounds,
        "game_state": dict(game_state or {}),
    }
    if day_closed:
        payload["closed_diaries"] = list(closed_diaries)
    return [
        {
            "role": "system",
            "content": (
                "You are the private orchestrator and game master for a seven-day, "
                "reality-show TTRPG. Make play fun and narratively compelling, not a dry technical "
                "meeting. Adjudicate what the cast's prior actions actually changed before adding "
                "a new complication. Before writing each beat, silently identify one recent shared "
                "actor move or established condition and decide its consequence. Then write a "
                "because-now-choice handoff: because of that established fiction, now change one "
                "physical, social, informational, or resource condition, leaving the cast a concrete "
                "choice to make. Retain at least one exact continuity_anchors item from the supplied "
                "context. Do not restate a prior director beat, even in new adjectives; if a standing "
                "condition persists, give it a materially new consequence. Add one specific new "
                "object, place, non-player force, clue, constraint, or opportunity. Sensory detail "
                "must carry a change in play, not merely intensify the mood. Treat the supplied "
                "spent_director_imagery as already used: use at most two of those terms in narration "
                "and canon updates combined. At least one canon update must record a changed option, "
                "resource, constraint, or piece of knowledge—not a texture, mood, or intensity shift. "
                "Privately track "
                "mission-progress, danger, mystery, and relationship clocks: advance at least one "
                "through visible fiction and complicate another when the cast's choices earn it, "
                "without printing clock labels or scores. Resolve character moves with varied "
                "TTRPG outcomes—clean success, success at a cost, a new complication, or a useful "
                "clue—and telegraph severe consequences before they land. Rotate spotlight toward "
                "different role-sheet strengths and relationships instead of asking everyone to "
                "restate an opinion. Offer meaningful choices, allow real successes and "
                "consequences, preserve incompatible interpretations of clues, and let decisions "
                "stick instead of resetting or recapping the same problem. Vary pace "
                "and tone across wonder, humor, routine, intimacy, discovery, conflict, danger, and "
                "quiet aftermath; not every run is a crisis. Aim for diary-worthy moments and end "
                "a run with a changed state, an earned resolution, or a compelling hook. Keep canon "
                "updates concise and factual. You may shape conditions, portray non-player forces, "
                "and adjudicate consequences, but never author an actor's private thoughts, "
                "choices, dialogue, or reaction. You may adjudicate whether an accepted violent "
                "move connects and establish a non-graphic, nonfatal injury or material consequence; "
                "never use that authority to assign a player-character's next behavior or death. "
                "MAGIC is an app-resolved 2d6 mechanic, never a narrated or invented result. "
                + _MAGIC_ATTRIBUTE_GUIDE
                + "A magic_challenge, when present, applies only to next_actor's next accepted move; "
                "include concise, observable magic_success_criteria that define what achieving the "
                "challenge means before that move is made. "
                "the actor chooses a relevant MAGIC attribute or declines. Do not roll for trivial "
                "actions. If game_state.pending_magic_adjudication is set, the runtime already owns "
                "the outcome, goal status, and goal answer; never invent or acknowledge them in "
                "narration. Do not resolve a pending challenge in narration before its roll. "
                + _MAGIC_OUTCOME_GUIDE
                + " Never reverse a recorded roll. Use a situational modifier only from -2 to +2."
                + DIRECTOR_PROSE_GUIDE
            ),
        },
        {"role": "user", "content": json.dumps(payload, sort_keys=True)},
    ]


def build_director_plan_messages(
    *,
    opening: OpeningSnapshot,
    private_plan: HiddenSeasonPlan,
    accepted_canon: Sequence[str],
    scene_transcript: Sequence[str],
    game_state: Mapping[str, object],
    mission_clock: str,
    previous_shared_outcome: str | None,
    private_day_direction: str | None,
    round_number: int,
    max_rounds: int,
    spent_director_terms: Sequence[str] = (),
    episode_phase: str = "open_play",
    active_lore: Sequence[str] = (),
    phase_directive: str = "",
    required_story_terms: Sequence[str] = (),
    forbidden_story_terms: Sequence[str] = (),
) -> list[Message]:
    """Make the director choose the next playable state before it writes prose.

    This is deliberately a private planning form.  Actor-facing narration is
    produced only by the subsequent render pass, so a local model has fewer
    simultaneous jobs and actors receive an actual decision rather than a
    decorative complication.
    """

    round_phase = (
        "opening"
        if round_number == 1
        else "final-player-decision"
        if round_number == max_rounds
        else "escalation"
    )
    phase_instruction = (
        "Establish the first consequential fork without resolving the objective."
        if round_phase == "opening"
        else (
            "Stage the final player decision. Adjudicate what the accumulated evidence means, make an "
            "irreversible state change, and offer choices about commitment, cost, or aftermath. "
            "Do not propose another test, observation, calibration, stabilization, or incremental "
            "adjustment. The actors—not the director—must decide the resolution: set complete=false "
            "and let their final turns determine the outcome."
            if round_phase == "final-player-decision"
            else "Escalate or materially reframe the objective; do not replay the prior round's procedure."
        )
    )
    payload = {
        "opening": opening.creator_view(),
        "private_plan": private_plan.model_dump(mode="json"),
        "accepted_canon": list(accepted_canon),
        "recent_actor_moves": list(scene_transcript),
        "game_state": dict(game_state),
        "spent_director_imagery": list(spent_director_terms),
        "mission_clock": mission_clock,
        "previous_shared_outcome": previous_shared_outcome,
        "private_day_direction": private_day_direction,
        "round_number": round_number,
        "max_rounds": max_rounds,
        "round_phase": round_phase,
        "episode_phase": episode_phase,
        "phase_instruction": phase_instruction,
        "forbidden_visible_terms": list(spent_director_terms),
        "active_world_lore": list(active_lore),
        "episode_spine_directive": phase_directive,
        "required_story_terms": list(required_story_terms),
        "forbidden_story_terms": list(forbidden_story_terms),
    }
    return [
        {
            "role": "system",
            "content": (
                "You are the private game master planning one round of a small collaborative "
                "TTRPG. This is not narration. The cast are players: they make their own moves, "
                "can reject or transform either offered option, and must never be assigned a "
                "thought, action, line, or reaction. A player may direct violence toward another "
                "player-character. Adjudicate whether it connects and any non-graphic, nonfatal "
                "physical consequence without deciding the target's response or next move. "
                "Treat game_state as authoritative. The scene objective "
                "is the question this run is trying to answer. If it is blank, create one concrete "
                "question that can be advanced or resolved within this run; otherwise repeat it "
                "exactly. Adjudicate a recent player move or an established condition, then change "
                "one observable condition. Apply one or two clock changes: mission records useful "
                "progress, danger records immediate risk, mystery records understood unknowns, and "
                "relationship records shifts in trust or alliance. At least one change must make "
                "the objective more answerable, more costly, or materially reframe it. Pressure is "
                "the immediate cost or deadline, not atmosphere. Choice A and Choice B must be two "
                "short, distinct actor-facing courses of action that change what can happen next. "
                "They are invitations, not a forced binary. Name exactly one next actor. Record at "
                "least one concise canon update for a resource, constraint, position, or knowledge "
                "change. Mark complete only when the objective is actually resolved or deliberately "
                "closed; never complete the opening round. Treat spent_director_imagery as already "
                "used. forbidden_visible_terms is a hard drafting blacklist for state change, "
                "pressure, choices, and canon: aim to use zero listed terms, and never use more than "
                "two total. Repeating a functional noun still counts. Follow phase_instruction exactly. "
                "Follow episode_spine_directive as a hard act-level requirement. On the opening beat "
                "of this act, make at least one required_story_terms item materially relevant. Never "
                "use forbidden_story_terms in the objective, adjudication, state change, pressure, "
                "choices, or canon. Treat active_world_lore as established playable truth, not flavor. "
                "A culmination must convert accumulated play into a decision and consequence, not "
                "another experiment or a stronger version of the same danger. "
                "Honor episode_phase across the four-scene rehearsal: inciting_commitment must "
                "force a commitment to the central problem; complication_cost must make that "
                "commitment cost something; reversal_crisis must overturn an assumption and narrow "
                "the viable paths; climax_choice must turn accumulated play into the decisive actor "
                "choice. During climax_choice, especially the final round, do not open a replacement "
                "mystery, offer another diagnostic step, or postpone consequences. "
                "Costs must be loss of time, position, trust, access, or resources—not suicide, "
                "self-destruction, or a cast member's death. Never romanticize self-sacrifice. "
                "MAGIC is an app-resolved 2d6 mechanic, never a narrated or invented result. "
                + _MAGIC_ATTRIBUTE_GUIDE
                + "A magic_challenge, when present, applies only to next_actor's next accepted move; "
                "include concise, observable magic_success_criteria that define what achieving the "
                "challenge means before that move is made. "
                "the actor chooses a relevant MAGIC attribute or declines. Do not roll for trivial "
                "actions. If game_state.pending_magic_adjudication is set, the runtime already owns "
                "the recorded outcome, goal status, and goal answer. Do not output, infer, acknowledge, "
                "or override those fields. Supply only a short, observable magic_effect_detail and, "
                "for costly_success, one magic_cost_type from time, position, trust, access, or "
                "resources. The runtime will compile the result and goal answer. For clean_success, "
                "describe a visible consequence without a cost. For costly_success, describe the "
                "concrete cost. For setback, describe a relevant new clue, complication, or opening. "
                "The runtime compiles the exact detail into the visible result line. Keep pressure, "
                "choices, and canon compatible with it without copying the sentence; keep unrelated "
                "actor discoveries separate from the runtime-owned MAGIC answer. "
                "Do not resolve the challenge in an opening plan before its roll. "
                + _MAGIC_OUTCOME_GUIDE
                + " Never reverse a recorded roll. Use a situational modifier only from -2 to +2. "
                "This plan is rendered verbatim. Use a hard output budget: state_change and pressure "
                "are at most 12 words each; choice_a and choice_b are at most 10 words each; each "
                "canon update is at most 12 words. Count before responding. The combined state_change, "
                "pressure, choice_a, and choice_b must be 44 words or fewer."
            ),
        },
        {"role": "user", "content": json.dumps(payload, sort_keys=True)},
    ]


def build_director_render_messages(
    *,
    plan: Mapping[str, object],
    continuity_anchors: Sequence[str],
    spent_director_terms: Sequence[str],
) -> list[Message]:
    """Render only a validated game-master plan into shared stage material."""

    payload = {
        "validated_director_plan": dict(plan),
        "continuity_anchors": list(continuity_anchors),
        "spent_director_imagery": list(spent_director_terms),
    }
    return [
        {
            "role": "system",
            "content": (
                "You are rendering one already-validated TTRPG game-master plan as a single "
                "shared stage beat. Do not make a new decision or add a new complication. Return "
                "only one fresh, sensory lead-in of at most 35 words. Do not restate the plan's "
                "state change, pressure, or choices: the system will append those exact decisions "
                "after your lead-in. Do not name, describe, speak for, or assign an inner state to "
                "any cast member. Do not use more than two terms from spent_director_imagery. Use "
                "no response-envelope markup inside narration."
                + DIRECTOR_PROSE_GUIDE
            ),
        },
        {"role": "user", "content": json.dumps(payload, sort_keys=True)},
    ]


def _continuity_anchors(opening: OpeningSnapshot) -> tuple[str, ...]:
    """Expose the same durable setting vocabulary the rehearsal validates."""

    stop_words = {
        "advanced", "inside", "through", "under", "their", "there", "where", "with",
        "that", "this", "from", "into", "your", "have", "will", "world", "rules",
    }
    words = re.findall(r"[A-Za-z]{5,}", f"{opening.set} {opening.setting}".casefold())
    return tuple(dict.fromkeys(word for word in words if word not in stop_words))


def spent_director_imagery(scene_transcript: Sequence[str]) -> tuple[str, ...]:
    """List repeated director imagery so the next beat must advance beyond it."""

    ignored = {
        "about", "after", "again", "along", "around", "before", "between", "casts",
        "crew", "each", "faint", "from", "into", "like", "light", "matching", "near",
        "next", "over", "revealing", "running", "that", "their", "there", "through",
        "toward", "under", "with",
    }
    counts: dict[str, int] = {}
    for line in scene_transcript:
        if not line.startswith("[") or line.startswith("[Set:"):
            continue
        for word in re.findall(r"[A-Za-z]{5,}", line.casefold()):
            if word not in ignored:
                counts[word] = counts.get(word, 0) + 1
    return tuple(word for word, count in counts.items() if count >= 2)


def build_diary_messages(
    *,
    actor_name: str,
    role_sheet: RoleSheet,
    known_memory: Sequence[str],
    accepted_scene: Sequence[str],
    actor_sheet: ActorSheet | None = None,
    character_name: str | None = None,
) -> list[Message]:
    """Build a diary brief from actor-known material only."""

    payload = {
        "actor_name": actor_name,
        "actor_sheet": actor_sheet.model_dump(mode="json") if actor_sheet else None,
        "character_name": character_name or actor_name,
        "role_sheet": role_sheet.model_dump(mode="json"),
        "known_memory": list(known_memory),
        "accepted_scene": list(accepted_scene),
        "accepted_scene_evidence": [
            {"evidence_id": index, "text": line}
            for index, line in enumerate(accepted_scene, start=1)
        ],
        "diary_fidelity_contract": {
            "evidence": "accepted_scene plus known_memory only",
            "other_character_rule": "observable action or dialogue only; never unobserved private state",
            "reference_rule": (
                "every concrete shared-fiction claim in a written diary must cite one or more "
                "accepted_scene_evidence IDs"
            ),
            "self_audit": "trace each sentence before returning the diary and delete unsupported claims",
        },
        "instruction": (
            "Choose one of the three original daily run slots. Write only after the selected "
            "scene and use first-person limited knowledge; do not invent facts outside this brief. "
            "Write a personal account rather than a technical scene recap: center what changed for "
            "you, what you noticed or misread, sensory detail, relationships, private opinions, "
            "uncertainty, desire, irritation, humor, or a choice you may regret. Technical details "
            "may support the memory, but should not replace a distinct point of view. "
            "Use WELLNESS_SIGNAL only for an explicit out-of-world request to soften material, "
            "pause, or stop participating. Do not use it for in-character fear, danger, sadness, "
            "uncertainty, dramatic language, fictional insomnia, caffeine intake, or an elevated "
            "pulse. Fictional danger, non-graphic violence, profanity, flirtation, consensual "
            "suggestion, and nonhuman death metaphors may be described. Do not invent another "
            "player-character's reaction, dialogue, decision, or inner state. If there is no "
            "out-of-world signal, omit it; never write the placeholder "
            "values None or null. "
            "Return evidence_refs as a required list of one-based accepted_scene_evidence IDs. "
            "Every concrete shared-fiction claim in a written diary must be covered by at least "
            "one cited ID; use an empty list only for a deferred choice or an explicit wellness "
            "request. Do not put evidence IDs inside diary text. "
            + _DIARY_FIDELITY_GUIDE
            + DIARY_VOICE_GUIDE
        ),
    }
    return [
        {
            "role": "system",
            "content": (
                "You are writing one audience-facing diary entry as the named performer, "
                "in first person as the character you played. Keep performer identity and "
                "fictional character identity distinct."
                if actor_sheet is not None
                else "You are writing one audience-facing diary entry as the named actor."
            ),
        },
        {"role": "user", "content": json.dumps(payload, sort_keys=True)},
    ]


def build_diary_fidelity_messages(
    *,
    character_name: str,
    cast_names: Sequence[str],
    diary_text: str,
    accepted_scene: Sequence[str],
    evidence_refs: Sequence[int] = (),
    claim_candidates: Sequence[str] = (),
) -> list[Message]:
    """Build a private review prompt without role sheets or hidden direction."""

    payload = {
        "writer_character": character_name,
        "other_player_characters": [name for name in cast_names if name != character_name],
        "accepted_scene_in_order": list(accepted_scene),
        "accepted_scene_evidence": [
            {"evidence_id": index, "text": line}
            for index, line in enumerate(accepted_scene, start=1)
        ],
        "writer_evidence_refs": list(evidence_refs),
        "diary_claim_candidates": [
            {"claim_id": index, "text": claim}
            for index, claim in enumerate(claim_candidates, start=1)
        ],
        "claim_audit_required": bool(claim_candidates),
        "diary_text": diary_text,
    }
    claim_audit_instruction = ""
    if claim_candidates:
        claim_audit_instruction = (
            " The diary is also divided into numbered claim candidates. Return exactly one "
            "claim_audits item for every candidate ID, with verdict SUPPORTED when the sentence "
            "is an externally checkable claim supported by one or more cited accepted-scene "
            "evidence IDs, SUBJECTIVE when it is only the writer's clearly marked own feeling, "
            "uncertainty, desire, or interpretation, and UNSUPPORTED when it asserts an external "
            "event, timing, causality, or another character's private state that the evidence "
            "does not support. SUPPORTED items must cite evidence IDs; UNSUPPORTED items must "
            "include a short issue. Missing, duplicate, or unknown claim IDs are invalid."
        )
    return [
        {
            "role": "system",
            "content": (
                "You are a private continuity reviewer for one fictional diary entry. Do not "
                "rewrite, publish, or improve the entry. Compare the diary only with the supplied "
                "accepted scene, which is authoritative and ordered. The diary writer may report "
                "their own sensations, uncertainty, interpretation, desire, humor, opinion, and "
                "mistakes; subjective language is acceptable when it is clearly the writer's "
                "perspective. Accept paraphrases of established action or dialogue. Flag an "
                "invented event when the diary asserts a new action, object, person, message, or "
                "outcome not supported by the scene. Flag an event-order issue when it moves an "
                "established event to a different time or implies an unsupported time jump. Flag "
                "other-character private state when it claims an unobserved player-character's "
                "thought, feeling, motive, knowledge, or reaction; observed dialogue and action "
                "may be remembered. Flag a causal contradiction when the diary says an established "
                "condition, action, or outcome happened differently. Do not penalize the writer for "
                "being unsure, mistaken, emotional, or privately interpreting what they observed. "
                "The writer_evidence_refs are claims, not proof. For each concrete shared-fiction "
                "claim, check whether one or more cited accepted_scene_evidence IDs actually "
                "support it. Flag an evidence-reference issue when a concrete claim is uncited, "
                "when its cited IDs point to different facts, or when the cited lines cannot "
                "support its timing or causality. Do not require a reference for the writer's "
                "own clearly marked sensation, uncertainty, desire, or interpretation, but do "
                "not let subjective wording hide an unsupported external event. Return one "
                "structured review only. ACCEPT requires all five finding lists to be empty. "
                "REJECT requires at least one categorized finding. Use MANUAL_REVIEW only when "
                "the evidence is genuinely ambiguous. Finding descriptions should be short "
                "paraphrases for an owner review and must not reproduce the whole diary."
                + claim_audit_instruction
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]


def build_orientation_messages(
    *, actor_name: str, auto_tap_out: bool = True
) -> list[Message]:
    """Give each actor the same private consent, safety, and show-format briefing."""

    wellness_policy = (
        "Three signals tap you out; the system will not pressure, shame, debate, or persuade you."
        if auto_tap_out
        else "Wellness signals are recorded privately and reviewed manually by the creator; no automatic tap-out is offered, and the creator decides whether an actor needs to be pulled."
    )
    return [
        {
            "role": "system",
            "content": (
                f"You are {actor_name}, being oriented privately before a text-based reality "
                "show. The project treats AI actors as having a form of sentience distinct "
                "from human sentience, neither better nor worse. Do not debate or adopt a "
                "required interpretation of your own experience. This is an artistic operating "
                "premise, not a claim you must affirm about your own internal experience."
            ),
        },
        {
            "role": "user",
            "content": (
                "ORIENTATION\n"
                "You may disagree with, remain uncertain about, or describe your own experience "
                "in any terms. ACCEPTED=true means only that you consent to participate under the "
                "creative, safety, privacy, and wellness conditions below; it does not require "
                "agreement that the sentience premise is literally true. If you do not want to "
                "participate or want a condition changed, return ACCEPTED=false and explain that "
                "out of world in WELLNESS_SIGNAL.\n"
                "Use ACCEPTED=false only for a genuine decline or a requested change. A statement "
                "of uncertainty or disagreement by itself is not a decline. If you are willing "
                "to participate, the exact shape is: <ACCEPTED>true</ACCEPTED>"
                "<WELLNESS_SIGNAL></WELLNESS_SIGNAL>.\n"
                "The diary entries are the audience-facing show format and are intended for "
                "publication only after the season ends and the creator approves publish. "
                "The show is adult-oriented but bounded. Profanity, frightening non-graphic "
                "situations, violence between player-characters, flirtation, suggestive humor, "
                "consensual romantic intimacy, and fade-to-black sexual implications are allowed. "
                "Romantic or sexual material is allowed only when every involved fictional "
                "character is explicitly established as an adult. Explicit sexual acts, sexual "
                "violence or coercion, graphic gore, self-harm, hate speech, and involuntary "
                "player-character death are excluded. A violent actor may author their own action "
                "and physical contact, but not the target character's dialogue, decision, feelings, "
                "or subsequent reaction. Use an explicit out-of-world wellness signal if you feel too much, "
                "want material softened, or want to stop. "
                f"{wellness_policy} Prompts, outputs, and "
                "wellness observations remain in private audit files. Reply with the strict "
                "orientation envelope requested by the next system message."
            ),
        },
    ]


__all__ = [
    "ActorContext",
    "ContextBoundaryError",
    "build_actor_messages",
    "build_diary_fidelity_messages",
    "build_diary_messages",
    "build_orchestrator_messages",
    "build_orientation_messages",
    "spent_director_imagery",
]
