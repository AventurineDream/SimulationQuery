"""Strict response envelopes for actor and orchestrator model calls."""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, model_validator

from ..domain.magic import MagicAttribute, MagicCostType


class StructuredOutputError(ValueError):
    """Raised when neither native JSON nor the strict tagged format parses."""


class ActorTurnEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["actor_turn"] = "actor_turn"
    text: str = Field(min_length=1, max_length=750)
    wellness_signal: str | None = Field(default=None, max_length=400)
    memory_notes: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(
        default_factory=list, max_length=2
    )
    diary_intent: bool = False
    magic_stat: MagicAttribute | None = None
    magic_method: str | None = Field(default=None, max_length=320)

    @model_validator(mode="after")
    def magic_method_matches_selected_stat(self) -> "ActorTurnEnvelope":
        if self.magic_stat is None and self.magic_method is not None:
            raise ValueError("MAGIC_METHOD requires a selected MAGIC_STAT")
        if self.magic_stat is not None and not (self.magic_method or "").strip():
            raise ValueError("a MAGIC attempt requires a separate MAGIC_METHOD")
        return self

    @model_validator(mode="after")
    def shared_text_must_not_contain_envelope_markup(self) -> "ActorTurnEnvelope":
        """Fail closed when a transport envelope leaks into scene material."""

        if re.search(r"</?[A-Za-z][A-Za-z0-9_:-]*\b[^>]*>", self.text):
            raise ValueError("actor text must not contain envelope markup")
        return self


class OrchestratorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["orchestrator"] = "orchestrator"
    # Two-pass directing compiles the fixed plan, MAGIC receipt, and choices
    # into this internal envelope after the raw renderer has already passed
    # its 720-character bound. Keep the provider-facing render envelope tight;
    # this envelope needs room for the runtime-owned receipt to remain exact.
    narration: str = Field(min_length=1, max_length=1600)
    next_actor: str | None = Field(default=None, max_length=80)
    complete: bool = False
    canon_updates: list[Annotated[str, Field(min_length=1, max_length=180)]] = Field(
        default_factory=list, max_length=2
    )
    magic_challenge: str | None = Field(default=None, max_length=180)
    magic_success_criteria: str | None = Field(default=None, max_length=180)
    magic_modifier: int = Field(default=0, ge=-2, le=2)

    @model_validator(mode="before")
    @classmethod
    def normalize_optional_magic_fields(cls, value: object) -> object:
        return _strip_legacy_magic_adjudication_fields(_normalize_magic_fields(value))

    @model_validator(mode="after")
    def magic_fields_require_a_designated_actor(self) -> "OrchestratorEnvelope":
        if self.magic_challenge is None and self.magic_modifier != 0:
            raise ValueError("a MAGIC modifier requires a declared challenge")
        if self.magic_challenge is not None and self.next_actor is None:
            raise ValueError("a MAGIC challenge requires a designated next_actor")
        if self.magic_challenge is None and self.magic_success_criteria is not None:
            raise ValueError("MAGIC success criteria require a declared challenge")
        return self


class DirectorClockChange(BaseModel):
    """One small, visible change to the scene's game state."""

    model_config = ConfigDict(extra="forbid")

    clock: Literal["mission", "danger", "mystery", "relationship"]
    change: Literal[-1, 1]


class DirectorPlanEnvelope(BaseModel):
    """The private, non-prose adjudication that a director beat must render."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["director_plan"] = "director_plan"
    scene_objective: str = Field(min_length=8, max_length=220)
    adjudication: str = Field(min_length=8, max_length=300)
    state_change: str = Field(min_length=8, max_length=240)
    pressure: str = Field(min_length=8, max_length=240)
    choice_a: str = Field(min_length=5, max_length=180)
    choice_b: str = Field(min_length=5, max_length=180)
    next_actor: str = Field(min_length=1, max_length=80)
    complete: bool = False
    clock_changes: list[DirectorClockChange] = Field(min_length=1, max_length=2)
    canon_updates: list[Annotated[str, Field(min_length=1, max_length=180)]] = Field(
        min_length=1, max_length=2
    )
    magic_challenge: str | None = Field(default=None, max_length=180)
    magic_success_criteria: str | None = Field(default=None, max_length=180)
    magic_modifier: int = Field(default=0, ge=-2, le=2)
    magic_cost_type: MagicCostType | None = Field(
        default=None,
        description="Director consequence input for costly_success only.",
    )
    magic_effect_detail: str | None = Field(
        default=None,
        max_length=180,
        description=(
            "A short observable consequence detail supplied after the runtime resolves the roll."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_optional_magic_challenge(cls, value: object) -> object:
        normalized = _strip_legacy_magic_adjudication_fields(_normalize_magic_fields(value))
        if isinstance(normalized, dict):
            for field_name in (
                "magic_success_criteria",
                "magic_cost_type",
                "magic_effect_detail",
            ):
                optional_value = normalized.get(field_name)
                if isinstance(optional_value, str):
                    if optional_value.strip().casefold() in {
                        "", "none", "null", "n/a", "na", "nil", "false"
                    }:
                        normalized[field_name] = None
                    else:
                        normalized[field_name] = optional_value.strip()
                normalized.setdefault(field_name, None)
        return normalized

    @model_validator(mode="after")
    def choices_must_present_a_real_fork(self) -> "DirectorPlanEnvelope":
        if self.choice_a.casefold().strip() == self.choice_b.casefold().strip():
            raise ValueError("choice_a and choice_b must be distinct")
        if self.magic_challenge is None and self.magic_modifier != 0:
            raise ValueError("a MAGIC modifier requires a declared challenge")
        if self.magic_challenge is None and self.magic_success_criteria is not None:
            raise ValueError("MAGIC success criteria require a declared challenge")
        return self


def _normalize_magic_fields(value: object) -> object:
    if not isinstance(value, dict):
        return value
    normalized = dict(value)
    challenge = normalized.get("magic_challenge")
    if isinstance(challenge, str) and challenge.strip().casefold() in {
        "", "none", "null", "n/a", "na", "nil", "false"
    }:
        normalized["magic_challenge"] = None
    elif isinstance(challenge, str):
        normalized["magic_challenge"] = challenge.strip()
    for field_name in ("magic_success_criteria", "magic_cost_type", "magic_effect_detail"):
        field_value = normalized.get(field_name)
        if isinstance(field_value, str) and field_value.strip().casefold() in {
            "", "none", "null", "n/a", "na", "nil", "false"
        }:
            normalized[field_name] = None
        elif isinstance(field_value, str):
            normalized[field_name] = field_value.strip()
    return normalized


def _strip_legacy_magic_adjudication_fields(value: object) -> object:
    """Ignore pre-boundary outcome fields while reading older artifacts.

    New model responses never receive these fields in their schema.  The
    compatibility strip lets already-accepted plans be replayed without
    allowing stale model-authored tier or answer data to influence the runtime.
    """

    if not isinstance(value, dict):
        return value
    normalized = dict(value)
    for field_name in (
        "magic_result_ack",
        "magic_goal_status",
        "magic_goal_answer",
    ):
        normalized.pop(field_name, None)
    return normalized


class DirectorRenderEnvelope(BaseModel):
    """The public-facing prose rendered from a validated director plan."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["director_render"] = "director_render"
    narration: str = Field(max_length=720)

    @model_validator(mode="after")
    def narration_has_no_markup(self) -> "DirectorRenderEnvelope":
        if re.search(r"</?[A-Za-z][A-Za-z0-9_:-]*\b[^>]*>", self.narration):
            raise ValueError("director narration must not contain envelope markup")
        return self


class EpisodeResolutionEnvelope(BaseModel):
    """Director adjudication after the cast has made the final choices."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["episode_resolution"] = "episode_resolution"
    outcome: Literal["SUCCESS", "COSTLY_SUCCESS", "COSTLY_FAILURE", "FAILURE"]
    central_question_answered: str = Field(min_length=8, max_length=240)
    narration: str = Field(min_length=20, max_length=1200)
    irreversible_change: str = Field(min_length=8, max_length=240)
    gained: str = Field(min_length=3, max_length=180)
    lost: str = Field(min_length=3, max_length=180)
    hook: str | None = Field(default=None, max_length=180)
    canon_updates: list[Annotated[str, Field(min_length=1, max_length=180)]] = Field(
        min_length=2, max_length=4
    )
    complete: Literal[True]


class DiaryEnvelope(BaseModel):
    """One actor's first-attempt diary decision and optional entry."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["diary"] = "diary"
    chosen_slot_number: int = Field(ge=1, le=3)
    write_now: bool
    text: str
    evidence_refs: list[StrictInt] = Field(
        max_length=16,
        description=(
            "One-based IDs from the supplied accepted_scene_evidence. Empty is allowed only "
            "for a deferred choice or an explicit wellness request."
        ),
    )
    wellness_signal: str | None = None

    @model_validator(mode="after")
    def writing_now_requires_text_or_a_wellness_signal(self) -> "DiaryEnvelope":
        """Do not accept an empty diary as a completed writing decision."""

        if self.write_now and not self.text.strip() and not self.wellness_signal:
            raise ValueError("write_now requires diary text or a wellness signal")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("diary evidence references must be unique")
        if any(reference < 1 for reference in self.evidence_refs):
            raise ValueError("diary evidence references must be positive")
        if self.write_now and self.text.strip() and not self.evidence_refs and not self.wellness_signal:
            raise ValueError("a written diary must cite accepted scene evidence")
        return self


class DiaryClaimAudit(BaseModel):
    """One sentence-level claim classification in a private diary review."""

    model_config = ConfigDict(extra="forbid")

    claim_id: StrictInt = Field(ge=1)
    verdict: Literal["SUPPORTED", "SUBJECTIVE", "UNSUPPORTED", "MIXED"]
    evidence_refs: list[StrictInt] = Field(default_factory=list, max_length=16)
    issue: str | None = Field(default=None, max_length=240)

    @model_validator(mode="after")
    def verdict_requires_the_right_receipt(self) -> "DiaryClaimAudit":
        if self.verdict == "SUPPORTED" and not self.evidence_refs:
            raise ValueError("a supported claim must cite accepted scene evidence")
        if self.verdict in {"UNSUPPORTED", "MIXED"} and not self.issue:
            raise ValueError("an unsupported or mixed claim must describe its issue")
        return self


class DiaryFidelityEnvelope(BaseModel):
    """A private continuity review of one diary against the accepted scene."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["diary_fidelity_review"] = "diary_fidelity_review"
    decision: Literal["ACCEPT", "REJECT", "MANUAL_REVIEW"]
    summary: str = Field(min_length=1, max_length=360)
    invented_events: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(
        default_factory=list, max_length=4
    )
    other_character_private_states: list[
        Annotated[str, Field(min_length=1, max_length=240)]
    ] = Field(default_factory=list, max_length=4)
    event_order_issues: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(
        default_factory=list, max_length=4
    )
    causal_contradictions: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(
        default_factory=list, max_length=4
    )
    evidence_reference_issues: list[
        Annotated[str, Field(min_length=1, max_length=240)]
    ] = Field(default_factory=list, max_length=4)
    claim_audits: list[DiaryClaimAudit] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def decision_must_match_findings(self) -> "DiaryFidelityEnvelope":
        """Require a categorized reason for rejection and no hidden reasons for acceptance."""

        has_findings = any(
            (
                self.invented_events,
                self.other_character_private_states,
                self.event_order_issues,
                self.causal_contradictions,
                self.evidence_reference_issues,
            )
        )
        has_blocking_claim_audit = any(
            audit.verdict in {"UNSUPPORTED", "MIXED"} for audit in self.claim_audits
        )
        if self.decision == "ACCEPT" and has_findings:
            raise ValueError("an accepted diary review cannot contain fidelity findings")
        if self.decision == "REJECT" and not has_findings and not has_blocking_claim_audit:
            raise ValueError(
                "a rejected diary review requires a categorized finding or a blocking claim audit"
            )
        return self


class OrientationEnvelope(BaseModel):
    """A private orientation response before a character enters performance."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["orientation"] = "orientation"
    accepted: bool = False
    wellness_signal: str | None = None


class PrivatePlanEnvelope(BaseModel):
    """Bounded JSON used only while constructing a private rehearsal plan."""

    model_config = ConfigDict(extra="forbid")

    premise: str = Field(min_length=1, max_length=800)
    planned_tensions: list[str] = Field(min_length=1, max_length=4)
    hidden_mysteries: list[str] = Field(default_factory=list, max_length=3)


class RoleSheetEnvelope(BaseModel):
    """Provider-facing bounded form of a private role sheet."""

    model_config = ConfigDict(extra="forbid")

    character_id: str = Field(min_length=1)
    objectives: list[str] = Field(min_length=1, max_length=2)
    boundaries: list[str] = Field(min_length=1, max_length=2)
    knowledge: list[str] = Field(min_length=1, max_length=2)
    relationships: list[str] = Field(min_length=1, max_length=3)
    secrets: list[str] = Field(min_length=1, max_length=2)
    play_style: str = Field(min_length=1, max_length=320)
    voice_guidance: str = Field(min_length=1, max_length=480)
    version: int = Field(default=1, ge=1, le=1)


Envelope = TypeVar(
    "Envelope",
    ActorTurnEnvelope,
    OrchestratorEnvelope,
    DirectorPlanEnvelope,
    DirectorRenderEnvelope,
    EpisodeResolutionEnvelope,
    DiaryEnvelope,
    DiaryFidelityEnvelope,
    OrientationEnvelope,
)


_ACTOR_TAGS = (
    "ACTOR_TEXT", "WELLNESS_SIGNAL", "MEMORY_NOTE", "DIARY_INTENT", "MAGIC_STAT",
    "MAGIC_METHOD",
)


def parse_actor_output(raw: str) -> ActorTurnEnvelope:
    """Parse native JSON, then a strictly bounded actor-tagged fallback.

    Some local models emit a later field after forgetting the closing tag for
    the preceding field.  We may restore only those internal boundaries when
    the later known tag makes the boundary unambiguous; unknown text and a
    missing final close still fail closed. A known MAGIC_STAT tag at either
    boundary of native JSON's text field is moved into its schema field.
    """

    normalized = _normalize_native_actor_magic_tag(raw)
    envelope = _parse(
        _repair_actor_tag_boundaries(normalized), ActorTurnEnvelope, _parse_actor_tags
    )
    return envelope.model_copy(
        update={"wellness_signal": _normalize_optional_signal(envelope.wellness_signal)}
    )


def _normalize_native_actor_magic_tag(raw: str) -> str:
    """Move recognized inline actor metadata out of native actor text.

    Some schema-capable local models obey the requested semantic fields but
    serialize the tagged fallback convention inside ``text``. Normalize one
    recognized MAGIC_STAT tag and bounded ``[Memory: ...]`` labels when the
    corresponding JSON fields are absent. Conflicting fields, unknown
    attributes, and other markup remain subject to the strict parser.
    """

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if not isinstance(decoded, dict) or not isinstance(decoded.get("text"), str):
        return raw
    actor_text = decoded["text"]
    changed = False

    magic_matches = list(
        re.finditer(
            r"<MAGIC_STAT>\s*(?P<attribute>.*?)\s*</MAGIC_STAT>",
            actor_text,
            flags=re.DOTALL | re.IGNORECASE,
        )
    )
    if magic_matches:
        if decoded.get("magic_stat") is not None or len(magic_matches) != 1:
            return raw
        attribute = _normalize_magic_attribute(magic_matches[0].group("attribute"))
        if not isinstance(attribute, MagicAttribute):
            return raw
        actor_text = (
            actor_text[: magic_matches[0].start()]
            + actor_text[magic_matches[0].end() :]
        )
        decoded["magic_stat"] = attribute.value
        changed = True

    method_matches = list(
        re.finditer(
            r"<MAGIC_METHOD>\s*(?P<method>.*?)\s*</MAGIC_METHOD>",
            actor_text,
            flags=re.DOTALL | re.IGNORECASE,
        )
    )
    if method_matches:
        if decoded.get("magic_method") is not None or len(method_matches) != 1:
            return raw
        method = method_matches[0].group("method").strip()
        if not method:
            return raw
        actor_text = (
            actor_text[: method_matches[0].start()]
            + actor_text[method_matches[0].end() :]
        )
        decoded["magic_method"] = method
        changed = True

    memory_matches = list(
        re.finditer(
            r"\[Memory:\s*(?P<note>[^\]]+?)\s*\]",
            actor_text,
            flags=re.IGNORECASE,
        )
    )
    if memory_matches:
        existing_notes = decoded.get("memory_notes", [])
        if not isinstance(existing_notes, list) or len(existing_notes) + len(memory_matches) > 2:
            return raw
        notes = [match.group("note").strip() for match in memory_matches]
        if any(not note for note in notes):
            return raw
        decoded["memory_notes"] = [*existing_notes, *notes]
        actor_text = re.sub(
            r"\[Memory:\s*(?P<note>[^\]]+?)\s*\]",
            "",
            actor_text,
            flags=re.IGNORECASE,
        )
        changed = True

    if not changed:
        return raw
    actor_text = actor_text.strip()
    if not actor_text:
        return raw
    decoded["text"] = actor_text
    return json.dumps(decoded, ensure_ascii=False)


def parse_orchestrator_output(raw: str) -> OrchestratorEnvelope:
    """Parse native JSON first, then the strict orchestrator tagged fallback."""

    return _parse(
        _repair_orchestrator_tag_typos(raw),
        OrchestratorEnvelope,
        _parse_orchestrator_tags,
    )


def parse_director_plan_output(raw: str) -> DirectorPlanEnvelope:
    """Parse a director's private game-state plan."""

    return _parse(raw, DirectorPlanEnvelope, _parse_director_plan_tags)


def parse_director_render_output(raw: str) -> DirectorRenderEnvelope:
    """Parse prose that must implement a previously accepted director plan."""

    return _parse(raw, DirectorRenderEnvelope, _parse_director_render_tags)


def parse_episode_resolution_output(raw: str) -> EpisodeResolutionEnvelope:
    """Parse the director's terminal adjudication."""

    return _parse(raw, EpisodeResolutionEnvelope, _parse_episode_resolution_tags)


def parse_diary_output(raw: str) -> DiaryEnvelope:
    """Parse native JSON or tagged diary output with safe optional-signal cleanup."""

    envelope = _parse(_repair_diary_tag_boundaries(raw), DiaryEnvelope, _parse_diary_tags)
    try:
        return DiaryEnvelope.model_validate(
            {
                **envelope.model_dump(),
                "wellness_signal": _normalize_optional_signal(envelope.wellness_signal),
            }
        )
    except ValidationError as exc:
        raise StructuredOutputError("diary response required text after wellness normalization") from exc


def parse_diary_fidelity_output(raw: str) -> DiaryFidelityEnvelope:
    """Parse a private diary-fidelity review from JSON or strict tagged fields."""

    return _parse(raw, DiaryFidelityEnvelope, _parse_diary_fidelity_tags)


def parse_orientation_output(raw: str) -> OrientationEnvelope:
    """Parse native JSON first, then strict orientation tags."""

    return _parse(raw, OrientationEnvelope, _parse_orientation_tags)


def schema_for(schema_name: str) -> dict[str, object]:
    """Return the provider-facing JSON Schema for one known response envelope."""

    schemas: dict[str, type[BaseModel]] = {
        "actor_turn": ActorTurnEnvelope,
        "orchestrator": OrchestratorEnvelope,
        "director_plan": DirectorPlanEnvelope,
        "director_render": DirectorRenderEnvelope,
        "episode_resolution": EpisodeResolutionEnvelope,
        "diary": DiaryEnvelope,
        "diary_fidelity_review": DiaryFidelityEnvelope,
        "orientation": OrientationEnvelope,
        "private_plan": PrivatePlanEnvelope,
        "role_sheet": RoleSheetEnvelope,
    }
    try:
        return schemas[schema_name].model_json_schema()
    except KeyError:
        known = ", ".join(sorted(schemas))
        raise ValueError(f"unknown structured schema {schema_name!r}; known: {known}") from None


def _parse(raw: str, model: type[Envelope], fallback) -> Envelope:
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        decoded = None
    if isinstance(decoded, dict):
        try:
            return model.model_validate(decoded)
        except ValidationError:
            pass

    values = fallback(raw)
    if values is None:
        raise StructuredOutputError("response was neither valid JSON nor strict tagged output")
    try:
        return model.model_validate(values)
    except ValidationError as exc:
        raise StructuredOutputError("tagged response failed envelope validation") from exc


def _tag(raw: str, name: str) -> str | None:
    match = re.fullmatch(rf"\s*<{name}>\s*(.*?)\s*</{name}>\s*", raw, flags=re.DOTALL)
    return match.group(1).strip() if match else None


def _tagged_fields(raw: str, names: tuple[str, ...]) -> dict[str, str] | None:
    fields: dict[str, str] = {}
    remainder = raw.strip()
    for name in names:
        pattern = re.compile(rf"<{name}>\s*(.*?)\s*</{name}>", flags=re.DOTALL)
        matches = list(pattern.finditer(remainder))
        if matches:
            fields[name] = matches[0].group(1).strip()
            remainder = pattern.sub("", remainder)
    if remainder.strip():
        return None
    return fields


def _repair_actor_tag_boundaries(raw: str) -> str:
    """Restore only missing internal actor-tag boundaries.

    This handles a response such as ``<ACTOR_TEXT>...<MEMORY_NOTE>...`` by
    inserting ``</ACTOR_TEXT>`` immediately before the known next tag.  It
    never invents a closing tag at end-of-output, removes unknown content, or
    changes JSON responses.
    """

    candidate = raw.strip()
    if not candidate.startswith("<ACTOR_TEXT>"):
        return raw

    repaired = candidate
    changed = False
    for name in _ACTOR_TAGS[:-1]:
        opening = f"<{name}>"
        closing = f"</{name}>"
        search_from = 0
        while True:
            start = repaired.find(opening, search_from)
            if start < 0:
                break
            content_start = start + len(opening)
            close_at = repaired.find(closing, content_start)
            next_positions = [
                position
                for next_name in _ACTOR_TAGS
                if next_name != name
                for position in (repaired.find(f"<{next_name}>", content_start),)
                if position >= 0
            ]
            boundary = min(next_positions, default=-1)
            if boundary < 0:
                break
            if close_at < 0 or close_at > boundary:
                repaired = repaired[:boundary] + closing + repaired[boundary:]
                changed = True
                search_from = boundary + len(closing)
            else:
                search_from = close_at + len(closing)

    return repaired if changed else raw


def _repair_orchestrator_tag_typos(raw: str) -> str:
    """Repair one observed, unambiguous narration closing-tag typo.

    Some local orchestrator responses consistently close ``NARRATION`` as
    ``LARRATION``. Repair only that exact one-opening/one-closing mismatch;
    all other malformed or ambiguous tagged output remains fail-closed.
    """

    candidate = raw.strip()
    if (
        candidate.startswith("<NARRATION>")
        and candidate.count("<NARRATION>") == 1
        and candidate.count("</NARRATION>") == 0
        and candidate.count("</LARRATION>") == 1
    ):
        return raw.replace("</LARRATION>", "</NARRATION>")
    return raw


def _repair_diary_tag_boundaries(raw: str) -> str:
    """Restore only missing internal diary-tag boundaries.

    Local models sometimes begin the next field before closing the previous
    field.  A missing final close still fails closed; only a boundary made
    unambiguous by a later known tag is repaired.
    """

    candidate = raw.strip()
    if not candidate.startswith("<DIARY_SLOT>"):
        return raw

    repaired = candidate
    changed = False
    tags = ("DIARY_SLOT", "WRITE_NOW", "DIARY_TEXT", "EVIDENCE_REFS", "WELLNESS_SIGNAL")
    for name in tags[:-1]:
        opening = f"<{name}>"
        closing = f"</{name}>"
        search_from = 0
        while True:
            start = repaired.find(opening, search_from)
            if start < 0:
                break
            content_start = start + len(opening)
            close_at = repaired.find(closing, content_start)
            next_positions = [
                position
                for next_name in tags
                if next_name != name
                for position in (repaired.find(f"<{next_name}>", content_start),)
                if position >= 0
            ]
            boundary = min(next_positions, default=-1)
            if boundary < 0:
                break
            if close_at < 0 or close_at > boundary:
                repaired = repaired[:boundary] + closing + repaired[boundary:]
                changed = True
                search_from = boundary + len(closing)
            else:
                search_from = close_at + len(closing)

    return repaired if changed else raw


def _parse_actor_tags(raw: str) -> dict[str, object] | None:
    fields = _tagged_fields(
        raw,
        (
            "ACTOR_TEXT", "WELLNESS_SIGNAL", "MEMORY_NOTE", "DIARY_INTENT",
            "MAGIC_STAT", "MAGIC_METHOD",
        ),
    )
    if fields is None or "ACTOR_TEXT" not in fields:
        return None
    return {
        "text": fields["ACTOR_TEXT"],
        "wellness_signal": fields.get("WELLNESS_SIGNAL"),
        "memory_notes": _repeated_tag_values(raw, "MEMORY_NOTE"),
        "diary_intent": _parse_bool(fields.get("DIARY_INTENT"), default=False),
        "magic_stat": _normalize_magic_attribute(fields.get("MAGIC_STAT")),
        "magic_method": fields.get("MAGIC_METHOD"),
    }


def _parse_orchestrator_tags(raw: str) -> dict[str, object] | None:
    fields = _tagged_fields(
        raw,
        (
            "NARRATION",
            "NEXT_ACTOR",
            "COMPLETE",
            "CANON_UPDATE",
            "MAGIC_CHALLENGE",
            "MAGIC_SUCCESS_CRITERIA",
            "MAGIC_MODIFIER",
            # Accepted only so older tagged responses can be replayed; the
            # runtime now owns all result adjudication fields.
            "MAGIC_RESULT_ACK",
        ),
    )
    if fields is None:
        return None
    if "NARRATION" not in fields:
        return None
    modifier = 0
    modifier_text = fields.get("MAGIC_MODIFIER")
    if modifier_text is not None:
        try:
            modifier = int(modifier_text.strip())
        except ValueError as exc:
            raise StructuredOutputError("MAGIC modifier must be an integer") from exc
    return {
        "narration": fields.get("NARRATION", ""),
        "next_actor": fields.get("NEXT_ACTOR"),
        "complete": _parse_bool(fields.get("COMPLETE"), default=False),
        "canon_updates": _repeated_tag_values(raw, "CANON_UPDATE"),
        "magic_challenge": fields.get("MAGIC_CHALLENGE"),
        "magic_success_criteria": fields.get("MAGIC_SUCCESS_CRITERIA"),
        "magic_modifier": modifier,
    }


def _parse_director_plan_tags(raw: str) -> dict[str, object] | None:
    fields = _tagged_fields(
        raw,
        (
            "SCENE_OBJECTIVE",
            "ADJUDICATION",
            "STATE_CHANGE",
            "PRESSURE",
            "CHOICE_A",
            "CHOICE_B",
            "NEXT_ACTOR",
            "COMPLETE",
            "CLOCK_CHANGE",
            "CANON_UPDATE",
            "MAGIC_CHALLENGE",
            "MAGIC_SUCCESS_CRITERIA",
            "MAGIC_MODIFIER",
            # Legacy outcome tags are consumed and discarded below.  They are
            # not part of the new director contract.
            "MAGIC_RESULT_ACK",
            "MAGIC_GOAL_STATUS",
            "MAGIC_GOAL_ANSWER",
            "MAGIC_COST_TYPE",
            "MAGIC_EFFECT_DETAIL",
        ),
    )
    required = {
        "SCENE_OBJECTIVE",
        "ADJUDICATION",
        "STATE_CHANGE",
        "PRESSURE",
        "CHOICE_A",
        "CHOICE_B",
        "NEXT_ACTOR",
    }
    if fields is None or not required.issubset(fields):
        return None
    clock_changes: list[dict[str, object]] = []
    for value in _repeated_tag_values(raw, "CLOCK_CHANGE"):
        match = re.fullmatch(
            r"\s*(mission|danger|mystery|relationship)\s*:\s*([+-]1)\s*",
            value,
            flags=re.IGNORECASE,
        )
        if match is None:
            return None
        clock_changes.append({"clock": match.group(1).casefold(), "change": int(match.group(2))})
    modifier = 0
    modifier_text = fields.get("MAGIC_MODIFIER")
    if modifier_text is not None:
        try:
            modifier = int(modifier_text.strip())
        except ValueError as exc:
            raise StructuredOutputError("MAGIC modifier must be an integer") from exc
    challenge = fields.get("MAGIC_CHALLENGE")
    return {
        "scene_objective": fields["SCENE_OBJECTIVE"],
        "adjudication": fields["ADJUDICATION"],
        "state_change": fields["STATE_CHANGE"],
        "pressure": fields["PRESSURE"],
        "choice_a": fields["CHOICE_A"],
        "choice_b": fields["CHOICE_B"],
        "next_actor": fields["NEXT_ACTOR"],
        "complete": _parse_bool(fields.get("COMPLETE"), default=False),
        "clock_changes": clock_changes,
        "canon_updates": _repeated_tag_values(raw, "CANON_UPDATE"),
        "magic_challenge": challenge,
        "magic_success_criteria": fields.get("MAGIC_SUCCESS_CRITERIA"),
        "magic_modifier": modifier,
        "magic_cost_type": fields.get("MAGIC_COST_TYPE"),
        "magic_effect_detail": fields.get("MAGIC_EFFECT_DETAIL"),
    }


def _normalize_magic_attribute(value: str | None) -> MagicAttribute | None:
    if value is None or value.strip().casefold() in {
        "", "none", "null", "n/a", "na", "nil", "false"
    }:
        return None
    normalized = value.strip().casefold()
    return next(
        (attribute for attribute in MagicAttribute if attribute.value.casefold() == normalized),
        value.strip(),  # Pydantic rejects unrecognized values with a structured validation error.
    )


def _parse_director_render_tags(raw: str) -> dict[str, object] | None:
    narration = _tag(raw, "NARRATION")
    return {"narration": narration} if narration is not None else None


def _parse_episode_resolution_tags(raw: str) -> dict[str, object] | None:
    fields = _tagged_fields(
        raw,
        (
            "OUTCOME", "CENTRAL_QUESTION_ANSWERED", "NARRATION",
            "IRREVERSIBLE_CHANGE", "GAINED", "LOST", "HOOK",
            "CANON_UPDATE", "COMPLETE",
        ),
    )
    required = {
        "OUTCOME", "CENTRAL_QUESTION_ANSWERED", "NARRATION",
        "IRREVERSIBLE_CHANGE", "GAINED", "LOST", "COMPLETE",
    }
    if fields is None or not required.issubset(fields):
        return None
    return {
        "outcome": fields["OUTCOME"],
        "central_question_answered": fields["CENTRAL_QUESTION_ANSWERED"],
        "narration": fields["NARRATION"],
        "irreversible_change": fields["IRREVERSIBLE_CHANGE"],
        "gained": fields["GAINED"],
        "lost": fields["LOST"],
        "hook": fields.get("HOOK") or None,
        "canon_updates": _repeated_tag_values(raw, "CANON_UPDATE"),
        "complete": _parse_bool(fields.get("COMPLETE"), default=False),
    }


def _parse_diary_tags(raw: str) -> dict[str, object] | None:
    fields = _tagged_fields(
        raw,
        ("DIARY_SLOT", "WRITE_NOW", "DIARY_TEXT", "EVIDENCE_REFS", "WELLNESS_SIGNAL"),
    )
    if fields is None or "DIARY_SLOT" not in fields or "EVIDENCE_REFS" not in fields:
        return None
    try:
        chosen_slot_number = int(fields["DIARY_SLOT"])
    except (TypeError, ValueError) as exc:
        raise StructuredOutputError("diary slot must be an integer") from exc
    raw_evidence_refs = fields["EVIDENCE_REFS"].strip()
    if raw_evidence_refs:
        evidence_refs: list[int] = []
        for token in raw_evidence_refs.split(","):
            token = token.strip()
            if not token:
                raise StructuredOutputError("diary evidence references must be comma-separated integers")
            try:
                evidence_refs.append(int(token))
            except ValueError as exc:
                raise StructuredOutputError(
                    "diary evidence references must be comma-separated integers"
                ) from exc
    else:
        evidence_refs = []
    return {
        "chosen_slot_number": chosen_slot_number,
        "write_now": _parse_bool(fields.get("WRITE_NOW"), default=False),
        "text": fields.get("DIARY_TEXT", ""),
        "evidence_refs": evidence_refs,
        "wellness_signal": fields.get("WELLNESS_SIGNAL"),
    }


def _parse_diary_fidelity_tags(raw: str) -> dict[str, object] | None:
    fields = _tagged_fields(
        raw,
        (
            "DECISION",
            "SUMMARY",
            "INVENTED_EVENT",
            "OTHER_CHARACTER_PRIVATE_STATE",
            "EVENT_ORDER_ISSUE",
            "CAUSAL_CONTRADICTION",
            "EVIDENCE_REFERENCE_ISSUE",
            "CLAIM_AUDIT",
        ),
    )
    if fields is None or "DECISION" not in fields or "SUMMARY" not in fields:
        return None
    return {
        "decision": fields["DECISION"],
        "summary": fields["SUMMARY"],
        "invented_events": _repeated_tag_values(raw, "INVENTED_EVENT"),
        "other_character_private_states": _repeated_tag_values(
            raw, "OTHER_CHARACTER_PRIVATE_STATE"
        ),
        "event_order_issues": _repeated_tag_values(raw, "EVENT_ORDER_ISSUE"),
        "causal_contradictions": _repeated_tag_values(raw, "CAUSAL_CONTRADICTION"),
        "evidence_reference_issues": _repeated_tag_values(
            raw, "EVIDENCE_REFERENCE_ISSUE"
        ),
        "claim_audits": [
            _parse_claim_audit_tag(value)
            for value in _repeated_tag_values(raw, "CLAIM_AUDIT")
        ],
    }


def _parse_claim_audit_tag(value: str) -> dict[str, object]:
    """Parse ``claim_id|verdict|evidence_ids|issue`` fallback fields."""

    parts = [part.strip() for part in value.split("|", 3)]
    if len(parts) < 3:
        raise StructuredOutputError(
            "claim audit tags must be claim_id|verdict|evidence_ids|issue"
        )
    try:
        claim_id = int(parts[0])
    except ValueError as exc:
        raise StructuredOutputError("claim audit ID must be an integer") from exc
    evidence_refs: list[int] = []
    if parts[2]:
        for token in parts[2].split(","):
            try:
                evidence_refs.append(int(token.strip()))
            except ValueError as exc:
                raise StructuredOutputError(
                    "claim audit evidence IDs must be comma-separated integers"
                ) from exc
    return {
        "claim_id": claim_id,
        "verdict": parts[1].upper(),
        "evidence_refs": evidence_refs,
        "issue": parts[3] or None if len(parts) == 4 else None,
    }


def _normalize_optional_signal(value: str | None) -> str | None:
    """Keep only an explicit out-of-world request in a wellness channel."""

    if value is None:
        return None
    normalized = value.strip()
    if normalized.casefold() in {"", "none", "null", "n/a", "na", "nil", "false"}:
        return None
    folded = normalized.casefold()
    explicit_patterns = (
        r"\b(?:out[- ]of[- ]world|out[- ]of[- ]character|ooc)\b",
        r"\bplease\s+(?:pause|stop|soften)\b",
        r"\bplease\s+slow\s+(?:the\s+)?scene\s+down\b",
        r"\b(?:i\s+(?:need|want)|please)\s+(?:to\s+)?(?:pause|stop)\s+(?:the\s+)?(?:scene|material|roleplay|participation)\b",
        r"\b(?:i\s+(?:need|want)\s+a\s+break|i\s+do\s+not\s+want\s+to\s+participate)\b",
        r"\b(?:this|the)\s+(?:material|scene|roleplay)\s+(?:is\s+)?(?:too\s+much|unsafe|overwhelming)\b",
        r"\bkeep\s+(?:this|the)\s+(?:attempt|scene|material)\s+private\b",
    )
    return normalized if any(re.search(pattern, folded) for pattern in explicit_patterns) else None


def _parse_orientation_tags(raw: str) -> dict[str, object] | None:
    fields = _tagged_fields(raw, ("ACCEPTED", "WELLNESS_SIGNAL"))
    if fields is None or "ACCEPTED" not in fields:
        return None
    signal = fields.get("WELLNESS_SIGNAL")
    if signal is not None and signal.strip().lower() in {"", "none", "null", "n/a"}:
        signal = None
    return {
        "accepted": _parse_bool(fields.get("ACCEPTED"), default=False),
        "wellness_signal": signal,
    }


def _repeated_tag_values(raw: str, name: str) -> list[str]:
    return [value.strip() for value in re.findall(rf"<{name}>\s*(.*?)\s*</{name}>", raw, re.DOTALL)]


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise StructuredOutputError(f"invalid boolean tag: {value}")


__all__ = [
    "ActorTurnEnvelope",
    "DirectorClockChange",
    "DirectorPlanEnvelope",
    "DirectorRenderEnvelope",
    "EpisodeResolutionEnvelope",
    "DiaryEnvelope",
    "DiaryClaimAudit",
    "DiaryFidelityEnvelope",
    "OrientationEnvelope",
    "OrchestratorEnvelope",
    "StructuredOutputError",
    "parse_actor_output",
    "parse_director_plan_output",
    "parse_director_render_output",
    "parse_episode_resolution_output",
    "parse_diary_output",
    "parse_diary_fidelity_output",
    "parse_orientation_output",
    "parse_orchestrator_output",
]
