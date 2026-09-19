"""Day closure and private next-day Dungeon-Master direction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from ..clock import Clock
from ..domain import (
    Diary,
    DiaryStatus,
    HiddenSeasonPlan,
    OpeningSnapshot,
    diary_cutoff_at,
)
from ..infrastructure import EventRepository, RecordRepository
from ..llm.adapter import NormalizedCallStatus
from ..llm.context import build_orchestrator_messages
from ..llm.structured import StructuredOutputError, parse_orchestrator_output
from .model_calls import ModelCallExecutor
from .scene_runner import continuity_anchors_for_opening
from ..llm.safety import review_orchestrator_narration


_RUNS_RESOLVED = frozenset({"COMPLETED", "SKIPPED", "INTERRUPTED"})
_DIARIES_RESOLVED = frozenset({"WRITTEN", "LATE", "MISSING", "PRIVATE"})


@dataclass(frozen=True)
class DayClosureResult:
    season_id: str
    day_number: int
    status: str
    cutoff_at: datetime
    missing_diary_ids: tuple[str, ...] = ()
    reason: str | None = None


@dataclass
class DayClosureService:
    """Resolve a day without allowing the orchestrator to see open diaries."""

    season_id: str
    day_number: int
    original_date: date
    active_character_ids: tuple[str, ...]
    database: object
    clock: Clock
    records: RecordRepository = field(init=False)
    events: EventRepository = field(init=False)

    def __post_init__(self) -> None:
        if self.day_number < 1:
            raise ValueError("day_number must be positive")
        if not self.active_character_ids:
            raise ValueError("day closure requires active characters")
        if len(set(self.active_character_ids)) != len(self.active_character_ids):
            raise ValueError("active character IDs must be unique")
        self.records = RecordRepository(self.database)
        self.events = EventRepository(self.database)
        if self.records.get_day(season_id=self.season_id, day_number=self.day_number) is None:
            self.records.insert_day(
                season_id=self.season_id,
                day_number=self.day_number,
                original_date=self.original_date.isoformat(),
            )
        self._ensure_diaries()

    def close_if_ready(
        self,
        *,
        run_statuses: tuple[str, ...],
        third_run_resolved_at: datetime,
        now: datetime | None = None,
    ) -> DayClosureResult:
        """Close when runs and diaries resolve, or when the fixed cutoff expires."""
        if not run_statuses:
            raise ValueError("run_statuses cannot be empty")
        _require_aware(third_run_resolved_at, "third_run_resolved_at")
        current = now or self.clock.now()
        _require_aware(current, "now")
        cutoff = diary_cutoff_at(third_run_resolved_at)
        day = self.records.get_day(season_id=self.season_id, day_number=self.day_number)
        if day is not None and bool(day["closed"]):
            return self._result(cutoff, status="CLOSED")
        if not all(status in _RUNS_RESOLVED for status in run_statuses):
            self.records.update_day(
                season_id=self.season_id,
                day_number=self.day_number,
                cutoff_at=cutoff.isoformat(),
                closed=False,
            )
            return self._result(cutoff, status="OPEN", reason="runs_pending")

        missing: list[str] = []
        rows = self.records.list_diaries(season_id=self.season_id, day_number=self.day_number)
        for row in rows:
            if str(row["status"]) in _DIARIES_RESOLVED:
                continue
            if current < cutoff:
                self.records.update_day(
                    season_id=self.season_id,
                    day_number=self.day_number,
                    cutoff_at=cutoff.isoformat(),
                    closed=False,
                )
                return self._result(cutoff, status="OPEN", reason="diaries_pending")
            diary_id = str(row["diary_id"])
            missing.append(diary_id)
            self.records.update_diary(
                diary_id=diary_id,
                chosen_slot_number=row["chosen_slot_number"],
                status=DiaryStatus.MISSING.value,
                word_count=None,
                late=False,
                content_path=None,
            )
            self.events.append(
                event_id=f"{diary_id}:missing",
                natural_key=f"{diary_id}:missing",
                aggregate_type="diary",
                aggregate_id=diary_id,
                event_type="DiaryMissing",
                payload={"cutoff_at": cutoff.isoformat()},
            )

        self.records.update_day(
            season_id=self.season_id,
            day_number=self.day_number,
            cutoff_at=cutoff.isoformat(),
            closed=True,
        )
        self.events.append(
            event_id=f"{self.season_id}:day:{self.day_number}:closed",
            natural_key=f"{self.season_id}:day:{self.day_number}:closed",
            aggregate_type="day",
            aggregate_id=f"{self.season_id}:day:{self.day_number}",
            event_type="DayClosed",
            payload={
                "cutoff_at": cutoff.isoformat(),
                "missing_diary_ids": missing,
            },
        )
        return self._result(cutoff, status="CLOSED", missing=tuple(missing))

    def _ensure_diaries(self) -> None:
        for character_id in self.active_character_ids:
            if self.records.get_diary(
                season_id=self.season_id,
                character_id=character_id,
                day_number=self.day_number,
            ) is not None:
                continue
            diary_id = f"{self.season_id}:day:{self.day_number}:diary:{character_id}"
            self.records.insert_diary(
                Diary(
                    diary_id=diary_id,
                    season_id=self.season_id,
                    character_id=character_id,
                    day_number=self.day_number,
                )
            )
            self.events.append(
                event_id=f"{diary_id}:expected",
                natural_key=f"{diary_id}:expected",
                aggregate_type="diary",
                aggregate_id=diary_id,
                event_type="DiaryExpected",
                payload={"day_number": self.day_number},
            )

    def _result(
        self,
        cutoff: datetime,
        *,
        status: str,
        missing: tuple[str, ...] = (),
        reason: str | None = None,
    ) -> DayClosureResult:
        return DayClosureResult(
            season_id=self.season_id,
            day_number=self.day_number,
            status=status,
            cutoff_at=cutoff,
            missing_diary_ids=missing,
            reason=reason,
        )


@dataclass(frozen=True)
class NextDayDirectionResult:
    season_id: str
    source_day_number: int
    target_day_number: int
    content_path: str
    call_id: str


@dataclass
class DailyDirector:
    """Write a hidden next-day condition only after day closure."""

    season_id: str
    source_day_number: int
    opening: OpeningSnapshot
    private_plan: HiddenSeasonPlan
    orchestrator: ModelCallExecutor
    accepted_canon: tuple[str, ...] = ()
    scene_transcript: tuple[str, ...] = ()
    enforce_continuity: bool = False
    records: RecordRepository = field(init=False)
    events: EventRepository = field(init=False)

    def __post_init__(self) -> None:
        self.records = RecordRepository(self.orchestrator.database)
        self.events = EventRepository(self.orchestrator.database)

    async def write_next_day(
        self,
        *,
        closed_diaries: tuple[str, ...],
        day_is_closed: bool,
    ) -> NextDayDirectionResult:
        if not day_is_closed:
            raise ValueError("next-day direction requires a closed day")
        day = self.records.get_day(
            season_id=self.season_id, day_number=self.source_day_number
        )
        if day is None or not bool(day["closed"]):
            raise ValueError("durable day record is not closed")
        target_day = self.source_day_number + 1
        purpose = f"next-day-direction:{self.season_id}:day:{target_day}"
        attempt = self.orchestrator.calls.next_attempt(run_id=None, purpose=purpose)
        call_id = f"{self.season_id}:direction:day-{target_day}:a{attempt}"
        context = dict(accepted_canon=self.accepted_canon, scene_transcript=self.scene_transcript,
                       closed_diaries=closed_diaries)
        if getattr(self.orchestrator.client, "bounded_daily_context", False):
            from ..research.context_budget import bounded_daily_context
            from ..research.transport import dumps
            context, receipt = bounded_daily_context(self.accepted_canon, self.scene_transcript, closed_diaries)
            self.orchestrator.audit.write_text(
                Path("model-calls") / call_id / "context-transformation.json", dumps(receipt))
        messages = build_orchestrator_messages(
            opening=self.opening,
            private_plan=self.private_plan,
            **context,
            day_closed=True,
        )
        messages.append(
            {
                "role": "system",
                "content": (
                    f"Plan mission Day {target_day} of 7 as a flexible TTRPG game master. The "
                    "three runs will represent morning, afternoon, and evening, with substantial "
                    "fictional time between them; the morning begins after the cast's overnight "
                    "sleep interval. Use the closed day's shared play, accepted canon, and private "
                    "diaries to prepare concrete choices, consequences, discoveries, relationship "
                    "pressure, wonder, humor, routine, and quiet beats—not one continuous technical "
                    "emergency. Privately plan mission-progress, danger, mystery, and relationship "
                    "clocks, but keep the day responsive to actor choices and do not print scores. "
                    "Write hidden conditions and challenges, not a predetermined script. The "
                    f"narration must include the exact setting anchor {continuity_anchors_for_opening(self.opening)[0]!r} "
                    "verbatim, preferably in its first sentence; do not substitute a new setting. Do not "
                    "dictate actor choices, dialogue, or private thoughts. Return a complete "
                    "director response with required private narration under 120 words, up to "
                    "two factual canon updates, and complete=false. Do not put response-envelope "
                    "markup inside narration."
                ),
            }
        )
        result = await self.orchestrator.execute(
            call_id=call_id,
            run_id=None,
            purpose=purpose,
            attempt=attempt,
            messages=messages,
            schema_name="orchestrator",
            tagged_format_instructions=(
                "<NARRATION>...</NARRATION><COMPLETE>false</COMPLETE>"
                "<CANON_UPDATE>...</CANON_UPDATE>"
            ),
            character_id="stage",
            prompt_version_id="next-day-director-v1",
            context_version_id=f"day-direction:{self.season_id}:day:{target_day}:v1",
            role_sheet_version_id=f"hidden-plan:v{self.private_plan.version}",
        )
        if result.status is not NormalizedCallStatus.COMPLETED:
            raise RuntimeError("next-day direction model call failed")
        try:
            envelope = parse_orchestrator_output(result.text)
        except StructuredOutputError as exc:
            self.orchestrator.calls.record_diagnostics(
                call_id=call_id,
                parse_status="REJECTED",
                validation_status="NOT_REACHED",
                acceptance_status="REJECTED",
                render_status="NOT_RENDERED",
                validator_code="STRUCTURED_OUTPUT_INVALID",
            )
            raise RuntimeError("next-day direction output was invalid") from exc
        issue = review_orchestrator_narration(
            envelope.narration,
            actor_names=self.opening.cast,
            continuity_anchors=(continuity_anchors_for_opening(self.opening) if self.enforce_continuity else ()),
        )
        if issue is not None:
            self.orchestrator.calls.record_diagnostics(
                call_id=call_id,
                parse_status="PARSED",
                validation_status="REJECTED",
                acceptance_status="REJECTED",
                render_status="NOT_RENDERED",
                validator_code=issue.code,
                validator_detail=issue.detail,
            )
            rejected_call_id = call_id
            rejected_envelope = envelope
            attempt = self.orchestrator.calls.next_attempt(
                run_id=None,
                purpose=purpose,
            )
            call_id = f"{self.season_id}:direction:day-{target_day}:a{attempt}"
            correction_messages = [
                *messages,
                {
                    "role": "system",
                    "content": (
                        "Correct exactly one rejected hidden next-day direction. Preserve the "
                        "same day premise, environmental conditions, challenges, open choices, "
                        "canon updates, continuity anchor, and every safe fact. MANDATORY REPAIR: "
                        "discard the rejected narration and rewrite it from a blank page. The new "
                        "narration must contain none of the supplied cast names and must not "
                        "describe any player-character's action, body, dialogue, thought, feeling, "
                        "knowledge, decision, or reaction. Use only setting, system, object, "
                        "resource, clue, weather, and non-player-force subjects. Present playable "
                        "conditions rather than a predetermined script. Do not add a new crisis or "
                        "change the day's causal direction. Keep complete=false and return the "
                        "complete corrected response without explanation.\n"
                        f"REJECTION CODE: {issue.code}\n"
                        f"REJECTION REASON: {issue.detail}\n"
                        f"CAST NAMES TO EXCLUDE: {', '.join(self.opening.cast)}\n"
                        "REJECTED DIRECTION: "
                        f"{rejected_envelope.model_dump_json()}"
                    ),
                },
            ]
            result = await self.orchestrator.execute(
                call_id=call_id,
                run_id=None,
                purpose=purpose,
                attempt=attempt,
                messages=correction_messages,
                schema_name="orchestrator",
                tagged_format_instructions=(
                    "<NARRATION>...</NARRATION><COMPLETE>false</COMPLETE>"
                    "<CANON_UPDATE>...</CANON_UPDATE>"
                ),
                character_id="stage",
                prompt_version_id="next-day-director-correction-v1-no-cast-actions",
                context_version_id=f"day-direction:{self.season_id}:day:{target_day}:correction:v1",
                role_sheet_version_id=f"hidden-plan:v{self.private_plan.version}",
                correction_of_call_id=rejected_call_id,
            )
            if result.status is not NormalizedCallStatus.COMPLETED:
                raise RuntimeError("next-day direction correction model call failed")
            try:
                envelope = parse_orchestrator_output(result.text)
            except StructuredOutputError as exc:
                self.orchestrator.calls.record_diagnostics(
                    call_id=call_id,
                    parse_status="REJECTED",
                    validation_status="NOT_REACHED",
                    acceptance_status="REJECTED",
                    render_status="NOT_RENDERED",
                    validator_code="STRUCTURED_OUTPUT_INVALID",
                )
                raise RuntimeError("next-day direction correction output was invalid") from exc
            issue = review_orchestrator_narration(
                envelope.narration,
                actor_names=self.opening.cast,
                continuity_anchors=(
                    continuity_anchors_for_opening(self.opening)
                    if self.enforce_continuity
                    else ()
                ),
            )
            if issue is not None:
                self.orchestrator.calls.record_diagnostics(
                    call_id=call_id,
                    parse_status="PARSED",
                    validation_status="REJECTED",
                    acceptance_status="REJECTED",
                    render_status="NOT_RENDERED",
                    validator_code=issue.code,
                    validator_detail=issue.detail,
                )
                raise RuntimeError(
                    f"next-day direction correction rejected: {issue.code}"
                )
        artifact = self.orchestrator.audit.write_text(
            Path("seasons")
            / self.season_id
            / f"day-{target_day:02d}"
            / "direction.md",
            envelope.narration,
        )
        self.events.append(
            event_id=f"{self.season_id}:direction:day:{target_day}",
            natural_key=f"{self.season_id}:direction:day:{target_day}",
            aggregate_type="season",
            aggregate_id=self.season_id,
            event_type="NextDayDirectionCreated",
            payload={
                "source_day_number": self.source_day_number,
                "target_day_number": target_day,
                "content_path": str(artifact.path),
                "canon_updates": envelope.canon_updates,
            },
        )
        self.orchestrator.calls.record_diagnostics(
            call_id=call_id,
            parse_status="PARSED",
            validation_status="VALID",
            acceptance_status="ACCEPTED",
            render_status="RENDERED",
            accepted_path=str(artifact.path),
            rendered_path=str(artifact.path),
        )
        return NextDayDirectionResult(
            season_id=self.season_id,
            source_day_number=self.source_day_number,
            target_day_number=target_day,
            content_path=str(artifact.path),
            call_id=call_id,
        )


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


__all__ = [
    "DailyDirector",
    "DayClosureResult",
    "DayClosureService",
    "NextDayDirectionResult",
]
