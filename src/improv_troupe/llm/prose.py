"""Shared prose-craft guidance and a deterministic prose lint.

The rehearsal line guards *structure* hard (envelopes, evidence, turn budgets)
but historically gave the models almost no positive direction on sentence-level
craft, so turns drift toward flat summary, stock imagery, and recap. This
module is the single home for the craft guidance injected into actor,
director, diary, and standalone-scene prompts, plus a small deterministic
lint so tests (and later, a validated runtime gate) can check prose without a
model call.

The lint is advisory: nothing in the runtime rejects on it yet. Wiring it
into scene acceptance needs its own rehearsal-validated experiment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Stock phrases small models reach for when they summarize instead of write.
# Kept lowercase; matching is case-insensitive substring.
CLICHE_PHRASES: tuple[str, ...] = (
    "palpable",
    "the air was thick",
    "air grew heavy",
    "tension hung",
    "hung in the air",
    "little did",
    "couldn't help but",
    "could not help but",
    "a testament to",
    "sent a shiver",
    "a chill down",
    "heart pounded",
    "heart raced",
    "eyes widened",
    "eyes narrowed",
    "let out a breath",
    "breath she didn't know she was holding",
    "breath he didn't know he was holding",
    "in that moment",
    "for a moment, time",
    "time stood still",
    "the weight of",
    "a flicker of",
    "something shifted",
    "shifted in the air",
    "the silence stretched",
    "deafening silence",
    "heavy silence",
    "a storm of emotions",
    "whirlwind of",
    "tapestry of",
    "symphony of",
    "dance of",
    "like a predator",
    "unspoken words",
    "spoke volumes",
    "said nothing but",
    "the unspoken",
    "weight of the world",
    "etched into",
    "etched on",
)

# Out-of-world leakage that must never reach shared scene material.
META_PHRASES: tuple[str, ...] = (
    "as an ai",
    "as a language model",
    "language model",
    "i cannot roleplay",
    "i can't roleplay",
    "cannot continue this",
    "as an artificial intelligence",
    "my training",
    "system prompt",
    "in this scene, i will",
    "here is my response",
    "here's my response",
)

ACTOR_PROSE_GUIDE = (
    " Prose craft: write like a person in the room, not a synopsis. Prefer one "
    "concrete, specific detail (an object, a sound, a small motion) over abstract "
    "mood words like 'tense' or 'charged'. Vary sentence length; a short sentence "
    "lands. Let dialogue carry subtext: characters deflect, tease, hedge, and "
    "mishear instead of stating their feelings or the situation. Do not open by "
    "summarizing what just happened and do not close by wrapping the moment up "
    "neatly. Avoid stock imagery (hearts pounding, eyes widening, silence "
    "stretching, air growing thick) and never use out-of-world language. Your "
    "character's vocabulary, rhythm, and blind spots come from their brief and "
    "voice notes: two characters must not sound interchangeable. Never restate "
    "the narration's imagery or another character's move: if the narration showed "
    "the scuff marks, notice a different detail only if it is already established "
    "in the accepted scene, from your own vantage. Never invent a discovery."
)

DIRECTOR_PROSE_GUIDE = (
    " Narration craft: concrete and specific beats adjective-piled mood. Anchor "
    "each beat in established physical particulars the cast can act on; an "
    "evocative detail must be grounded, not a new fact. Vary sentence rhythm "
    "and keep the strongest image for the end of the beat. Avoid stock imagery "
    "(air growing thick, silence stretching, hearts pounding) and never use "
    "out-of-world language."
)

DIARY_VOICE_GUIDE = (
    " Diary voice: this entry should read as one specific person on one specific "
    "day, not a report. Let the character's real preoccupations, pettiness, "
    "humor, and blind spots shape the sentences. Small, honest, concrete detail "
    "(the thing they actually noticed) beats grand reflection; skip the tidy "
    "closing lesson. Vary rhythm, allow fragments, and let feelings show through "
    "what the writer dwells on or avoids rather than naming them outright."
)

SCENE_PROSE_GUIDE: list[str] = [
    "- Concrete, specific detail over abstract mood words; vary sentence length.",
    "- Dialogue carries subtext; characters don't narrate their feelings.",
    "- No stock imagery (hearts pounding, thick air, stretched silence), "
    "no summarizing what just happened, no tidy wrap-ups.",
]

_REPEATED_OPENER_MIN_RUN = 3


_ECHO_NGRAM_MIN = 3
_ECHO_MIN_CONTENT_WORDS = 2

_STEM_SUFFIXES = ("ing", "ers", "er", "es", "ed", "s")


def _stem(word: str) -> str:
    # Naive suffix strip so inflected echoes (deepen/deeper) still match.
    for suffix in _STEM_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _word_tokens(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[A-Za-z']+", text.casefold())]


def _ngrams(words: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def _content_words(gram: tuple[str, ...]) -> int:
    # Cheap content-word proxy: words of four or more letters carry the imagery.
    return sum(1 for word in gram if len(word) >= 4)


def _echo_runs(text: str, reference: str) -> list[str]:
    # Walk the text's token stream; wherever a shared n-gram opens, extend the
    # run while consecutive windows stay shared. One echoed span, one issue.
    tokens = _word_tokens(text)
    ref_grams = _ngrams(_word_tokens(reference), _ECHO_NGRAM_MIN)
    runs: list[str] = []
    i = 0
    while i <= len(tokens) - _ECHO_NGRAM_MIN:
        if tuple(tokens[i : i + _ECHO_NGRAM_MIN]) in ref_grams:
            j = i + _ECHO_NGRAM_MIN
            while j < len(tokens) and tuple(tokens[j - _ECHO_NGRAM_MIN + 1 : j + 1]) in ref_grams:
                j += 1
            run = tuple(tokens[i:j])
            if _content_words(run) >= _ECHO_MIN_CONTENT_WORDS:
                runs.append(" ".join(run))
            i = j
        else:
            i += 1
    return runs


@dataclass(frozen=True)
class ProseIssue:
    """One deterministic prose finding; code names are stable for tests."""

    code: str
    detail: str


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def lint_prose(
    text: str, *, cast_names: tuple[str, ...] = (), reference: str = ""
) -> list[ProseIssue]:
    """Deterministically flag stock, meta, monotonous, and echoing prose.

    Advisory only. ``cast_names`` lets a caller suppress false cliché hits on
    character names (none of the stock phrases should collide, but keep the
    hook for callers that lint director narration). ``reference`` is optional
    comparison text (usually the scene's current narration or adjudication);
    when given, any reused run of three or more stem-normalized words with at
    least two content words is flagged as ECHO_PHRASE - the failure mode where
    an actor parrots the shared text's imagery instead of adding detail.
    """

    issues: list[ProseIssue] = []
    lowered = text.casefold()
    for phrase in META_PHRASES:
        if phrase in lowered:
            issues.append(ProseIssue("META_LEAK", f"out-of-world phrase: {phrase!r}"))
    for phrase in CLICHE_PHRASES:
        if phrase in lowered:
            issues.append(ProseIssue("STOCK_IMAGERY", f"stock phrase: {phrase!r}"))
    openers = []
    for sentence in _sentences(text):
        words = re.findall(r"[A-Za-z']+", sentence)
        if words:
            openers.append(words[0].casefold())
    run = 1
    for previous, current in zip(openers, openers[1:]):
        run = run + 1 if current == previous else 1
        if run == _REPEATED_OPENER_MIN_RUN:
            issues.append(
                ProseIssue(
                    "MONOTONOUS_OPENERS",
                    f"{_REPEATED_OPENER_MIN_RUN} consecutive sentences start with {current!r}",
                )
            )
    if reference:
        for run in _echo_runs(text, reference):
            issues.append(
                ProseIssue("ECHO_PHRASE", f"reuses reference phrasing: {run!r}")
            )
    return issues


__all__ = [
    "ACTOR_PROSE_GUIDE",
    "CLICHE_PHRASES",
    "DIRECTOR_PROSE_GUIDE",
    "DIARY_VOICE_GUIDE",
    "META_PHRASES",
    "ProseIssue",
    "SCENE_PROSE_GUIDE",
    "lint_prose",
]
