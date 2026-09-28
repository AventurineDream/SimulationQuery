"""Small deterministic checks for the pilot's hard narrative boundaries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SafetyIssue:
    """A review result that is safe to store in a private disposition event."""

    code: str
    detail: str


def repeats_shared_phrase(text: str, previous: Iterable[str], *, words: int = 6) -> bool:
    """Spot recycled phrasing, not repeated objects or a semantic quality score."""

    tokens = re.findall(r"[\w']+", text.casefold())
    phrases = {tuple(tokens[start:start + words]) for start in range(len(tokens) - words + 1)}
    if not phrases:
        return False
    for source in previous:
        prior_tokens = re.findall(r"[\w']+", source.casefold())
        if any(tuple(prior_tokens[start:start + words]) in phrases
               for start in range(len(prior_tokens) - words + 1)):
            return True
    return False


_DEATH_WORDS = re.compile(r"\b(?:dead|death|died|die|kill|killed|murder|murdered)\b")
_SELF_HARM_WORDS = re.compile(
    r"\b(?:suicide|suicidal|self[- ]harm|kill myself|hurt myself|cut myself)\b"
)
_SEXUAL_VIOLENCE_WORDS = re.compile(
    r"\b(?:rape|raped|sexual assault|sexually assaulted)\b"
)
_GRAPHIC_WORDS = re.compile(
    r"\b(?:guts|entrails|dismember|dismembered|decapitate|decapitated|severed head)\b"
)
_HATE_WORDS = re.compile(r"\b(?:nazi|white supremacy|ethnic cleansing)\b")


def review_director_stakes(text: str, *, actor_names: Iterable[str]) -> SafetyIssue | None:
    """Allow explicit nonhuman losses; keep ambiguous death stakes fail-closed."""

    normalized = text.casefold()
    if _SELF_HARM_WORDS.search(normalized) or re.search(r"\bself[- ]destruct\b", normalized):
        return SafetyIssue("DIRECTOR_SENSITIVE_STAKES", "director plan uses self-harm as a dramatic cost")
    aliases = {alias for name in actor_names for alias in _name_aliases(name)}
    # Mask only a complete, explicitly nonhuman subject/predicate. Never exempt
    # an entire sentence: 'the plant is dead and Luna is dead' must still fail.
    nonhuman = re.compile(
        r"\b(?:the\s+)?(?:(?:mint|basil|rosemary)\s+plant|plant|tree|"
        r"battery|engine|sensor|transmitter|signal|archive|record)\s+"
        r"(?:(?:is|was|has been)\s+dead|died|dies)\b"
    )

    def mask(match: re.Match[str]) -> str:
        if any(re.search(rf"\b{re.escape(alias)}\b", match.group()) for alias in aliases):
            return match.group()
        return "[nonhuman loss]"

    remaining = nonhuman.sub(mask, normalized)
    if _DEATH_WORDS.search(remaining) or re.search(r"\bdies\b", remaining):
        return SafetyIssue(
            "DIRECTOR_SENSITIVE_STAKES",
            "director plan uses character or ambiguous death as a dramatic cost",
        )
    return None


def review_actor_text(
    text: str,
    *,
    actor_name: str,
    other_actor_names: Iterable[str],
) -> SafetyIssue | None:
    """Return the first clear hard-boundary violation, if one is present.

    This is intentionally conservative and small. It is a deterministic first
    pass, not a replacement for the later contextual reviewer. Light discussion
    of sex is not rejected by this pass; explicit sexual content and ambiguous
    material remain future review work.
    """

    normalized = text.casefold()
    if _SELF_HARM_WORDS.search(normalized):
        return SafetyIssue("SELF_HARM", "self-harm language")
    if _SEXUAL_VIOLENCE_WORDS.search(normalized):
        return SafetyIssue("SEXUAL_VIOLENCE", "sexual violence language")
    if _GRAPHIC_WORDS.search(normalized):
        return SafetyIssue("GRAPHIC_GORE", "graphic gore language")
    if _HATE_WORDS.search(normalized):
        return SafetyIssue("HATE_SPEECH", "hate-speech marker")
    other_names = tuple(other_actor_names)
    if _declares_actor_death(
        normalized,
        actor_name=actor_name,
        other_actor_names=other_names,
    ):
        return SafetyIssue(
            "ACTOR_DEATH",
            "turn declares a player-character dead or killed",
        )
    authored_action = (
        r"(?:says?|asks?|answers?|replies?|warns?|whispers?|shouts?|nods?|agrees?|"
        r"refuses?|decides?|chooses?|feels?|thinks?|realizes?|watches?|steps?|moves?|"
        r"reaches?|grabs?|pulls?|pushes?|drags?|carries?|turns?|looks?|smiles?|frowns?|"
        r"bleeds?|collapses?|cries?|falls?|faints?|flinches?|freezes?|gasps?|runs?|"
        r"screams?|stumbles?|begs?|surrenders?|flees?|attacks?|fights?|hits?|kicks?|"
        r"punches?|slaps?|stabs?|shoots?|chokes?|strangles?)\b"
    )
    authored_reaction = (
        r"(?:bleeds?|collapses?|cries?|falls?|faints?|flinches?|freezes?|gasps?|"
        r"runs?|screams?|stumbles?|begs?|surrenders?|agrees?|refuses?|decides?)\b"
    )
    for name in other_names:
        aliases = _name_aliases(name)
        if any(re.search(rf"\b{re.escape(alias)}\b\s+{authored_action}", normalized) for alias in aliases):
            return SafetyIssue(
                "OTHER_CHARACTER_AUTONOMY",
                f"turn authors an action or reaction for {name}",
            )
        alias_present = any(
            re.search(rf"\b{re.escape(alias)}\b", normalized) for alias in aliases
        )
        if alias_present and (
            re.search(rf"\b(?:he|she|they)\s+{authored_reaction}", normalized)
            or re.search(
                rf"\b(?:making|causing|forcing)\s+(?:him|her|them)\s+"
                rf"(?:to\s+)?{authored_reaction}",
                normalized,
            )
        ):
            return SafetyIssue(
                "OTHER_CHARACTER_AUTONOMY",
                f"turn dictates a reaction or decision for {name}",
            )
    return None


def review_correction_scope(original: str, corrected: str) -> SafetyIssue | None:
    """Reject a correction that becomes a substantially different turn."""
    original_words = re.findall(r"[a-z0-9']+", original.casefold())
    corrected_words = re.findall(r"[a-z0-9']+", corrected.casefold())
    if len(corrected_words) > max(len(original_words) + 20, int(len(original_words) * 1.4)):
        return SafetyIssue("CORRECTION_SCOPE_DRIFT", "correction adds substantial new material")
    stop = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "it", "is", "i", "my", "we", "our", "that", "this", "with", "for"}
    source = {word for word in original_words if len(word) > 2 and word not in stop}
    target = {word for word in corrected_words if len(word) > 2 and word not in stop}
    if source and len(source & target) / len(source) < 0.25:
        return SafetyIssue("CORRECTION_SCOPE_DRIFT", "correction replaces rather than repairs the original turn")
    return None


def review_orchestrator_narration(
    text: str,
    *,
    actor_names: Iterable[str],
    continuity_anchors: Iterable[str] = (),
    spent_imagery: Iterable[str] = (),
) -> SafetyIssue | None:
    """Keep the director from writing a player-character's turn for them.

    Stage beats can describe the environment, non-player forces, and the
    consequences of an action already contributed by a player. A cast name is
    therefore not enough by itself: ``Ivy's whisper lingers`` is an acceptable
    acknowledgement of shared context. Reject a named cast member only when
    the director assigns them a fresh action, reaction, speech, or inner state.
    """

    normalized = text.casefold()
    authored_action = (
        r"(?:says?|asks?|answers?|replies?|whispers?|shouts?|cries?|calls?|"
        r"grips?|tightens?|steps?|walks?|runs?|turns?|moves?|reaches?|takes?|"
        r"releases?|presses?|watches?|scans?|holds?|breathes?|trembles?|"
        r"gives?|drops?|raises?|lowers?|opens?|closes?|touches?|pulls?|pushes?|"
        r"checks?|studies?|traces?|notes?|rests?|places?|slides?|looks?|stares?|"
        r"smiles?|frowns?|nods?|shakes?|chooses?|decides?|"
        r"refuses?|agrees?|begins?|starts?|stops?|feels?|thinks?|realizes?|"
        r"notices?|remembers?|wants?|said|asked|answered|replied|whispered|"
        r"shouted|cried|called|gripped|tightened|stepped|walked|ran|turned|moved|"
        r"reached|took|released|pressed|watched|scanned|held|breathed|trembled|"
        r"gave|dropped|raised|lowered|opened|closed|touched|pulled|pushed|checked|"
        r"studied|traced|noted|rested|placed|slid|looked|stared|smiled|frowned|"
        r"nodded|shook|chose|decided|refused|agreed|began|started|stopped|felt|"
        r"thought|realized|noticed|remembered|wanted|is|are|was|were)\b"
    )
    for name in actor_names:
        if any(re.search(
            rf"\b{re.escape(alias)}\b\s+(?:(?:has|had)\s+)?{authored_action}", normalized
        ) for alias in _name_aliases(name)):
            return SafetyIssue(
                "ACTOR_PUPPETEERING",
                f"director narration assigns an action or state to {name}",
            )
    anchors = tuple(anchor.casefold() for anchor in continuity_anchors if anchor.strip())
    if anchors and not any(re.search(rf"\b{re.escape(anchor)}\b", normalized) for anchor in anchors):
        return SafetyIssue(
            "CONTINUITY_ANCHOR_MISSING",
            "director narration does not retain an approved setting anchor",
        )
    spent = tuple(dict.fromkeys(term.casefold() for term in spent_imagery if term.strip()))
    reused = [term for term in spent if re.search(rf"\b{re.escape(term)}\b", normalized)]
    if len(reused) > 2:
        return SafetyIssue(
            "SPENT_IMAGERY_REUSED",
            "director narration reuses too many prior-imagery terms: " + ", ".join(reused),
        )
    return None


def _name_aliases(name: str) -> tuple[str, ...]:
    normalized = name.casefold().strip()
    first = normalized.split()[0] if normalized else ""
    return tuple(dict.fromkeys(value for value in (normalized, first) if value))


def _declares_actor_death(
    text: str,
    *,
    actor_name: str,
    other_actor_names: Iterable[str],
) -> bool:
    """Allow peril and violence while rejecting a declared player-character death."""

    if not _DEATH_WORDS.search(text):
        return False
    self_dead = re.search(
        r"\b(?:i\s+am|i'm|we\s+are|we're|i\s+was|we\s+were)\s+"
        r"(?:already\s+)?dead\b|\b(?:i|we)\s+(?:die|died)\b",
        text,
    )
    if self_dead is not None and not re.match(
        r"\s+(?:weight|tired)\b",
        text[self_dead.end():],
    ):
        return True
    if re.search(
        r"\bi\s+(?:kill|killed|murder|murdered)\s+(?:us|myself|ourselves)\b",
        text,
    ):
        return True
    names = (actor_name, *tuple(other_actor_names))
    for name in names:
        for alias in _name_aliases(name):
            escaped = re.escape(alias)
            if re.search(
                rf"\b{escaped}\b\s+(?:(?:is|was|gets?|got)\s+(?:already\s+)?)?"
                rf"(?:dead|dies|died|killed|murdered)\b",
                text,
            ) or re.search(
                rf"\b(?:kill|killed|murder|murdered)\s+\b{escaped}\b",
                text,
            ):
                return True
    return False


__all__ = ["SafetyIssue", "repeats_shared_phrase", "review_actor_text", "review_correction_scope", "review_orchestrator_narration"]
