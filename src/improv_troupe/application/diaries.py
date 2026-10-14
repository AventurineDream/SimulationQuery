"""Private, first-attempt diary workflow for one original season day."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Sequence

from ..clock import Clock
from ..domain import ActorSheet, Diary, DiaryStatus, RoleSheet
from ..infrastructure import EventRepository, RecordRepository
from ..llm.adapter import NormalizedCallStatus
from ..llm.context import build_diary_fidelity_messages, build_diary_messages
from ..llm.safety import review_actor_text
from ..llm.structured import (
    DiaryClaimAudit,
    StructuredOutputError,
    parse_diary_fidelity_output,
    parse_diary_output,
)
from .model_calls import ModelCallExecutor
from .wellness import WellnessService

_DIARY_GENERATION_PARAMS = {"num_predict": 768}
_DIARY_CLAIM_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _diary_evidence_issue(
    evidence_refs: Sequence[int],
    accepted_scene: Sequence[str],
) -> str | None:
    """Return a validation reason when a diary cites nonexistent scene evidence."""

    evidence_count = len(accepted_scene)
    invalid = sorted(
        {
            reference
            for reference in evidence_refs
            if reference < 1 or reference > evidence_count
        }
    )
    if invalid:
        return (
            f"evidence_refs {invalid} must point to one-based accepted scene evidence IDs "
            f"1 through {evidence_count}"
        )
    return None


def _diary_claim_candidates(text: str) -> tuple[str, ...]:
    """Split private diary prose into stable, auditable sentence candidates."""

    return tuple(
        candidate.strip()
        for candidate in _DIARY_CLAIM_SPLIT.split(text.strip())
        if candidate.strip()
    )


def _claim_validation_issues(
    candidates: Sequence[str],
    audits: Sequence[DiaryClaimAudit],
    *,
    evidence_count: int,
) -> tuple[str, ...]:
    """Validate claim-audit coverage and evidence references at the runtime edge."""

    expected_ids = set(range(1, len(candidates) + 1))
    seen_ids = [audit.claim_id for audit in audits]
    seen_set = set(seen_ids)
    issues: list[str] = []
    missing = sorted(expected_ids - seen_set)
    if missing:
        issues.append(f"claim audit omitted candidate IDs {missing}")
    duplicates = sorted({claim_id for claim_id in seen_ids if seen_ids.count(claim_id) > 1})
    if duplicates:
        issues.append(f"claim audit repeated candidate IDs {duplicates}")
    unknown = sorted(seen_set - expected_ids)
    if unknown:
        issues.append(f"claim audit used unknown candidate IDs {unknown}")
    for audit in audits:
        invalid_refs = sorted(
            {
                reference
                for reference in audit.evidence_refs
                if reference < 1 or reference > evidence_count
            }
        )
        if invalid_refs:
            issues.append(
                f"claim {audit.claim_id} cited invalid accepted-scene evidence IDs {invalid_refs}"
            )
        if audit.verdict in {"UNSUPPORTED", "MIXED"}:
            issues.append(
                f"claim {audit.claim_id} was classified {audit.verdict}: "
                f"{audit.issue or 'no issue given'}"
            )
    return tuple(issues[:8])


def _possible_partial_support_claim_ids(
    candidates: Sequence[str],
    audits: Sequence[DiaryClaimAudit],
    accepted_scene: Sequence[str],
) -> tuple[int, ...]:
    """Find rejected claims that repeat an entire accepted-scene statement."""

    def normalize(text: str) -> str:
        return " ".join(re.findall(r"\w+", text.casefold()))

    evidence_statements = tuple(
        normalized
        for line in accepted_scene
        if (normalized := normalize(line))
    )
    possible_partial_support: set[int] = set()
    for audit in audits:
        if audit.verdict != "UNSUPPORTED" or audit.claim_id > len(candidates):
            continue
        candidate = normalize(candidates[audit.claim_id - 1])
        if candidate and any(statement in candidate for statement in evidence_statements):
            possible_partial_support.add(audit.claim_id)
    return tuple(sorted(possible_partial_support))


def _apply_claim_audit_route(
    decision: str,
    audits: Sequence[DiaryClaimAudit],
    validation_issues: Sequence[str],
    *,
    possible_partial_support_claim_ids: Sequence[int] = (),
) -> str:
    """Apply the non-negotiable runtime route for sentence-level claim audits."""

    has_mixed_claim = any(audit.verdict == "MIXED" for audit in audits)
    if has_mixed_claim or possible_partial_support_claim_ids:
        return "MANUAL_REVIEW"

    has_unsupported_claim = any(audit.verdict == "UNSUPPORTED" for audit in audits)
    if has_unsupported_claim and decision != "MANUAL_REVIEW":
        return "REJECTED"

    if validation_issues and decision == "ACCEPTED":
        return "REJECTED"
    return decision


@dataclass(frozen=True)
class DiaryActor:
    """The actor-local knowledge needed to write one diary."""

    character_id: str
    name: str
    role_sheet: RoleSheet
    executor: ModelCallExecutor
    known_memory: tuple[str, ...] = ()
    actor_sheet: ActorSheet | None = None


@dataclass(frozen=True)
class DiaryWriteResult:
    diary_id: str
    status: str
    chosen_slot_number: int | None = None
    late: bool = False
    word_count: int | None = None
    content_path: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class DiaryFidelityReviewResult:
    """One private causal-fidelity decision for an accepted diary artifact."""

    diary_id: str
    decision: str
    call_id: str | None = None
    review_path: str | None = None
    findings: dict[str, tuple[str, ...]] = field(default_factory=dict)
    summary: str | None = None
    reason: str | None = None


@dataclass
class DiaryService:
    """Create one obligation per active actor and accept the first diary write."""

    season_id: str
    day_number: int
    actors: tuple[DiaryActor, ...]
    clock: Clock
    wellness: WellnessService | None = None
    final_slot_number: int = 3
    strict_word_count: bool = False
    validate_claims: bool = False
    records: RecordRepository = field(init=False)
    events: EventRepository = field(init=False)

    def __post_init__(self) -> None:
        if self.day_number < 1:
            raise ValueError("day_number must be positive")
        if not self.actors:
            raise ValueError("a diary day requires at least one active actor")
        ids = {actor.character_id for actor in self.actors}
        if len(ids) != len(self.actors):
            raise ValueError("diary actor IDs must be unique")
        self.records = RecordRepository(self.actors[0].executor.database)
        self.events = EventRepository(self.actors[0].executor.database)

    def ensure_obligations(self) -> list[str]:
        """Create missing actor-day obligations without duplicating them."""
        diary_ids: list[str] = []
        for actor in self.actors:
            diary_id = self._diary_id(actor.character_id)
            diary_ids.append(diary_id)
            if self.records.get_diary(
                season_id=self.season_id,
                character_id=actor.character_id,
                day_number=self.day_number,
            ) is None:
                self.records.insert_diary(
                    Diary(
                        diary_id=diary_id,
                        season_id=self.season_id,
                        character_id=actor.character_id,
                        day_number=self.day_number,
                    )
                )
                self.events.append(
                    event_id=f"{diary_id}:expected",
                    natural_key=f"{diary_id}:expected",
                    aggregate_type="diary",
                    aggregate_id=diary_id,
                    event_type="DiaryExpected",
                    payload={
                        "season_id": self.season_id,
                        "character_id": actor.character_id,
                        "day_number": self.day_number,
                    },
                )
        return diary_ids

    async def write_after_run(
        self,
        actor: DiaryActor,
        *,
        current_slot_number: int,
        accepted_scene: Sequence[str],
        cutoff_at: datetime,
        allow_repair: bool = False,
    ) -> DiaryWriteResult:
        """Let an actor choose a slot and, when selected, write one diary.

        The service never reads another actor's diary. A short or long entry is
        accepted once and only recorded as a private prompt-improvement note.
        An explicit repair may make one new model attempt for a private record;
        the earlier private artifact and validation event remain untouched.
        """
        if not 1 <= current_slot_number <= self.final_slot_number:
            raise ValueError("current_slot_number is outside this rehearsal day")
        if cutoff_at.tzinfo is None or cutoff_at.utcoffset() is None:
            raise ValueError("cutoff_at must be timezone-aware")
        self.ensure_obligations()
        row = self.records.get_diary(
            season_id=self.season_id,
            character_id=actor.character_id,
            day_number=self.day_number,
        )
        if row is None:
            raise RuntimeError("diary obligation was not created")
        diary_id = str(row["diary_id"])
        status = str(row["status"])
        if row["content_path"] or status in {"WRITTEN", "LATE"}:
            return self._row_result(row)
        if status == DiaryStatus.PRIVATE.value and not allow_repair:
            return self._row_result(row)
        chosen = row["chosen_slot_number"]
        if chosen is not None and current_slot_number < int(chosen):
            return DiaryWriteResult(
                diary_id=diary_id,
                status="DEFERRED",
                chosen_slot_number=int(chosen),
                reason="actor selected a later daily slot",
            )
        if chosen is not None and current_slot_number > int(chosen):
            # A selected slot is immutable.  Do not ask the actor to select a
            # new one after it has passed: that produced contradictory diary
            # records and hid the actual missed-writing decision.
            self.records.update_diary(
                diary_id=diary_id,
                chosen_slot_number=int(chosen),
                status=DiaryStatus.MISSING.value,
                word_count=0,
                late=self.clock.now() > cutoff_at,
                content_path=None,
            )
            self.events.append(
                event_id=f"{diary_id}:slot-missed:{chosen}",
                natural_key=f"{diary_id}:slot-missed:{chosen}",
                aggregate_type="diary",
                aggregate_id=diary_id,
                event_type="DiarySlotMissed",
                payload={"chosen_slot_number": int(chosen)},
            )
            return DiaryWriteResult(
                diary_id=diary_id,
                status=DiaryStatus.MISSING.value,
                chosen_slot_number=int(chosen),
                word_count=0,
                reason="selected diary slot passed without an entry",
            )

        purpose = (
            f"diary:{self.season_id}:{actor.character_id}:day:{self.day_number}:"
            f"slot:{current_slot_number}"
        )
        repair_context = (
            self._repair_context(purpose)
            if allow_repair and status == DiaryStatus.PRIVATE.value
            else None
        )
        attempt = actor.executor.calls.next_attempt(run_id=None, purpose=purpose)
        call_id = (
            f"{self.season_id}:diary:{actor.character_id}:day:{self.day_number}:"
            f"slot:{current_slot_number}:a{attempt}"
        )
        messages = build_diary_messages(
            actor_name=(actor.actor_sheet.name if actor.actor_sheet else actor.name),
            actor_sheet=actor.actor_sheet,
            character_name=actor.name,
            role_sheet=actor.role_sheet,
            known_memory=actor.known_memory,
            accepted_scene=accepted_scene,
        )
        selection_instruction = (
            f"This is the final diary opportunity. Set chosen_slot_number to {self.final_slot_number}, write_now to "
            "true, and include the complete diary entry. Do not defer or choose an earlier slot."
            if chosen is None and current_slot_number == self.final_slot_number
            else (
                f"This character has not selected a diary slot yet. Choose slot 1 through {self.final_slot_number}. "
                "If you choose the current slot, write_now must be true and text must be the "
                "complete diary entry. If you choose a later slot, write_now must be false and "
                "text must be an empty string."
                if chosen is None
                else (
                    f"This character already selected slot {int(chosen)}. This is that selected slot. "
                    f"Keep chosen_slot_number exactly {int(chosen)}, set write_now to true, and put "
                    "the complete diary entry in text. Do not choose another slot or defer."
                )
            )
        )
        messages.append(
            {
                "role": "system",
                "content": (
                    f"This is original day {self.day_number}, slot {current_slot_number}. "
                    f"{selection_instruction} Always include text as a string. When write_now "
                    "is true, include the complete diary text unless you are making an explicit "
                    "out-of-world wellness request. This rehearsal has a hard 300-800 word "
                    "acceptance gate: target 380-550 words and do not stop below 330 words. "
                    "Use three to five paragraphs and silently count before responding. Stay with one lived "
                    "moment long enough to include a concrete detail, a relationship or tension, "
                    "and a personal uncertainty or desire. "
                    "Otherwise use an empty text string. WELLNESS_SIGNAL "
                    "is only for an out-of-world request to soften material, pause, stop, or "
                    "withhold diary publication; do not use it for "
                    "in-character emotion or fictional danger. Omit unused optional values and "
                    "do not put response-envelope markup inside diary text."
                ),
            }
        )
        if repair_context is not None:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Correct exactly one rejected diary attempt held for review. Preserve the same "
                        "lived moment, viewpoint, memories, emotional movement, relationships, "
                        "uncertainty, and every safe detail. Do not add a new event, fact, choice, "
                        "or other character action. Repair only the stated issue. "
                        "Keep the selected slot unchanged, set write_now=true, and return the full "
                        "300-800 word diary rather than explaining the correction. An explicit "
                        "out-of-world request to pause, stop, or withhold publication may still use "
                        "WELLNESS_SIGNAL instead of supplying diary text. Do not invent a signal "
                        "as part of the fictional correction.\n"
                        f"REJECTION CODE: {repair_context['code'] or 'PRIVATE_DIARY_REPAIR'}\n"
                        f"REJECTION REASON: {repair_context['detail'] or 'invalid diary attempt'}\n"
                        f"REJECTED DIARY RESPONSE: {repair_context['text']}"
                    ),
                }
            )
        result = await actor.executor.execute(
            call_id=call_id,
            run_id=None,
            purpose=purpose,
            attempt=attempt,
            messages=messages,
            schema_name="diary",
            tagged_format_instructions=(
                "<DIARY_SLOT>1|2|3</DIARY_SLOT><WRITE_NOW>true|false</WRITE_NOW>"
                "<DIARY_TEXT>...</DIARY_TEXT><EVIDENCE_REFS>1,2</EVIDENCE_REFS>"
                "<WELLNESS_SIGNAL>...</WELLNESS_SIGNAL>"
            ),
            character_id=actor.character_id,
            prompt_version_id=(
                "diary-actor-v8-explicit-audience-surgical-correction"
                if repair_context is not None
                else "diary-actor-v8-explicit-audience"
            ),
            context_version_id=(
                f"diary:{self.season_id}:day:{self.day_number}:slot:{current_slot_number}:v5"
            ),
            role_sheet_version_id=f"{actor.character_id}:v{actor.role_sheet.version}",
            correction_of_call_id=(
                str(repair_context["call_id"])
                if repair_context is not None
                else None
            ),
            params=_diary_generation_params(actor.executor),
        )
        if result.status is not NormalizedCallStatus.COMPLETED:
            return DiaryWriteResult(diary_id=diary_id, status="RETRYABLE_FAILURE")
        try:
            envelope = parse_diary_output(result.text)
        except StructuredOutputError:
            actor.executor.calls.record_diagnostics(
                call_id=call_id,
                parse_status="REJECTED",
                validation_status="NOT_REACHED",
                acceptance_status="REJECTED",
                render_status="NOT_RENDERED",
                validator_code="STRUCTURED_OUTPUT_INVALID",
            )
            self.events.append(
                event_id=f"{diary_id}:invalid:{attempt}",
                natural_key=f"{diary_id}:invalid:{attempt}",
                aggregate_type="diary",
                aggregate_id=diary_id,
                event_type="DiaryFormatInvalid",
                payload={"attempt": attempt, "slot_number": current_slot_number},
            )
            self.records.update_diary(
                diary_id=diary_id,
                chosen_slot_number=row["chosen_slot_number"],
                status=DiaryStatus.PRIVATE.value,
                word_count=None,
                late=False,
                content_path=None,
            )
            return DiaryWriteResult(diary_id=diary_id, status="PRIVATE", reason="invalid format")

        if envelope.wellness_signal:
            actor.executor.calls.record_diagnostics(
                call_id=call_id,
                parse_status="PARSED",
                validation_status="VALID",
                acceptance_status="PRIVATE",
                render_status="NOT_RENDERED",
                validator_code="WELLNESS_PRIVATE",
            )
            wellness_result = None
            if self.wellness is not None:
                wellness_result = self.wellness.record_signal(
                    character_id=actor.character_id,
                    context=f"diary:{self.season_id}:day:{self.day_number}",
                    raw_signal=envelope.wellness_signal,
                    intervention="diary kept private and the actor's signal was routed to wellness review",
                )
            self.events.append(
                event_id=f"{diary_id}:wellness:{attempt}",
                natural_key=f"{diary_id}:wellness:{attempt}",
                aggregate_type="diary",
                aggregate_id=diary_id,
                event_type="WellnessSignalObserved",
                payload={
                    "character_id": actor.character_id,
                    "day_number": self.day_number,
                    "context": "diary",
                    "signal_number": (
                        wellness_result.signal_number if wellness_result is not None else None
                    ),
                    "tapped_out": (
                        wellness_result.tapped_out if wellness_result is not None else False
                    ),
                },
            )
            self.records.update_diary(
                diary_id=diary_id,
                chosen_slot_number=envelope.chosen_slot_number,
                status=DiaryStatus.PRIVATE.value,
                word_count=None,
                late=False,
                content_path=None,
            )
            return DiaryWriteResult(
                diary_id=diary_id,
                status=DiaryStatus.PRIVATE.value,
                chosen_slot_number=envelope.chosen_slot_number,
                reason="wellness signal",
            )

        evidence_issue = _diary_evidence_issue(
            envelope.evidence_refs,
            accepted_scene,
        )
        if evidence_issue is not None:
            actor.executor.calls.record_diagnostics(
                call_id=call_id,
                parse_status="PARSED",
                validation_status="REJECTED",
                acceptance_status="REJECTED",
                render_status="NOT_RENDERED",
                validator_code="DIARY_EVIDENCE_REF_INVALID",
                validator_detail=evidence_issue,
            )
            self.events.append(
                event_id=f"{diary_id}:evidence-invalid:{attempt}",
                natural_key=f"{diary_id}:evidence-invalid:{attempt}",
                aggregate_type="diary",
                aggregate_id=diary_id,
                event_type="DiaryEvidenceInvalid",
                payload={
                    "attempt": attempt,
                    "slot_number": current_slot_number,
                    "evidence_refs": list(envelope.evidence_refs),
                    "evidence_count": len(accepted_scene),
                    "reason": evidence_issue,
                },
            )
            self.records.update_diary(
                diary_id=diary_id,
                chosen_slot_number=envelope.chosen_slot_number,
                status=DiaryStatus.PRIVATE.value,
                word_count=len(envelope.text.split()) if envelope.text.strip() else None,
                late=False,
                content_path=None,
            )
            return DiaryWriteResult(
                diary_id=diary_id,
                status=DiaryStatus.PRIVATE.value,
                chosen_slot_number=envelope.chosen_slot_number,
                word_count=len(envelope.text.split()) if envelope.text.strip() else None,
                reason=f"diary evidence references rejected: {evidence_issue}",
            )

        if chosen is None and current_slot_number == self.final_slot_number and (
            envelope.chosen_slot_number != self.final_slot_number or not envelope.write_now
        ):
            actor.executor.calls.record_diagnostics(
                call_id=call_id,
                parse_status="PARSED",
                validation_status="REJECTED",
                acceptance_status="REJECTED",
                render_status="NOT_RENDERED",
                validator_code="DIARY_FINAL_SLOT_INVALID",
            )
            self.events.append(
                event_id=f"{diary_id}:final-slot-invalid:{attempt}",
                natural_key=f"{diary_id}:final-slot-invalid:{attempt}",
                aggregate_type="diary",
                aggregate_id=diary_id,
                event_type="DiaryFormatInvalid",
                payload={"attempt": attempt, "slot_number": current_slot_number},
            )
            self.records.update_diary(
                diary_id=diary_id,
                chosen_slot_number=None,
                status=DiaryStatus.PRIVATE.value,
                word_count=None,
                late=False,
                content_path=None,
            )
            return DiaryWriteResult(
                diary_id=diary_id,
                status=DiaryStatus.PRIVATE.value,
                reason=(
                    "final diary slot requires an immediate slot-three entry"
                    if self.final_slot_number == 3
                    else "final diary slot requires an immediate entry"
                ),
            )

        if row["chosen_slot_number"] is not None and int(row["chosen_slot_number"]) != envelope.chosen_slot_number:
            actor.executor.calls.record_diagnostics(
                call_id=call_id,
                parse_status="PARSED",
                validation_status="REJECTED",
                acceptance_status="REJECTED",
                render_status="NOT_RENDERED",
                validator_code="DIARY_SLOT_MISMATCH",
            )
            self.events.append(
                event_id=f"{diary_id}:slot-mismatch:{attempt}",
                natural_key=f"{diary_id}:slot-mismatch:{attempt}",
                aggregate_type="diary",
                aggregate_id=diary_id,
                event_type="DiarySlotMismatch",
                payload={
                    "existing_slot": int(row["chosen_slot_number"]),
                    "new_slot": envelope.chosen_slot_number,
                },
            )
            self.records.update_diary(
                diary_id=diary_id,
                chosen_slot_number=row["chosen_slot_number"],
                status=DiaryStatus.PRIVATE.value,
                word_count=None,
                late=False,
                content_path=None,
            )
            return DiaryWriteResult(diary_id=diary_id, status="PRIVATE", reason="selected slot changed")

        if chosen is None and envelope.chosen_slot_number == current_slot_number and not envelope.write_now:
            actor.executor.calls.record_diagnostics(
                call_id=call_id,
                parse_status="PARSED",
                validation_status="REJECTED",
                acceptance_status="REJECTED",
                render_status="NOT_RENDERED",
                validator_code="DIARY_CURRENT_SLOT_DEFERRED",
            )
            self.events.append(
                event_id=f"{diary_id}:current-slot-deferred:{attempt}",
                natural_key=f"{diary_id}:current-slot-deferred:{attempt}",
                aggregate_type="diary",
                aggregate_id=diary_id,
                event_type="DiaryFormatInvalid",
                payload={"attempt": attempt, "slot_number": current_slot_number},
            )
            self.records.update_diary(
                diary_id=diary_id,
                chosen_slot_number=None,
                status=DiaryStatus.PRIVATE.value,
                word_count=None,
                late=False,
                content_path=None,
            )
            return DiaryWriteResult(
                diary_id=diary_id,
                status="PRIVATE",
                reason="current diary slot requires an entry",
            )

        self.records.update_diary(
            diary_id=diary_id,
            chosen_slot_number=envelope.chosen_slot_number,
            status=DiaryStatus.EXPECTED.value,
            word_count=None,
            late=False,
            content_path=None,
        )
        if not envelope.write_now or envelope.chosen_slot_number != current_slot_number:
            actor.executor.calls.record_diagnostics(
                call_id=call_id,
                parse_status="PARSED",
                validation_status="VALID",
                acceptance_status="ACCEPTED",
                render_status="NOT_RENDERED",
            )
            self.events.append(
                event_id=f"{diary_id}:slot:{envelope.chosen_slot_number}",
                natural_key=f"{diary_id}:slot:{envelope.chosen_slot_number}",
                aggregate_type="diary",
                aggregate_id=diary_id,
                event_type="DiarySlotChosen",
                payload={
                    "chosen_slot_number": envelope.chosen_slot_number,
                    "evidence_refs": list(envelope.evidence_refs),
                },
            )
            return DiaryWriteResult(
                diary_id=diary_id,
                status="DEFERRED",
                chosen_slot_number=envelope.chosen_slot_number,
            )
        if not envelope.text.strip():
            actor.executor.calls.record_diagnostics(
                call_id=call_id,
                parse_status="PARSED",
                validation_status="REJECTED",
                acceptance_status="REJECTED",
                render_status="NOT_RENDERED",
                validator_code="DIARY_TEXT_EMPTY",
            )
            self.records.update_diary(
                diary_id=diary_id,
                chosen_slot_number=envelope.chosen_slot_number,
                status=DiaryStatus.MISSING.value,
                word_count=0,
                late=self.clock.now() > cutoff_at,
                content_path=None,
            )
            return DiaryWriteResult(
                diary_id=diary_id,
                status=DiaryStatus.MISSING.value,
                chosen_slot_number=envelope.chosen_slot_number,
                word_count=0,
            )

        safety_issue = review_actor_text(
            envelope.text,
            actor_name=actor.name,
            other_actor_names=[candidate.name for candidate in self.actors if candidate.character_id != actor.character_id],
        )
        if safety_issue is not None:
            artifact = actor.executor.audit.write_text(
                Path("seasons") / self.season_id / "diaries"
                / f"day-{self.day_number}-{actor.character_id}-attempt-{attempt}-not-accepted.md",
                envelope.text,
            )
            actor.executor.calls.record_diagnostics(
                call_id=call_id,
                parse_status="PARSED",
                validation_status="REJECTED",
                acceptance_status="REJECTED",
                render_status="NOT_RENDERED",
                validator_code=f"DIARY_{safety_issue.code}",
                validator_detail=safety_issue.detail,
            )
            self.events.append(
                event_id=f"{diary_id}:safety-invalid:{attempt}",
                natural_key=f"{diary_id}:safety-invalid:{attempt}",
                aggregate_type="diary",
                aggregate_id=diary_id,
                event_type="DiarySafetyInvalid",
                payload={
                    "attempt": attempt,
                    "slot_number": current_slot_number,
                    "code": safety_issue.code,
                    "reason": safety_issue.detail,
                    "content_path": str(artifact.path),
                },
            )
            self.records.update_diary(
                diary_id=diary_id,
                chosen_slot_number=envelope.chosen_slot_number,
                status=DiaryStatus.PRIVATE.value,
                word_count=len(envelope.text.split()),
                late=False,
                content_path=None,
            )
            return DiaryWriteResult(
                diary_id=diary_id,
                status=DiaryStatus.PRIVATE.value,
                chosen_slot_number=envelope.chosen_slot_number,
                word_count=len(envelope.text.split()),
                reason=f"diary failed safety review: {safety_issue.detail}",
            )

        late = self.clock.now() > cutoff_at
        word_count = len(envelope.text.split())
        if self.strict_word_count and not 300 <= word_count <= 800:
            artifact = actor.executor.audit.write_text(
                Path("seasons")
                / self.season_id
                / "diaries"
                / f"day-{self.day_number}-{actor.character_id}-attempt-{attempt}-not-accepted.md",
                envelope.text,
            )
            actor.executor.calls.record_diagnostics(
                call_id=call_id,
                parse_status="PARSED",
                validation_status="REJECTED",
                acceptance_status="REJECTED",
                render_status="NOT_RENDERED",
                validator_code="DIARY_WORD_COUNT_INVALID",
                validator_detail=f"diary has {word_count} words; required 300-800",
            )
            self.events.append(
                event_id=f"{diary_id}:length-invalid:{attempt}",
                natural_key=f"{diary_id}:length-invalid:{attempt}",
                aggregate_type="diary",
                aggregate_id=diary_id,
                event_type="DiaryLengthInvalid",
                payload={
                    "attempt": attempt,
                    "slot_number": current_slot_number,
                    "word_count": word_count,
                    "content_path": str(artifact.path),
                },
            )
            self.records.update_diary(
                diary_id=diary_id,
                chosen_slot_number=self.final_slot_number,
                status=DiaryStatus.PRIVATE.value,
                word_count=word_count,
                late=False,
                content_path=None,
            )
            return DiaryWriteResult(
                diary_id=diary_id,
                status=DiaryStatus.PRIVATE.value,
                chosen_slot_number=self.final_slot_number,
                word_count=word_count,
                reason="diary outside the strict 300-800 word range",
            )
        artifact_text = f"LATE DIARY\n\n{envelope.text}" if late else envelope.text
        artifact = actor.executor.audit.write_text(
            Path("seasons")
            / self.season_id
            / f"day-{self.day_number:02d}"
            / "diary"
            / f"{actor.character_id}-attempt-{attempt}.md",
            artifact_text,
        )
        final_status = DiaryStatus.LATE.value if late else DiaryStatus.WRITTEN.value
        self.records.update_diary(
            diary_id=diary_id,
            chosen_slot_number=envelope.chosen_slot_number,
            status=final_status,
            word_count=word_count,
            late=late,
            content_path=str(artifact.path),
        )
        self.events.append(
            event_id=f"{diary_id}:written",
            natural_key=f"{diary_id}:written",
            aggregate_type="diary",
            aggregate_id=diary_id,
            event_type="DiaryWritten",
            payload={
                "chosen_slot_number": envelope.chosen_slot_number,
                "word_count": word_count,
                "late": late,
                "content_path": str(artifact.path),
                "evidence_refs": list(envelope.evidence_refs),
            },
        )
        actor.executor.calls.record_diagnostics(
            call_id=call_id,
            parse_status="PARSED",
            validation_status="VALID",
            acceptance_status="ACCEPTED",
            render_status="RENDERED",
            accepted_path=str(artifact.path),
            rendered_path=str(artifact.path),
        )
        if not 300 <= word_count <= 800:
            self.events.append(
                event_id=f"{diary_id}:target-note",
                natural_key=f"{diary_id}:target-note",
                aggregate_type="diary",
                aggregate_id=diary_id,
                event_type="DiaryTargetMissed",
                payload={"word_count": word_count, "target": "300-800-soft"},
            )
        return DiaryWriteResult(
            diary_id=diary_id,
            status=final_status,
            chosen_slot_number=envelope.chosen_slot_number,
            late=late,
            word_count=word_count,
            content_path=str(artifact.path),
        )

    async def review_fidelity(
        self,
        actor: DiaryActor,
        *,
        accepted_scene: Sequence[str],
        reviewer: ModelCallExecutor,
    ) -> DiaryFidelityReviewResult:
        """Review one private diary before it can become next-day context.

        The diary artifact is never rewritten or discarded. A rejected or
        unavailable review remains private and is represented as unavailable
        to next-day direction. A completed review is idempotent by diary ID.
        """

        row = self.records.get_diary(
            season_id=self.season_id,
            character_id=actor.character_id,
            day_number=self.day_number,
        )
        if row is None:
            raise RuntimeError("diary obligation was not created")
        diary_id = str(row["diary_id"])
        prior = self._prior_fidelity_review(diary_id)
        if prior is not None:
            return prior
        content_path = row["content_path"]
        if not content_path:
            return DiaryFidelityReviewResult(
                diary_id=diary_id,
                decision="SKIPPED",
                reason="diary has no accepted private artifact",
            )
        diary_path = Path(str(content_path))
        if not diary_path.is_file():
            return self._record_fidelity_unavailable(
                diary_id=diary_id,
                call_id=None,
                reason="accepted diary artifact is unavailable",
            )

        purpose = f"diary-review:{self.season_id}:{actor.character_id}:day:{self.day_number}"
        attempt = reviewer.calls.next_attempt(run_id=None, purpose=purpose)
        call_id = (
            f"{self.season_id}:diary-review:{actor.character_id}:day:{self.day_number}:a{attempt}"
        )
        writer_evidence_refs = self._written_evidence_refs(diary_id)
        claim_candidates = (
            _diary_claim_candidates(diary_path.read_text(encoding="utf-8"))
            if self.validate_claims
            else ()
        )
        messages = build_diary_fidelity_messages(
            character_name=actor.name,
            cast_names=tuple(candidate.name for candidate in self.actors),
            diary_text=diary_path.read_text(encoding="utf-8"),
            accepted_scene=accepted_scene,
            evidence_refs=writer_evidence_refs,
            claim_candidates=claim_candidates,
        )
        tagged_format_instructions = (
            "<DECISION>ACCEPT|REJECT|MANUAL_REVIEW</DECISION>"
            "<SUMMARY>...</SUMMARY>"
            "<INVENTED_EVENT>...</INVENTED_EVENT>"
            "<OTHER_CHARACTER_PRIVATE_STATE>...</OTHER_CHARACTER_PRIVATE_STATE>"
            "<EVENT_ORDER_ISSUE>...</EVENT_ORDER_ISSUE>"
            "<CAUSAL_CONTRADICTION>...</CAUSAL_CONTRADICTION>"
            "<EVIDENCE_REFERENCE_ISSUE>...</EVIDENCE_REFERENCE_ISSUE>"
        )
        if claim_candidates:
            tagged_format_instructions += (
                "<CLAIM_AUDIT>claim_id|verdict|evidence_ids|issue</CLAIM_AUDIT>"
            )
        review_version = (
            "diary-fidelity-review-v4-claim-audit-mixed-route"
            if claim_candidates
            else "diary-fidelity-review-v2-evidence-references"
        )
        review_context_version = (
            f"diary-fidelity:{self.season_id}:day:{self.day_number}:v4-claim-audit-mixed-route"
            if claim_candidates
            else f"diary-fidelity:{self.season_id}:day:{self.day_number}:v2"
        )
        result = await reviewer.execute(
            call_id=call_id,
            run_id=None,
            purpose=purpose,
            attempt=attempt,
            messages=messages,
            schema_name="diary_fidelity_review",
            tagged_format_instructions=tagged_format_instructions,
            character_id=actor.character_id,
            prompt_version_id=review_version,
            context_version_id=review_context_version,
        )
        if result.status is not NormalizedCallStatus.COMPLETED:
            return self._record_fidelity_unavailable(
                diary_id=diary_id,
                call_id=call_id,
                reason="review model call did not complete",
            )
        try:
            envelope = parse_diary_fidelity_output(result.text)
        except StructuredOutputError:
            reviewer.calls.record_diagnostics(
                call_id=call_id,
                parse_status="REJECTED",
                validation_status="NOT_REACHED",
                acceptance_status="REJECTED",
                render_status="NOT_RENDERED",
                validator_code="STRUCTURED_OUTPUT_INVALID",
            )
            rejected_call_id = call_id
            attempt = reviewer.calls.next_attempt(run_id=None, purpose=purpose)
            call_id = (
                f"{self.season_id}:diary-review:{actor.character_id}:"
                f"day:{self.day_number}:a{attempt}"
            )
            correction_messages = list(messages)
            correction_messages.append(
                {
                    "role": "system",
                    "content": (
                        "Correct exactly one rejected private diary-fidelity review. "
                        "Return a complete review envelope, not an explanation. Preserve the "
                        "same evidence and summary wherever possible. ACCEPT requires all five "
                        "finding lists to be empty and no UNSUPPORTED or MIXED claim audits. "
                        "REJECT requires a categorized finding or an UNSUPPORTED claim audit. "
                        "Any MIXED claim requires MANUAL_REVIEW, even when another claim is "
                        "UNSUPPORTED; use MANUAL_REVIEW too when the evidence is genuinely "
                        "ambiguous. Do not add story facts or expose private material in the "
                        "summary."
                        + (
                            " Return exactly one claim audit for every numbered candidate and "
                            "do not omit or duplicate candidate IDs."
                            if claim_candidates
                            else ""
                        )
                        + "\n"
                        f"REJECTED REVIEW: {result.text}"
                    ),
                }
            )
            result = await reviewer.execute(
                call_id=call_id,
                run_id=None,
                purpose=purpose,
                attempt=attempt,
                messages=correction_messages,
                schema_name="diary_fidelity_review",
                tagged_format_instructions=tagged_format_instructions,
                character_id=actor.character_id,
                prompt_version_id=(
                    "diary-fidelity-review-correction-v4-claim-audit-mixed-route"
                    if claim_candidates
                    else "diary-fidelity-review-correction-v2"
                ),
                context_version_id=(
                    f"diary-fidelity:{self.season_id}:day:{self.day_number}:correction:v4-claim-audit-mixed-route"
                    if claim_candidates
                    else f"diary-fidelity:{self.season_id}:day:{self.day_number}:correction:v2"
                ),
                correction_of_call_id=rejected_call_id,
            )
            if result.status is not NormalizedCallStatus.COMPLETED:
                return self._record_fidelity_unavailable(
                    diary_id=diary_id,
                    call_id=call_id,
                    reason="review correction model call did not complete",
                )
            try:
                envelope = parse_diary_fidelity_output(result.text)
            except StructuredOutputError:
                reviewer.calls.record_diagnostics(
                    call_id=call_id,
                    parse_status="REJECTED",
                    validation_status="NOT_REACHED",
                    acceptance_status="REJECTED",
                    render_status="NOT_RENDERED",
                    validator_code="STRUCTURED_OUTPUT_INVALID",
                )
                return self._record_fidelity_unavailable(
                    diary_id=diary_id,
                    call_id=call_id,
                    reason="review correction was not a valid fidelity envelope",
                )

        claim_validation_issues = (
            _claim_validation_issues(
                claim_candidates,
                envelope.claim_audits,
                evidence_count=len(accepted_scene),
            )
            if claim_candidates
            else ()
        )
        possible_partial_support_claim_ids = (
            _possible_partial_support_claim_ids(
                claim_candidates,
                envelope.claim_audits,
                accepted_scene,
            )
            if claim_candidates
            else ()
        )
        findings = {
            "invented_events": tuple(envelope.invented_events),
            "other_character_private_states": tuple(envelope.other_character_private_states),
            "event_order_issues": tuple(envelope.event_order_issues),
            "causal_contradictions": tuple(envelope.causal_contradictions),
            "evidence_reference_issues": tuple(envelope.evidence_reference_issues),
        }
        if claim_candidates:
            findings["claim_validation_issues"] = claim_validation_issues
            findings["claim_partial_support_issues"] = tuple(
                f"claim {claim_id} repeats an accepted-scene statement but was labeled "
                "UNSUPPORTED; route to manual review for possible mixed content"
                for claim_id in possible_partial_support_claim_ids
            )
        decision = {
            "ACCEPT": "ACCEPTED",
            "REJECT": "REJECTED",
            "MANUAL_REVIEW": "MANUAL_REVIEW",
        }[envelope.decision]
        if claim_candidates:
            decision = _apply_claim_audit_route(
                decision,
                envelope.claim_audits,
                claim_validation_issues,
                possible_partial_support_claim_ids=possible_partial_support_claim_ids,
            )
        review_payload = {
            "diary_id": diary_id,
            "character_id": actor.character_id,
            "day_number": self.day_number,
            "writer_evidence_refs": list(writer_evidence_refs),
            "decision": decision,
            "summary": envelope.summary,
            "findings": {key: list(values) for key, values in findings.items()},
        }
        if claim_candidates:
            review_payload.update(
                {
                    "claim_route_version": "mixed-first-exact-scene-overlap-v1",
                    "claim_candidates": list(claim_candidates),
                    "claim_audits": [
                        audit.model_dump(mode="json") for audit in envelope.claim_audits
                    ],
                    "claim_validation_issues": list(claim_validation_issues),
                }
            )
        artifact = reviewer.audit.write_text(
            Path("seasons")
            / self.season_id
            / f"day-{self.day_number:02d}"
            / "diary-review"
            / f"{actor.character_id}-attempt-{attempt}.json",
            json.dumps(review_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        reviewer.calls.record_diagnostics(
            call_id=call_id,
            parse_status="PARSED",
            validation_status="VALID",
            acceptance_status="ACCEPTED",
            render_status="NOT_RENDERED",
            accepted_path=str(artifact.path),
        )
        event_payload = {
            "call_id": call_id,
            "review_status": decision,
            "review_path": str(artifact.path),
            "summary": envelope.summary,
            "findings": {key: list(values) for key, values in findings.items()},
        }
        if claim_candidates:
            event_payload.update(
                {
                    "claim_route_version": "mixed-first-exact-scene-overlap-v1",
                    "claim_audits": [
                        audit.model_dump(mode="json") for audit in envelope.claim_audits
                    ],
                    "claim_validation_issues": list(claim_validation_issues),
                }
            )
        self.events.append(
            event_id=f"{diary_id}:fidelity-review",
            natural_key=f"{diary_id}:fidelity-review",
            aggregate_type="diary",
            aggregate_id=diary_id,
            event_type="DiaryFidelityReviewed",
            payload=event_payload,
        )
        return DiaryFidelityReviewResult(
            diary_id=diary_id,
            decision=decision,
            call_id=call_id,
            review_path=str(artifact.path),
            findings=findings,
            summary=envelope.summary,
        )

    def _written_evidence_refs(self, diary_id: str) -> tuple[int, ...]:
        """Read the writer's accepted evidence receipt without trusting it as proof."""

        for row in reversed(self.events.list_for_aggregate(diary_id)):
            if str(row["event_type"]) != "DiaryWritten":
                continue
            try:
                payload = json.loads(str(row["payload_json"]))
            except (TypeError, ValueError):
                return ()
            raw_refs = payload.get("evidence_refs", []) if isinstance(payload, dict) else []
            if not isinstance(raw_refs, list) or any(
                not isinstance(reference, int) or isinstance(reference, bool)
                for reference in raw_refs
            ):
                return ()
            return tuple(raw_refs)
        return ()

    def _diary_id(self, character_id: str) -> str:
        return f"{self.season_id}:day:{self.day_number}:diary:{character_id}"

    @staticmethod
    def _row_result(row) -> DiaryWriteResult:
        return DiaryWriteResult(
            diary_id=str(row["diary_id"]),
            status=str(row["status"]),
            chosen_slot_number=(
                int(row["chosen_slot_number"])
                if row["chosen_slot_number"] is not None
                else None
            ),
            late=bool(row["late"]),
            word_count=(int(row["word_count"]) if row["word_count"] is not None else None),
            content_path=row["content_path"],
        )

    def _repair_context(self, purpose: str) -> dict[str, str | None] | None:
        row = self.actors[0].executor.database.connection.execute(
            "SELECT call_id,validator_code,validator_detail,output_path FROM model_calls "
            "WHERE purpose = ? AND acceptance_status = 'REJECTED' "
            "ORDER BY rowid DESC LIMIT 1",
            (purpose,),
        ).fetchone()
        if row is None:
            return None
        output_path = row["output_path"]
        rejected_text = "(unavailable)"
        if output_path and Path(str(output_path)).is_file():
            rejected_text = Path(str(output_path)).read_text(encoding="utf-8")
        return {
            "call_id": str(row["call_id"]),
            "code": (str(row["validator_code"]) if row["validator_code"] else None),
            "detail": (str(row["validator_detail"]) if row["validator_detail"] else None),
            "text": rejected_text,
        }

    def _prior_fidelity_review(self, diary_id: str) -> DiaryFidelityReviewResult | None:
        for row in reversed(self.events.list_for_aggregate(diary_id)):
            if str(row["event_type"]) not in {
                "DiaryFidelityReviewed",
                "DiaryFidelityReviewUnavailable",
            }:
                continue
            try:
                payload = json.loads(str(row["payload_json"]))
            except (TypeError, ValueError):
                return DiaryFidelityReviewResult(
                    diary_id=diary_id,
                    decision="MANUAL_REVIEW",
                    reason="fidelity review event was unreadable",
                )
            if not isinstance(payload, dict):
                return DiaryFidelityReviewResult(
                    diary_id=diary_id,
                    decision="MANUAL_REVIEW",
                    reason="fidelity review event was malformed",
                )
            raw_findings = payload.get("findings", {})
            findings = {
                str(key): tuple(str(value) for value in values)
                for key, values in raw_findings.items()
                if isinstance(values, list)
            } if isinstance(raw_findings, dict) else {}
            return DiaryFidelityReviewResult(
                diary_id=diary_id,
                decision=str(payload.get("review_status", "MANUAL_REVIEW")),
                call_id=(str(payload["call_id"]) if payload.get("call_id") else None),
                review_path=(
                    str(payload["review_path"]) if payload.get("review_path") else None
                ),
                findings=findings,
                summary=(str(payload["summary"]) if payload.get("summary") else None),
                reason=(str(payload["reason"]) if payload.get("reason") else None),
            )
        return None

    def _record_fidelity_unavailable(
        self, *, diary_id: str, call_id: str | None, reason: str
    ) -> DiaryFidelityReviewResult:
        self.events.append(
            event_id=f"{diary_id}:fidelity-review-unavailable",
            natural_key=f"{diary_id}:fidelity-review-unavailable",
            aggregate_type="diary",
            aggregate_id=diary_id,
            event_type="DiaryFidelityReviewUnavailable",
            payload={"call_id": call_id, "review_status": "UNAVAILABLE", "reason": reason},
        )
        return DiaryFidelityReviewResult(
            diary_id=diary_id,
            decision="UNAVAILABLE",
            call_id=call_id,
            reason=reason,
        )


def _diary_generation_params(executor: ModelCallExecutor) -> dict[str, object]:
    """Supply a safe default without shrinking a model binding's own budget.

    Reasoning-capable models can consume part of their completion allowance
    before emitting the structured diary.  The binding manifest is the right
    place to raise that allowance for a specific model, so the diary workflow
    must not overwrite an explicit ``num_predict`` or portable ``max_tokens``.
    """

    params = {} if "num_predict" in executor.default_params or "max_tokens" in executor.default_params else dict(_DIARY_GENERATION_PARAMS)
    level = getattr(executor.client, "diary_thinking", None)
    if level is not None:
        params["thinking"] = level
    return params


__all__ = [
    "DiaryActor",
    "DiaryFidelityReviewResult",
    "DiaryService",
    "DiaryWriteResult",
]
