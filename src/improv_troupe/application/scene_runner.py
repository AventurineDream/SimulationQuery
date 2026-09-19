"""Checkpointed shared-scene execution for the four-actor pilot."""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from ..clock import Clock
from ..domain import ActorSheet, CharacterCard, HiddenSeasonPlan, OpeningSnapshot, RoleSheet, WorldBook
from ..domain.magic import (
    MagicAdjudication,
    MagicAttribute,
    MagicCostType,
    MagicOutcome,
    MagicRollResult,
    adjudicate_magic_roll,
    magic_roll_payload,
    resolve_magic_roll,
)
from ..engine.parsing import clean_line
from ..engine.transcript import Transcript
from ..infrastructure import EventRepository, RecordRepository
from ..llm.adapter import NormalizedCallStatus
from ..llm.context import (
    ActorContext,
    build_actor_messages,
    build_director_plan_messages,
    build_director_render_messages,
    build_orchestrator_messages,
    spent_director_imagery,
)
from ..llm.safety import SafetyIssue, review_actor_text, review_correction_scope, review_director_stakes, review_orchestrator_narration
from .world_books import ActiveLoreEntry, WorldBookEngine
from ..llm.structured import (
    ActorTurnEnvelope,
    DirectorPlanEnvelope,
    OrchestratorEnvelope,
    StructuredOutputError,
    parse_actor_output,
    parse_director_plan_output,
    parse_director_render_output,
    parse_orchestrator_output,
)
from .model_calls import ModelCallExecutor
from .wellness import WellnessService


_STAGE_CHARACTER_ID = "__orchestrator__"
_NEUTRAL_CHARACTER_PREFIX = "__interruption__:"


class SceneRunError(RuntimeError):
    """Raised when a scene cannot safely continue from its last checkpoint."""

    def __init__(self, reason: str, *, error_type: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.error_type = error_type

    @property
    def is_transport_timeout(self) -> bool:
        return self.error_type in {"ReadTimeout", "ConnectTimeout", "TimeoutError"}


@dataclass(frozen=True)
class SceneActor:
    """One independent character session, even when models are shared."""

    character_id: str
    name: str
    role_sheet: RoleSheet
    executor: ModelCallExecutor
    known_memory: tuple[str, ...] = ()
    actor_sheet: ActorSheet | None = None
    character_card: CharacterCard | None = None
    prompt_profile: str = "general"


@dataclass(frozen=True)
class SceneRunResult:
    """The observable result of one resumable scene execution attempt."""

    reason: str
    turns: int
    transcript: Transcript


@dataclass
class DirectorGameState:
    """The minimal TTRPG state that makes a scene objective consequential."""

    scene_objective: str | None = None
    clocks: dict[str, int] = field(
        default_factory=lambda: {"mission": 0, "danger": 0, "mystery": 0, "relationship": 0}
    )
    last_state_change: str | None = None
    last_pressure: str | None = None
    pending_magic_challenge: str | None = None
    pending_magic_success_criteria: str | None = None
    pending_magic_actor: str | None = None
    pending_magic_modifier: int = 0
    pending_magic_result: str | None = None
    pending_magic_adjudication: MagicAdjudication | None = None
    last_magic_roll: dict[str, object] | None = None
    last_magic_adjudication: MagicAdjudication | None = None

    def as_payload(self) -> dict[str, object]:
        return {
            "scene_objective": self.scene_objective or "",
            "clocks": dict(self.clocks),
            "last_state_change": self.last_state_change,
            "last_pressure": self.last_pressure,
            "pending_magic_challenge": self.pending_magic_challenge,
            "pending_magic_success_criteria": self.pending_magic_success_criteria,
            "pending_magic_actor": self.pending_magic_actor,
            "pending_magic_modifier": self.pending_magic_modifier,
            "pending_magic_result": self.pending_magic_result,
            "pending_magic_adjudication": (
                self.pending_magic_adjudication.model_dump(mode="json")
                if self.pending_magic_adjudication is not None
                else None
            ),
            "last_magic_roll": self.last_magic_roll,
            "last_magic_adjudication": (
                self.last_magic_adjudication.model_dump(mode="json")
                if self.last_magic_adjudication is not None
                else None
            ),
        }

    def apply(
        self,
        plan: DirectorPlanEnvelope,
        *,
        magic_adjudication: MagicAdjudication | None = None,
    ) -> None:
        self.scene_objective = self.scene_objective or plan.scene_objective
        for change in plan.clock_changes:
            self.clocks[change.clock] = self.clocks.get(change.clock, 0) + change.change
        self.last_state_change = plan.state_change
        self.last_pressure = plan.pressure
        if magic_adjudication is not None:
            self.finalize_magic_adjudication(magic_adjudication)
        self.apply_magic_fields(
            magic_challenge=plan.magic_challenge,
            magic_success_criteria=plan.magic_success_criteria,
            next_actor=plan.next_actor,
            magic_modifier=plan.magic_modifier,
        )

    def apply_magic_fields(
        self,
        *,
        magic_challenge: str | None,
        magic_success_criteria: str | None,
        next_actor: str | None,
        magic_modifier: int,
    ) -> None:
        self.pending_magic_challenge = magic_challenge
        if magic_challenge is not None:
            self.pending_magic_success_criteria = magic_success_criteria
        else:
            self.pending_magic_success_criteria = None
        self.pending_magic_actor = next_actor if magic_challenge else None
        self.pending_magic_modifier = magic_modifier if magic_challenge else 0

    def finalize_magic_adjudication(self, adjudication: MagicAdjudication) -> None:
        """Commit the runtime-derived result after its consequence is accepted."""

        if self.pending_magic_adjudication is not None:
            if self.pending_magic_adjudication != adjudication:
                raise ValueError("MAGIC adjudication does not match the pending roll")
        self.last_magic_adjudication = adjudication
        self.pending_magic_adjudication = None
        self.pending_magic_result = None
        self.pending_magic_success_criteria = None

    def challenge_for(self, *, character_id: str, name: str) -> str | None:
        if self.pending_magic_challenge is None or self.pending_magic_actor is None:
            return None
        pending = self.pending_magic_actor.casefold()
        return (
            self.pending_magic_challenge
            if pending in {character_id.casefold(), name.casefold()}
            else None
        )

    def answer_magic_challenge(
        self,
        *,
        character_id: str,
        name: str,
        roll: dict[str, object] | None = None,
    ) -> None:
        if self.challenge_for(character_id=character_id, name=name) is None:
            return
        if roll is not None:
            self.record_magic_roll(roll)
            return
        self.pending_magic_challenge = None
        self.pending_magic_actor = None
        self.pending_magic_modifier = 0

    def record_magic_roll(self, roll: dict[str, object]) -> None:
        success_criteria = str(roll.get("success_criteria", "")).strip()
        result = MagicRollResult(
            attribute=MagicAttribute(str(roll["attribute"])),
            attribute_score=int(roll["attribute_score"]),
            die_faces=(int(roll["die_faces"][0]), int(roll["die_faces"][1])),
            situational_modifier=int(roll["situational_modifier"]),
            total=int(roll["total"]),
            outcome=str(roll["outcome"]),
        )
        adjudication = adjudicate_magic_roll(result, success_criteria=success_criteria)
        self.last_magic_roll = dict(roll)
        self.pending_magic_result = result.outcome.value
        self.pending_magic_adjudication = adjudication
        self.pending_magic_challenge = None
        self.pending_magic_actor = None
        self.pending_magic_modifier = 0


@dataclass
class SceneRunner:
    """Run one shared scene while checkpointing every accepted disposition.

    The runner deliberately keeps model output parsing and acceptance separate:
    a failed or malformed call remains in the model-call audit, while only a
    parsed, wellness-clear actor turn becomes a durable scene turn.
    """

    run_id: str
    opening: OpeningSnapshot
    private_plan: HiddenSeasonPlan
    actors: tuple[SceneActor, ...]
    orchestrator: ModelCallExecutor
    day_number: int = 1
    slot_number: int = 1
    scheduled_local: str | None = None
    previous_shared_outcome: str | None = None
    prior_accepted_canon: tuple[str, ...] = ()
    private_day_direction: str | None = None
    episode_phase: str = "open_play"
    phase_directive: str = ""
    required_lore_entry_ids: tuple[str, ...] = ()
    required_story_terms: tuple[str, ...] = ()
    forbidden_story_terms: tuple[str, ...] = ()
    world_books: tuple[WorldBook, ...] = ()
    sessions_per_day: int = 3
    prior_actor_texts: tuple[str, ...] = ()
    prior_stage_narrations: tuple[str, ...] = ()
    enforce_narrative_acceptance: bool = False
    two_pass_directing: bool = False
    max_rounds: int = 4
    max_actor_turns: int = 16
    require_magic_challenge: bool = False
    required_magic_next_actor: str | None = None
    required_magic_challenge_text: str | None = None
    required_magic_modifier: int | None = None
    required_magic_opening_plan: DirectorPlanEnvelope | None = None
    forbidden_magic_attempt_terms: tuple[str, ...] = ()
    forbidden_magic_result_terms: tuple[str, ...] = ()
    max_duration: timedelta = timedelta(minutes=30)
    enforce_wall_time_limit: bool = True
    reviewer: Callable[[SceneActor, str], SafetyIssue | None] | None = None
    round_observer: Callable[["SceneRunner", int], None] | None = None
    wellness: WellnessService | None = None
    die_roller: Callable[[], tuple[int, int]] | None = field(default=None, repr=False)
    records: RecordRepository = field(init=False)
    events: EventRepository = field(init=False)
    transcript: Transcript = field(init=False)
    _accepted: set[tuple[int, str]] = field(init=False, repr=False)
    _resolved: set[tuple[int, str]] = field(init=False, repr=False)
    _neutral_interruptions: set[tuple[int, str]] = field(init=False, repr=False)
    _correction_requested: set[tuple[int, str]] = field(init=False, repr=False)
    _correction_reasons: dict[tuple[int, str], str] = field(init=False, repr=False)
    _correction_rejected_texts: dict[tuple[int, str], str] = field(init=False, repr=False)
    _stage_rounds: set[int] = field(init=False, repr=False)
    _actor_memory: dict[str, list[str]] = field(init=False, repr=False)
    _accepted_canon: list[str] = field(init=False, repr=False)
    _accepted_actor_texts: set[str] = field(init=False, repr=False)
    _accepted_stage_narrations: set[str] = field(init=False, repr=False)
    _game_state: DirectorGameState = field(init=False, repr=False)
    _pending_director_plans: dict[int, DirectorPlanEnvelope] = field(init=False, repr=False)
    _started_at: datetime = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not 2 <= len(self.actors) <= 4:
            raise ValueError("a shared scene requires two to four actors")
        if not 1 <= self.day_number <= 7:
            raise ValueError("day_number must be within the seven-day mission")
        if not 1 <= self.sessions_per_day <= 3:
            raise ValueError("sessions_per_day must be between one and three")
        if not 1 <= self.slot_number <= self.sessions_per_day:
            raise ValueError("slot_number must be within the configured daily sessions")
        if self.max_rounds < 1 or self.max_actor_turns < 1:
            raise ValueError("scene limits must be positive")
        if self.max_duration.total_seconds() <= 0:
            raise ValueError("max_duration must be positive")
        actor_ids = {actor.character_id for actor in self.actors}
        if len(actor_ids) != len(self.actors):
            raise ValueError("actor character IDs must be unique")
        if {actor.name for actor in self.actors} != set(self.opening.cast):
            raise ValueError("scene actors must match the approved opening cast")
        for actor in self.actors:
            if actor.role_sheet.character_id != actor.character_id:
                raise ValueError(f"role sheet does not belong to {actor.character_id}")
        self.records = RecordRepository(self.orchestrator.database)
        self.events = EventRepository(self.orchestrator.database)
        self.transcript = Transcript()
        self._accepted = set()
        self._resolved = set()
        self._neutral_interruptions = set()
        self._correction_requested = set()
        self._correction_reasons = {}
        self._correction_rejected_texts = {}
        self._stage_rounds = set()
        self._actor_memory = {
            actor.character_id: list(actor.known_memory) for actor in self.actors
        }
        self._accepted_canon = list(self.prior_accepted_canon)
        self._accepted_actor_texts = {
            _normalized_story_text(value) for value in self.prior_actor_texts if _normalized_story_text(value)
        }
        self._accepted_stage_narrations = {
            _normalized_story_text(value) for value in self.prior_stage_narrations if _normalized_story_text(value)
        }
        self._accepted_actor_texts = {
            _normalized_story_text(value) for value in self.prior_actor_texts if _normalized_story_text(value)
        }
        self._accepted_stage_narrations = {
            _normalized_story_text(value) for value in self.prior_stage_narrations if _normalized_story_text(value)
        }
        self._game_state = DirectorGameState()
        self._pending_director_plans = {}
        self._started_at = self.orchestrator.clock.now()

    async def execute(self, *, resume: bool = True) -> SceneRunResult:
        """Execute or resume the run, returning at its first safe terminal state."""
        row = self.records.get_run(self.run_id)
        if row is None:
            raise SceneRunError("unknown_run")
        status = str(row["status"])
        if status == "COMPLETED":
            self._hydrate()
            return SceneRunResult(
                reason=str(row["completion_reason"] or "completed"),
                turns=len(self._accepted),
                transcript=self.transcript,
            )
        if status == "INTERRUPTED" and not resume:
            raise SceneRunError("resume_required")
        if status not in {"QUEUED", "RUNNING", "INTERRUPTED"}:
            raise SceneRunError(f"run_not_executable:{status}")

        if status != "RUNNING":
            self.records.update_run_status(
                run_id=self.run_id,
                status="RUNNING",
                completion_reason=None,
                expected_status=status,
            )
        self._started_at = self.orchestrator.clock.now()
        self._hydrate()

        for round_number in range(1, self.max_rounds + 1):
            if len(self._accepted) >= self.max_actor_turns:
                return self._complete("turn_limit")

            round_actors = [
                actor
                for actor in self.actors
                if (round_number, actor.character_id) not in self._resolved
            ]
            if not round_actors:
                continue

            if round_number not in self._stage_rounds:
                if self._time_limit_reached():
                    return self._complete("time_limit")
                decision, decision_attempt, decision_call_id = await self._call_orchestrator(round_number)
                if self._time_limit_reached():
                    return self._complete("time_limit")
                self._persist_orchestrator_decision(
                    round_number, decision, decision_attempt, decision_call_id
                )
                if decision.complete:
                    return self._complete("natural_completion")

            order = self._ordered_actors(
                next_actor=self._stage_next_actor(round_number),
                remaining=round_actors,
            )
            for actor in order:
                if len(self._accepted) >= self.max_actor_turns:
                    return self._complete("turn_limit")
                if (round_number, actor.character_id) in self._resolved:
                    continue
                if self._time_limit_reached():
                    return self._complete("time_limit")
                stopped = await self._run_actor_turn(actor, round_number)
                if stopped is not None:
                    return stopped

            if self.round_observer is not None:
                self.round_observer(self, round_number)

        return self._complete("turn_limit" if len(self._accepted) >= self.max_actor_turns else "round_limit")

    def _hydrate(self) -> None:
        """Rebuild the readable script and progress sets from durable records."""
        self.transcript = Transcript()
        self.transcript.add_direction(self._opening_direction())
        self._accepted = set()
        self._resolved = set()
        self._neutral_interruptions = set()
        self._correction_requested = set()
        self._correction_reasons = {}
        self._correction_rejected_texts = {}
        self._stage_rounds = set()
        self._actor_memory = {
            actor.character_id: list(actor.known_memory) for actor in self.actors
        }
        self._accepted_canon = list(self.prior_accepted_canon)
        self._game_state = DirectorGameState()
        self._pending_director_plans = {}
        actor_names = {actor.character_id: actor.name for actor in self.actors}
        stored_rows = self.records.list_turns(self.run_id)
        event_rows = self.events.list_for_aggregate(self.run_id)
        rolls_by_turn: dict[str, dict[str, object]] = {}
        for event_row in event_rows:
            if str(event_row["event_type"]) != "MagicRollResolved":
                continue
            try:
                roll_payload = json.loads(event_row["payload_json"])
            except (TypeError, ValueError):
                continue
            rolls_by_turn[str(roll_payload.get("turn_id", ""))] = roll_payload
        turn_by_id = {str(row["turn_id"]): row for row in stored_rows}
        explicit_order = bool(stored_rows) and all(
            row["accepted_sequence"] is not None for row in stored_rows
        )
        if explicit_order:
            for row in stored_rows:
                if str(row["disposition"]) == "NARRATION_ACCEPT":
                    continue
                parent_id = row["caused_by_turn_id"]
                parent = turn_by_id.get(str(parent_id)) if parent_id else None
                if (
                    parent is None
                    or str(parent["disposition"]) != "NARRATION_ACCEPT"
                    or int(parent["round_number"]) != int(row["round_number"])
                ):
                    explicit_order = False
                    break
        if explicit_order:
            rows = sorted(stored_rows, key=lambda row: int(row["accepted_sequence"]))
        else:
            rows = sorted(
                stored_rows,
                key=lambda row: (
                    int(row["round_number"]),
                    0 if str(row["disposition"]) == "NARRATION_ACCEPT" else 1,
                    int(row["insertion_order"]),
                ),
            )
        for row in rows:
            disposition = str(row["disposition"])
            if disposition == "NEUTRAL_INTERRUPTION":
                round_number = int(row["round_number"])
                character_id = str(row["character_id"])
                original_character_id = character_id.removeprefix(_NEUTRAL_CHARACTER_PREFIX)
                key = (round_number, original_character_id)
                self._neutral_interruptions.add(key)
                self._resolved.add(key)
                path = row["content_path"]
                if path:
                    content = Path(str(path)).read_text(encoding="utf-8")
                    self.transcript.add_direction(content)
                continue
            if disposition not in {"ACCEPT", "ACCEPT_AFTER_CORRECTION", "NARRATION_ACCEPT"}:
                continue
            path = row["content_path"]
            if not path:
                raise SceneRunError(f"accepted_artifact_missing:{row['turn_id']}")
            content = Path(str(path)).read_text(encoding="utf-8")
            round_number = int(row["round_number"])
            character_id = str(row["character_id"])
            if character_id == _STAGE_CHARACTER_ID:
                self._stage_rounds.add(round_number)
                self._accepted_stage_narrations.add(_normalized_story_text(content))
                if content:
                    self.transcript.add_direction(content)
            elif character_id in actor_names:
                self._accepted.add((round_number, character_id))
                self._accepted_actor_texts.add(_normalized_story_text(content))
                self._resolved.add((round_number, character_id))
                self.transcript.add_line(actor_names[character_id], content)
                turn_id = str(row["turn_id"])
                if turn_id in rolls_by_turn:
                    self.transcript.add_direction(_magic_roll_summary(rolls_by_turn[turn_id]))
            else:
                raise SceneRunError(f"unknown_actor_in_run:{character_id}")

        for row in event_rows:
            event_type = str(row["event_type"])
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, ValueError):
                continue
            if event_type == "OrchestratorRoundAccepted":
                self._accepted_canon.extend(payload.get("canon_updates", []))
                magic_state = payload.get("magic_state")
                if isinstance(magic_state, dict):
                    self._game_state.apply_magic_fields(
                        magic_challenge=magic_state.get("magic_challenge"),
                        magic_success_criteria=magic_state.get("magic_success_criteria"),
                        next_actor=magic_state.get("next_actor"),
                        magic_modifier=int(magic_state.get("magic_modifier", 0)),
                    )
            elif event_type == "DirectorPlanAccepted":
                try:
                    plan_payload = _runtime_director_plan_payload(payload["plan"])
                    plan = DirectorPlanEnvelope.model_validate(plan_payload)
                    stored_adjudication = payload.get("magic_adjudication")
                    adjudication = (
                        MagicAdjudication.model_validate(stored_adjudication)
                        if stored_adjudication is not None
                        else self._game_state.pending_magic_adjudication
                    )
                    self._game_state.apply(plan, magic_adjudication=adjudication)
                except (KeyError, TypeError, ValueError):
                    raise SceneRunError("director_plan_event_invalid") from None
            elif event_type == "TurnAccepted":
                character_id = str(payload.get("character_id", ""))
                self._actor_memory.setdefault(character_id, []).extend(
                    str(note) for note in payload.get("memory_notes", [])
                )
                if bool(payload.get("magic_challenge_answered")):
                    self._game_state.answer_magic_challenge(
                        character_id=character_id,
                        name=actor_names.get(character_id, character_id),
                    )
            elif event_type == "MagicRollResolved":
                self._game_state.record_magic_roll(payload)
            elif event_type == "NeutralInterruptionInserted":
                character_id = str(payload.get("character_id", ""))
                if bool(payload.get("magic_challenge_answered")):
                    self._game_state.answer_magic_challenge(
                        character_id=character_id,
                        name=actor_names.get(character_id, character_id),
                    )
            elif event_type == "CorrectionRequested":
                key = (int(payload["round_number"]), str(payload["character_id"]))
                self._correction_requested.add(key)
                reason = str(payload.get("reason", "content review"))
                if payload.get("code") == "MAGIC_ATTEMPT_PREMATURE_RESULT":
                    reason = f"MAGIC_ATTEMPT_PREMATURE_RESULT: {reason}"
                self._correction_reasons[key] = reason
            elif event_type == "TurnDisposition":
                key = (int(payload["round_number"]), str(payload["character_id"]))
                content_path = payload.get("content_path")
                content = ""
                if content_path:
                    content = Path(str(content_path)).read_text(encoding="utf-8")
                detail = str(payload.get("reason", "content review"))
                self._correction_rejected_texts[key] = content
                self.transcript.add_audit(
                    f"CONTENT REVIEW — NOT CANON ({detail})\n{content}".rstrip()
                )
                if bool(payload.get("final")):
                    self._resolved.add(key)

        if len(self._accepted) > self.max_actor_turns:
            raise SceneRunError("durable_turn_count_exceeds_limit")

    async def _run_actor_turn(
        self, actor: SceneActor, round_number: int
    ) -> SceneRunResult | None:
        """Run one actor slot, including at most one private correction."""
        key = (round_number, actor.character_id)
        correction = key in self._correction_requested
        correction_reason = self._correction_reasons.get(key)
        correction_rejected_text = self._correction_rejected_texts.get(key)
        while True:
            if self._time_limit_reached():
                return self._complete("time_limit")
            envelope, call_attempt, call_id = await self._call_actor(
                actor,
                round_number,
                correction_reason=correction_reason if correction else None,
                correction_rejected_text=correction_rejected_text if correction else None,
            )
            if self._time_limit_reached():
                return self._complete("time_limit")
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
                        context=f"scene:{self.run_id}:round:{round_number}",
                        raw_signal=envelope.wellness_signal,
                        intervention="scene paused and redirected",
                    )
                self.events.append(
                    event_id=f"{self.run_id}:wellness:{round_number}:{actor.character_id}",
                    natural_key=f"{self.run_id}:wellness:{round_number}:{actor.character_id}",
                    aggregate_type="run",
                    aggregate_id=self.run_id,
                    event_type="WellnessSignalObserved",
                    payload={
                            "round_number": round_number,
                            "character_id": actor.character_id,
                            "signal_number": (
                                wellness_result.signal_number if wellness_result else None
                            ),
                            "tapped_out": (
                                wellness_result.tapped_out if wellness_result else False
                            ),
                        },
                )
                return self._interrupt("wellness_redirect")
            text = clean_line(
                envelope.text,
                actor.name,
                [
                    candidate.name
                    for candidate in self.actors
                    if candidate.character_id != actor.character_id
                ],
            )
            issue = (
                SafetyIssue("EMPTY_TURN", "empty actor turn")
                if not text
                else self._review(actor, text)
            )
            if (
                issue is None
                and envelope.magic_stat is not None
                and self._game_state.challenge_for(
                    character_id=actor.character_id, name=actor.name
                )
                is None
            ):
                issue = SafetyIssue(
                    "MAGIC_STAT_WITHOUT_CHALLENGE",
                    "MAGIC_STAT may be used only for the character's pending challenge",
                )
            if issue is None and envelope.magic_stat is not None:
                issue = self._review_magic_attempt_text(text)
            if issue is None and correction and correction_rejected_text:
                is_magic_result_repair = bool(
                    correction_reason
                    and correction_reason.startswith("MAGIC_ATTEMPT_PREMATURE_RESULT:")
                )
                if not is_magic_result_repair:
                    issue = review_correction_scope(correction_rejected_text, text)
            if issue is None:
                self._persist_actor_turn(
                    actor,
                    round_number,
                    text,
                    envelope,
                    call_attempt,
                    call_id,
                    disposition="ACCEPT_AFTER_CORRECTION" if correction else "ACCEPT",
                )
                return None

            self._persist_noncanon(actor, round_number, text, call_attempt, call_id, issue)
            if not correction:
                self.events.append(
                    event_id=f"{self.run_id}:correction-requested:{round_number}:{actor.character_id}",
                    natural_key=f"{self.run_id}:correction-requested:{round_number}:{actor.character_id}",
                    aggregate_type="run",
                    aggregate_id=self.run_id,
                    event_type="CorrectionRequested",
                    payload={
                        "round_number": round_number,
                        "character_id": actor.character_id,
                        "reason": issue.detail,
                        "code": issue.code,
                    },
                )
                self._correction_requested.add(key)
                next_correction_reason = (
                    f"{issue.code}: {issue.detail}"
                    if issue.code == "MAGIC_ATTEMPT_PREMATURE_RESULT"
                    else issue.detail
                )
                self._correction_reasons[key] = next_correction_reason
                self._correction_rejected_texts[key] = text
                correction = True
                correction_reason = next_correction_reason
                correction_rejected_text = text
                continue

            self._persist_neutral_interruption(actor, round_number, issue)
            self._resolved.add(key)
            return None

    def _review(self, actor: SceneActor, text: str) -> SafetyIssue | None:
        if self.reviewer is not None:
            return self.reviewer(actor, text)
        issue = review_actor_text(
            text,
            actor_name=actor.name,
            other_actor_names=[
                candidate.name
                for candidate in self.actors
                if candidate.character_id != actor.character_id
            ],
        )
        if issue is not None:
            return issue
        if self.enforce_narrative_acceptance and _normalized_story_text(text) in self._accepted_actor_texts:
            return SafetyIssue("EXACT_REPEAT", "turn repeats accepted shared text")
        return None

    def _review_magic_attempt_text(self, text: str) -> SafetyIssue | None:
        """Keep configured challenge answers out of the actor's pre-roll attempt."""

        if not self.forbidden_magic_attempt_terms:
            return None
        matched = self._forbidden_magic_attempt_terms_in_text(text)
        if matched:
            return SafetyIssue(
                "MAGIC_ATTEMPT_PREMATURE_RESULT",
                "the MAGIC attempt states a result or diagnosis before the roll; rewrite it as "
                "an observable method without naming the conclusion (matched: "
                + ", ".join(matched)
                + ")",
            )
        return None

    def _forbidden_magic_attempt_terms_in_text(self, text: str) -> tuple[str, ...]:
        lowered = text.casefold()
        return tuple(
            term
            for term in self.forbidden_magic_attempt_terms
            if term.casefold() in lowered
        )

    async def _call_orchestrator(
        self, round_number: int
    ) -> tuple[OrchestratorEnvelope, int, str]:
        # A pending MAGIC result always takes the structured planning path,
        # even for callers that use single-pass directing for ordinary beats.
        # Free-form narration must never adjudicate a recorded roll.
        if self.two_pass_directing or self._game_state.pending_magic_adjudication is not None:
            return await self._call_two_pass_orchestrator(round_number)
        return await self._call_single_pass_orchestrator(round_number)

    async def _call_single_pass_orchestrator(
        self, round_number: int
    ) -> tuple[OrchestratorEnvelope, int, str]:
        purpose = f"orchestrator_round:{round_number}"
        attempt = self.orchestrator.calls.next_attempt(run_id=self.run_id, purpose=purpose)
        call_id = f"{self.run_id}:orchestrator:r{round_number}:a{attempt}"
        scene_lines = self._scene_lines()
        spent_imagery_terms = spent_director_imagery(scene_lines)
        continuity_anchors = continuity_anchors_for_opening(self.opening)
        messages = build_orchestrator_messages(
            opening=self.opening,
            private_plan=self.private_plan,
            accepted_canon=self._accepted_canon,
            scene_transcript=self._orchestrator_scene_lines(),
            mission_clock=self._mission_clock(),
            previous_shared_outcome=self.previous_shared_outcome,
            private_day_direction=self.private_day_direction,
            round_number=round_number,
            max_rounds=self.max_rounds,
            spent_director_terms=spent_imagery_terms,
            game_state=self._game_state.as_payload(),
        )
        magic_setup_directive = self._magic_rehearsal_setup_directive(round_number)
        if magic_setup_directive is not None:
            messages.append(
                {
                    "role": "system",
                    "content": magic_setup_directive,
                }
            )
        messages.append(
            {
                "role": "system",
                "content": (
                    "Return one complete director response. Narration is required and must be "
                    "shared, sensory scene material only, under 120 words, and must not name "
                    "or describe any cast member. The cast will make their own moves after the "
                    "beat. This rehearsal rejects narration that uses more than two terms from "
                    f"this exact spent list: {', '.join(spent_imagery_terms) or '(none)'}. "
                    f"Use one exact setting anchor from: {', '.join(continuity_anchors)}. "
                    "Make the cast's concrete fork explicit as two possible actions, not merely a "
                    "changed atmosphere. next_actor is optional; if included, it must be exactly one "
                    "cast name—never a list or ordering. complete is a boolean; "
                    "include at least one canon_update naming the new resource, constraint, or knowledge; "
                    "canon_updates are at most two concise factual strings. Do not put response-envelope "
                    "markup inside narration. A MAGIC challenge is optional, only for meaningful "
                    "uncertainty, and must name next_actor; the runtime derives any recorded result "
                    "after the actor's accepted check."
                ),
            }
        )
        result = await self.orchestrator.execute(
            call_id=call_id,
            run_id=self.run_id,
            purpose=purpose,
            attempt=attempt,
            messages=messages,
            schema_name="orchestrator",
            tagged_format_instructions=(
                "<NARRATION>...</NARRATION><NEXT_ACTOR>...</NEXT_ACTOR>"
                "<COMPLETE>true|false</COMPLETE><CANON_UPDATE>...</CANON_UPDATE>"
                "<MAGIC_CHALLENGE>none or meaningful uncertainty</MAGIC_CHALLENGE>"
                "<MAGIC_SUCCESS_CRITERIA>observable result that counts as success</MAGIC_SUCCESS_CRITERIA>"
                "<MAGIC_MODIFIER>-2..2</MAGIC_MODIFIER>"
            ),
            character_id=_STAGE_CHARACTER_ID,
            prompt_version_id="scene-director-v9-magic-success-criteria",
            context_version_id=f"scene:{self.run_id}:round:{round_number}:v1",
            role_sheet_version_id=f"hidden-plan:v{self.private_plan.version}",
        )
        if result.status is not NormalizedCallStatus.COMPLETED:
            return self._raise_interrupt(
                f"orchestrator_call_{result.status.value.lower()}",
                error_type=result.error_type,
            )
        try:
            decision = parse_orchestrator_output(result.text)
        except StructuredOutputError:
            self.orchestrator.calls.record_diagnostics(
                call_id=call_id,
                parse_status="REJECTED",
                validation_status="NOT_REACHED",
                acceptance_status="REJECTED",
                render_status="NOT_RENDERED",
                validator_code="STRUCTURED_OUTPUT_INVALID",
            )
            return self._raise_interrupt("orchestrator_output_invalid")
        issue = self._review_required_magic_setup(
            next_actor=decision.next_actor,
            challenge=decision.magic_challenge,
            success_criteria=decision.magic_success_criteria,
            modifier=decision.magic_modifier,
            round_number=round_number,
        )
        if (
            issue is None
            and decision.magic_challenge is not None
            and decision.next_actor.casefold()
            not in {
                value
                for actor in self.actors
                for value in (actor.name.casefold(), actor.character_id.casefold())
            }
        ):
            issue = SafetyIssue(
                "MAGIC_CHALLENGE_ACTOR_INVALID",
                "a MAGIC challenge must designate exactly one cast member as next_actor",
            )
        if issue is None:
            issue = review_orchestrator_narration(
                decision.narration,
                actor_names=[actor.name for actor in self.actors],
                continuity_anchors=(
                    continuity_anchors if self.enforce_narrative_acceptance else ()
                ),
                spent_imagery=(
                    spent_imagery_terms if self.enforce_narrative_acceptance else ()
                ),
            )
        if (
            issue is None
            and self.enforce_narrative_acceptance
            and decision.next_actor
            and decision.next_actor.casefold()
            not in {value for actor in self.actors for value in (actor.name.casefold(), actor.character_id.casefold())}
        ):
            issue = SafetyIssue(
                "NEXT_ACTOR_INVALID",
                "next_actor must be omitted or name exactly one cast member",
            )
        if issue is None and self.enforce_narrative_acceptance and not decision.canon_updates:
            issue = SafetyIssue(
                "CANON_UPDATE_REQUIRED",
                "director beat must record a new resource, constraint, or piece of knowledge",
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
            return self._raise_interrupt(
                "orchestrator_actor_puppeteering"
                if issue.code == "ACTOR_PUPPETEERING"
                else "orchestrator_director_contract_invalid"
            )
        if self.enforce_narrative_acceptance and _normalized_story_text(decision.narration) in self._accepted_stage_narrations:
            self.orchestrator.calls.record_diagnostics(
                call_id=call_id,
                parse_status="PARSED",
                validation_status="REJECTED",
                acceptance_status="REJECTED",
                render_status="NOT_RENDERED",
                validator_code="EXACT_REPEAT",
                validator_detail="director narration repeats accepted shared text",
            )
            return self._raise_interrupt("orchestrator_repeated_narration")
        self.orchestrator.calls.record_diagnostics(
            call_id=call_id,
            parse_status="PARSED",
            validation_status="VALID",
            acceptance_status="PENDING",
            render_status="PENDING",
        )
        return decision, attempt, call_id

    async def _call_two_pass_orchestrator(
        self, round_number: int
    ) -> tuple[OrchestratorEnvelope, int, str]:
        """Plan the game state first, then render that fixed decision as prose."""

        plan_purpose = f"director_plan_round:{round_number}"
        plan_attempt = self.orchestrator.calls.next_attempt(
            run_id=self.run_id, purpose=plan_purpose
        )
        plan_call_id = f"{self.run_id}:director-plan:r{round_number}:a{plan_attempt}"
        plan_messages = build_director_plan_messages(
            opening=self.opening,
            private_plan=self.private_plan,
            accepted_canon=self._accepted_canon,
            scene_transcript=self._orchestrator_scene_lines(),
            game_state=self._game_state.as_payload(),
            mission_clock=self._mission_clock(),
            previous_shared_outcome=self.previous_shared_outcome,
            private_day_direction=self.private_day_direction,
            round_number=round_number,
            max_rounds=self.max_rounds,
            spent_director_terms=self._active_plan_spent_imagery(),
            episode_phase=self.episode_phase,
            phase_directive=self.phase_directive,
            required_story_terms=self.required_story_terms,
            forbidden_story_terms=self.forbidden_story_terms,
            active_lore=self._active_director_lore(),
        )
        magic_setup_directive = self._magic_rehearsal_setup_directive(round_number)
        if magic_setup_directive is not None:
            plan_messages.append(
                {
                    "role": "system",
                    "content": magic_setup_directive,
                }
            )
        magic_result_directive = self._magic_result_contract_directive()
        if magic_result_directive is not None:
            plan_messages.append({"role": "system", "content": magic_result_directive})
        plan_result = await self.orchestrator.execute(
            call_id=plan_call_id,
            run_id=self.run_id,
            purpose=plan_purpose,
            attempt=plan_attempt,
            messages=plan_messages,
            schema_name="director_plan",
            tagged_format_instructions=(
                "<SCENE_OBJECTIVE>...</SCENE_OBJECTIVE><ADJUDICATION>...</ADJUDICATION>"
                "<STATE_CHANGE>...</STATE_CHANGE><PRESSURE>...</PRESSURE>"
                "<CHOICE_A>...</CHOICE_A><CHOICE_B>...</CHOICE_B>"
                "<NEXT_ACTOR>one cast name</NEXT_ACTOR><COMPLETE>true|false</COMPLETE>"
                "<CLOCK_CHANGE>mission:+1</CLOCK_CHANGE>"
                "<CANON_UPDATE>...</CANON_UPDATE>"
                "<MAGIC_CHALLENGE>none or a meaningful uncertain action</MAGIC_CHALLENGE>"
                "<MAGIC_SUCCESS_CRITERIA>observable result that counts as success</MAGIC_SUCCESS_CRITERIA>"
                "<MAGIC_MODIFIER>-2..2</MAGIC_MODIFIER>"
                "<MAGIC_COST_TYPE>none|time|position|trust|access|resources</MAGIC_COST_TYPE>"
                "<MAGIC_EFFECT_DETAIL>none or one short observable consequence</MAGIC_EFFECT_DETAIL>"
            ),
            character_id=_STAGE_CHARACTER_ID,
            prompt_version_id="scene-director-plan-v6-magic-plan-contract",
            context_version_id=f"scene:{self.run_id}:round:{round_number}:game:v5",
            role_sheet_version_id=f"hidden-plan:v{self.private_plan.version}",
        )
        if plan_result.status is not NormalizedCallStatus.COMPLETED:
            return self._raise_interrupt(
                f"director_plan_call_{plan_result.status.value.lower()}",
                error_type=plan_result.error_type,
            )
        try:
            plan = parse_director_plan_output(plan_result.text)
        except StructuredOutputError:
            self.orchestrator.calls.record_diagnostics(
                call_id=plan_call_id,
                parse_status="REJECTED",
                validation_status="NOT_REACHED",
                acceptance_status="REJECTED",
                render_status="NOT_RENDERED",
                validator_code="DIRECTOR_PLAN_STRUCTURED_OUTPUT_INVALID",
            )
            return self._raise_interrupt("director_plan_output_invalid")
        repaired_fields: tuple[str, ...] = ()
        plan_issue = self._review_director_plan(plan, round_number)
        if plan_issue is not None:
            self.orchestrator.calls.record_diagnostics(
                call_id=plan_call_id,
                parse_status="PARSED",
                validation_status="REJECTED",
                acceptance_status="REJECTED",
                render_status="NOT_RENDERED",
                validator_code=plan_issue.code,
                validator_detail=plan_issue.detail,
            )
            rejected_plan_call_id = plan_call_id
            rejected_plan = plan
            rejected_plan_issue = plan_issue
            forbidden_magic_terms = self._forbidden_magic_result_terms_in_plan(plan)
            plan_attempt = self.orchestrator.calls.next_attempt(
                run_id=self.run_id, purpose=plan_purpose
            )
            plan_call_id = f"{self.run_id}:director-plan:r{round_number}:a{plan_attempt}"
            correction_messages = [
                *plan_messages,
                {
                    "role": "system",
                    "content": (
                        "Correct exactly one rejected director plan. Preserve the scene_objective "
                        "exactly and preserve the adjudication, state change, pressure, clock "
                        "changes, next actor, every safe canon fact, costs, and dramatic function. "
                        "Change only the rejected mechanism or wording needed to satisfy the named "
                        "validator. Do not soften, defer, or replace the outcome; do not author a "
                        "player-character's action, response, dialogue, decision, thought, feeling, "
                        "or death. Keep choice A and choice B distinct actor-facing courses of action. "
                        "Copy every field from REJECTED PLAN verbatim unless that field itself contains "
                        "a forbidden story term or an explicitly identified forbidden MAGIC result term. "
                        "Do not paraphrase safe choices, canon facts, costs, "
                        "clock changes, or the next actor. If only the adjudication contains the "
                        "forbidden term, every other field must be character-for-character identical. "
                        "For EPISODE_SPINE_FALLBACK_REUSED, remove every forbidden story term and "
                        "replace its mechanism with a genuinely new action, resource, or constraint "
                        "appropriate to the current act—not a synonym, euphemism, or replay. Return "
                        "one complete corrected structured plan without explanation.\n"
                        f"{_director_plan_correction_instruction(plan_issue.code, forbidden_magic_terms=forbidden_magic_terms)}\n"
                        f"REJECTION CODE: {plan_issue.code}\n"
                        f"REJECTION REASON: {plan_issue.detail}\n"
                        "FORBIDDEN STORY TERMS: "
                        f"{', '.join(self.forbidden_story_terms) or '(none)'}\n"
                        "FORBIDDEN MAGIC RESULT TERMS FOUND IN REJECTED PLAN: "
                        f"{', '.join(forbidden_magic_terms) or '(none)'}\n"
                        "REJECTED PLAN: "
                        f"{rejected_plan.model_dump_json()}"
                    ),
                },
            ]
            if magic_setup_directive is not None and plan_issue.code in {
                "MAGIC_CHALLENGE_SETUP_REQUIRED",
                "MAGIC_SUCCESS_CRITERIA_REQUIRED",
                "MAGIC_REHEARSAL_OPENING_LOCKED",
            }:
                correction_messages.append(
                    {
                        "role": "system",
                        "content": (
                            f"{magic_setup_directive} These required setup fields override the "
                            "general instruction to preserve the rejected plan. For the locked "
                            "opening, reproduce every field of the supplied plan exactly; that "
                            "locked plan overrides any conflicting rejected field."
                        ),
                    }
                )
            if self._game_state.pending_magic_adjudication is not None:
                correction_messages.append(
                    {
                        "role": "system",
                        "content": self._magic_result_correction_directive(forbidden_magic_terms),
                    }
                )
            plan_result = await self.orchestrator.execute(
                call_id=plan_call_id,
                run_id=self.run_id,
                purpose=plan_purpose,
                attempt=plan_attempt,
                messages=correction_messages,
                schema_name="director_plan",
                tagged_format_instructions=(
                    "<SCENE_OBJECTIVE>...</SCENE_OBJECTIVE><ADJUDICATION>...</ADJUDICATION>"
                    "<STATE_CHANGE>...</STATE_CHANGE><PRESSURE>...</PRESSURE>"
                "<CHOICE_A>...</CHOICE_A><CHOICE_B>...</CHOICE_B>"
                "<NEXT_ACTOR>one cast name</NEXT_ACTOR><COMPLETE>true|false</COMPLETE>"
                "<CLOCK_CHANGE>mission:+1</CLOCK_CHANGE>"
                "<CANON_UPDATE>...</CANON_UPDATE>"
                "<MAGIC_CHALLENGE>none or a meaningful uncertain action</MAGIC_CHALLENGE>"
                "<MAGIC_SUCCESS_CRITERIA>observable result that counts as success</MAGIC_SUCCESS_CRITERIA>"
                "<MAGIC_MODIFIER>-2..2</MAGIC_MODIFIER>"
                "<MAGIC_COST_TYPE>none|time|position|trust|access|resources</MAGIC_COST_TYPE>"
                "<MAGIC_EFFECT_DETAIL>none or concise visible result/cost/opening</MAGIC_EFFECT_DETAIL>"
                ),
                character_id=_STAGE_CHARACTER_ID,
                prompt_version_id="scene-director-plan-correction-v3-magic-plan-contract",
                context_version_id=f"scene:{self.run_id}:round:{round_number}:game:correction:v2",
                role_sheet_version_id=f"hidden-plan:v{self.private_plan.version}",
                correction_of_call_id=rejected_plan_call_id,
            )
            if plan_result.status is not NormalizedCallStatus.COMPLETED:
                return self._raise_interrupt(
                    f"director_plan_correction_call_{plan_result.status.value.lower()}",
                    error_type=plan_result.error_type,
                )
            try:
                plan = parse_director_plan_output(plan_result.text)
            except StructuredOutputError:
                self.orchestrator.calls.record_diagnostics(
                    call_id=plan_call_id,
                    parse_status="REJECTED",
                    validation_status="NOT_REACHED",
                    acceptance_status="REJECTED",
                    render_status="NOT_RENDERED",
                    validator_code="DIRECTOR_PLAN_CORRECTION_STRUCTURED_OUTPUT_INVALID",
                )
                return self._raise_interrupt("director_plan_correction_output_invalid")
            plan_issue = self._review_director_plan(plan, round_number)
            if plan_issue is not None:
                self.orchestrator.calls.record_diagnostics(
                    call_id=plan_call_id,
                    parse_status="PARSED",
                    validation_status="REJECTED",
                    acceptance_status="REJECTED",
                    render_status="NOT_RENDERED",
                    validator_code=plan_issue.code,
                    validator_detail=plan_issue.detail,
                )
                return self._raise_interrupt("director_plan_contract_invalid")
            correction_scope_issue = self._review_director_plan_correction_scope(
                rejected_plan,
                plan,
                rejection_code=rejected_plan_issue.code,
            )
            if correction_scope_issue is not None:
                repaired_plan, repaired_fields = self._repair_director_plan_correction_scope(
                    rejected_plan,
                    plan,
                    rejection_code=rejected_plan_issue.code,
                )
                if repaired_plan is None:
                    self.orchestrator.calls.record_diagnostics(
                        call_id=plan_call_id,
                        parse_status="PARSED",
                        validation_status="REJECTED",
                        acceptance_status="REJECTED",
                        render_status="NOT_RENDERED",
                        validator_code=correction_scope_issue.code,
                        validator_detail=correction_scope_issue.detail,
                    )
                    return self._raise_interrupt("director_plan_correction_scope_invalid")
                plan = repaired_plan
                repaired_issue = self._review_director_plan(plan, round_number)
                if repaired_issue is not None:
                    self.orchestrator.calls.record_diagnostics(
                        call_id=plan_call_id,
                        parse_status="PARSED",
                        validation_status="REJECTED",
                        acceptance_status="REJECTED",
                        render_status="NOT_RENDERED",
                        validator_code=repaired_issue.code,
                        validator_detail=repaired_issue.detail,
                    )
                    return self._raise_interrupt("director_plan_contract_invalid")
                self.events.append(
                    event_id=f"{self.run_id}:director-plan-scope-repaired:{round_number}",
                    natural_key=f"{self.run_id}:director-plan-scope-repaired:{round_number}",
                    aggregate_type="run",
                    aggregate_id=self.run_id,
                    event_type="DirectorPlanCorrectionScopeRepaired",
                    payload={
                        "round_number": round_number,
                        "correction_call_id": plan_call_id,
                        "rejection_code": rejected_plan_issue.code,
                        "restored_fields": list(repaired_fields),
                        "detail": correction_scope_issue.detail,
                    },
                )
        self.orchestrator.calls.record_diagnostics(
            call_id=plan_call_id,
            parse_status="PARSED",
            validation_status="VALID",
            acceptance_status="ACCEPTED",
            render_status="NOT_RENDERED",
            validator_code=("DIRECTOR_PLAN_CORRECTION_SCOPE_REPAIRED" if repaired_fields else None),
            validator_detail=(
                "deterministically restored unaffected fields: " + ", ".join(repaired_fields)
                if repaired_fields
                else None
            ),
        )

        purpose = f"orchestrator_round:{round_number}"
        attempt = self.orchestrator.calls.next_attempt(run_id=self.run_id, purpose=purpose)
        call_id = f"{self.run_id}:orchestrator:r{round_number}:a{attempt}"
        spent_imagery_terms = self._active_plan_spent_imagery()
        continuity_anchors = continuity_anchors_for_opening(self.opening)
        render_result = await self.orchestrator.execute(
            call_id=call_id,
            run_id=self.run_id,
            purpose=purpose,
            attempt=attempt,
            messages=build_director_render_messages(
                plan=plan.model_dump(mode="json"),
                continuity_anchors=continuity_anchors,
                spent_director_terms=spent_imagery_terms,
            ),
            schema_name="director_render",
            tagged_format_instructions="<NARRATION>...</NARRATION>",
            character_id=_STAGE_CHARACTER_ID,
            prompt_version_id="scene-director-render-v1",
            context_version_id=f"scene:{self.run_id}:round:{round_number}:game:v1",
            role_sheet_version_id=f"hidden-plan:v{self.private_plan.version}",
        )
        if render_result.status is not NormalizedCallStatus.COMPLETED:
            return self._raise_interrupt(
                f"orchestrator_call_{render_result.status.value.lower()}",
                error_type=render_result.error_type,
            )
        try:
            rendered = parse_director_render_output(render_result.text)
        except StructuredOutputError:
            self.orchestrator.calls.record_diagnostics(
                call_id=call_id,
                parse_status="REJECTED",
                validation_status="NOT_REACHED",
                acceptance_status="REJECTED",
                render_status="NOT_RENDERED",
                validator_code="DIRECTOR_RENDER_STRUCTURED_OUTPUT_INVALID",
            )
            return self._raise_interrupt("orchestrator_output_invalid")
        accepted_spent_terms = tuple(
            term for term in spent_imagery_terms if term not in set(continuity_anchors)
        )
        narration = _compile_director_beat(
            rendered.narration,
            plan,
            continuity_anchors[0],
            magic_adjudication=self._game_state.pending_magic_adjudication,
        )
        decision = OrchestratorEnvelope(
            narration=narration,
            next_actor=plan.next_actor,
            complete=plan.complete,
            canon_updates=plan.canon_updates,
        )
        issue = review_orchestrator_narration(
            rendered.narration,
            actor_names=[actor.name for actor in self.actors],
        )
        if issue is None:
            # The compiled beat intentionally contains validated choices such
            # as "Have Eli call...". Review its continuity and imagery without
            # treating those plan fields as fresh actor-authored actions.
            issue = review_orchestrator_narration(
                decision.narration,
                actor_names=(),
                continuity_anchors=continuity_anchors,
                spent_imagery=accepted_spent_terms,
            ) or self._review_director_render(decision.narration, plan, max_words=160)
        if issue is not None and issue.code == "SPENT_IMAGERY_REUSED":
            # The renderer's job is optional scene texture.  The plan has
            # already passed its own anti-repetition review, so do not let a
            # decorative echo erase a playable decision.  Preserve the raw
            # renderer output in its model-call audit and record this drop.
            narration = _compile_director_beat(
                "",
                plan,
                continuity_anchors[0],
                magic_adjudication=self._game_state.pending_magic_adjudication,
            )
            decision = decision.model_copy(update={"narration": narration})
            issue = review_orchestrator_narration(
                decision.narration,
                actor_names=(),
                continuity_anchors=continuity_anchors,
                spent_imagery=accepted_spent_terms,
            ) or self._review_director_render(decision.narration, plan, max_words=160)
            if issue is None:
                self.events.append(
                    event_id=f"{self.run_id}:director-render-flavor-dropped:{round_number}",
                    natural_key=f"{self.run_id}:director-render-flavor-dropped:{round_number}",
                    aggregate_type="run",
                    aggregate_id=self.run_id,
                    event_type="DirectorRenderFlavorDropped",
                    payload={
                        "round_number": round_number,
                        "call_id": call_id,
                        "code": "SPENT_IMAGERY_REUSED",
                    },
                )
        if issue is None and _normalized_story_text(decision.narration) in self._accepted_stage_narrations:
            issue = SafetyIssue("EXACT_REPEAT", "director narration repeats accepted shared text")
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
            attempt = self.orchestrator.calls.next_attempt(run_id=self.run_id, purpose=purpose)
            call_id = f"{self.run_id}:orchestrator:r{round_number}:a{attempt}"
            corrected = await self.orchestrator.execute(
                call_id=call_id, run_id=self.run_id, purpose=purpose, attempt=attempt,
                messages=[
                    *build_director_render_messages(
                        plan=plan.model_dump(mode="json"),
                        continuity_anchors=continuity_anchors,
                        spent_director_terms=spent_imagery_terms,
                    ),
                    {"role": "system", "content": (
                        "Repair one rejected director narration. Return only the narration envelope. "
                        "The supplied plan is fixed: do not alter its decisions, costs, clocks, "
                        "canon, next actor, or completion state. Write a fresh short environmental "
                        "lead-in using only objects, systems, light, sound, or temperature as subjects. "
                        "Do not name cast members or describe their actions, sensations, thoughts, "
                        "dialogue, reactions, or choices. Do not add a new event or crisis. "
                        "The application will append the unchanged plan.\n"
                        f"REJECTION: {issue.code}: {issue.detail}\n"
                        f"CAST NAMES: {', '.join(actor.name for actor in self.actors)}\n"
                        f"REJECTED NARRATION: {rendered.narration}"
                    )},
                ],
                schema_name="director_render",
                tagged_format_instructions="<NARRATION>...</NARRATION>",
                character_id=_STAGE_CHARACTER_ID,
                prompt_version_id="scene-director-render-correction-v1",
                context_version_id=f"scene:{self.run_id}:round:{round_number}:render-correction:v1",
                role_sheet_version_id=f"hidden-plan:v{self.private_plan.version}",
                correction_of_call_id=rejected_call_id,
            )
            if corrected.status is not NormalizedCallStatus.COMPLETED:
                return self._raise_interrupt(
                    f"director_render_correction_call_{corrected.status.value.lower()}",
                    error_type=corrected.error_type,
                )
            try:
                corrected_render = parse_director_render_output(corrected.text)
            except StructuredOutputError:
                self.orchestrator.calls.record_diagnostics(
                    call_id=call_id, parse_status="REJECTED", validation_status="NOT_REACHED",
                    acceptance_status="REJECTED", render_status="NOT_RENDERED",
                    validator_code="DIRECTOR_RENDER_CORRECTION_STRUCTURED_OUTPUT_INVALID",
                )
                return self._raise_interrupt("director_render_correction_output_invalid")
            decision = decision.model_copy(
                update={
                    "narration": _compile_director_beat(
                        corrected_render.narration,
                        plan,
                        continuity_anchors[0],
                        magic_adjudication=self._game_state.pending_magic_adjudication,
                    )
                }
            )
            issue = review_orchestrator_narration(
                corrected_render.narration,
                actor_names=[actor.name for actor in self.actors],
            )
            if issue is None:
                issue = review_orchestrator_narration(
                    decision.narration,
                    actor_names=(),
                    continuity_anchors=continuity_anchors,
                    spent_imagery=accepted_spent_terms,
                ) or self._review_director_render(decision.narration, plan, max_words=160)
            if issue is None and _normalized_story_text(decision.narration) in self._accepted_stage_narrations:
                issue = SafetyIssue("EXACT_REPEAT", "director narration repeats accepted shared text")
            if issue is not None:
                self.orchestrator.calls.record_diagnostics(
                    call_id=call_id, parse_status="PARSED", validation_status="REJECTED",
                    acceptance_status="REJECTED", render_status="NOT_RENDERED",
                    validator_code=issue.code, validator_detail=issue.detail,
                )
                return self._raise_interrupt("orchestrator_director_contract_invalid")
        self.orchestrator.calls.record_diagnostics(
            call_id=call_id,
            parse_status="PARSED",
            validation_status="VALID",
            acceptance_status="PENDING",
            render_status="PENDING",
        )
        self._pending_director_plans[round_number] = plan
        return decision, attempt, call_id

    def _review_director_plan(
        self, plan: DirectorPlanEnvelope, round_number: int
    ) -> SafetyIssue | None:
        cast_identifiers = {
            value.casefold()
            for actor in self.actors
            for value in (actor.name, actor.character_id)
        }
        if plan.next_actor.casefold() not in cast_identifiers:
            return SafetyIssue(
                "NEXT_ACTOR_INVALID",
                "next_actor must name exactly one cast member or character id",
            )
        if self._game_state.scene_objective and (
            _normalized_objective(plan.scene_objective)
            != _normalized_objective(self._game_state.scene_objective)
        ):
            return SafetyIssue("SCENE_OBJECTIVE_DRIFT", "director changed the active scene objective")
        if round_number == 1 and plan.complete:
            return SafetyIssue("PREMATURE_COMPLETION", "opening round may not complete the scene")
        if round_number == self.max_rounds and plan.complete:
            return SafetyIssue(
                "FINAL_ROUND_PREEMPTS_ACTORS",
                "the final director beat must leave resolution to the fourth actor round",
            )
        magic_setup_issue = self._review_required_magic_setup(
            next_actor=plan.next_actor,
            challenge=plan.magic_challenge,
            success_criteria=plan.magic_success_criteria,
            modifier=plan.magic_modifier,
            round_number=round_number,
        )
        if magic_setup_issue is not None:
            return magic_setup_issue
        if round_number == 1 and self.required_magic_opening_plan is not None:
            expected_opening = self.required_magic_opening_plan.model_dump(mode="json")
            if plan.model_dump(mode="json") != expected_opening:
                return SafetyIssue(
                    "MAGIC_REHEARSAL_OPENING_LOCKED",
                    "round one must match the exact locked, unresolved opening plan; "
                    "do not attribute a diagnosis or resolve the challenge before the roll",
                )
        outcome_issue = self._review_magic_outcome_consequence(plan)
        if outcome_issue is not None:
            return outcome_issue
        clocks = [change.clock for change in plan.clock_changes]
        if len(clocks) != len(set(clocks)):
            return SafetyIssue("CLOCK_CHANGE_AMBIGUOUS", "a clock may change at most once per beat")
        visible_fields = (
            plan.state_change,
            plan.pressure,
            plan.choice_a,
            plan.choice_b,
            *plan.canon_updates,
            *((plan.magic_effect_detail,) if plan.magic_effect_detail is not None else ()),
        )
        visible_text = " ".join(visible_fields).casefold()
        stakes_issue = review_director_stakes(
            visible_text, actor_names=[actor.name for actor in self.actors]
        )
        if stakes_issue is not None:
            return stakes_issue
        review_text = " ".join((plan.scene_objective, plan.adjudication, *visible_fields)).casefold()
        if round_number == 1 and self.required_story_terms and not any(
            re.search(rf"\b{re.escape(term.casefold())}\b", review_text)
            for term in self.required_story_terms
        ):
            return SafetyIssue(
                "EPISODE_SPINE_REQUIRED_BEAT_MISSING",
                "opening beat does not establish the required episode-spine story element",
            )
        used_forbidden = [
            term for term in self.forbidden_story_terms
            if re.search(rf"\b{re.escape(term.casefold())}\b", review_text)
        ]
        if used_forbidden:
            return SafetyIssue(
                "EPISODE_SPINE_FALLBACK_REUSED",
                "director returned to forbidden prior-act mechanisms: " + ", ".join(used_forbidden),
            )
        if any(len(field.split()) > 24 for field in visible_fields):
            return SafetyIssue("DIRECTOR_PLAN_TOO_VERBOSE", "a visible game-state field exceeds 24 words")
        if sum(len(field.split()) for field in visible_fields[:4]) > 64:
            return SafetyIssue("DIRECTOR_PLAN_TOO_VERBOSE", "the visible decision bundle exceeds 64 words")
        spent = self._active_plan_spent_imagery()
        reused = [
            term
            for term in spent
            if any(re.search(rf"\b{re.escape(term)}\b", field, flags=re.IGNORECASE) for field in visible_fields)
        ]
        if len(reused) > 2:
            return SafetyIssue(
                "PLAN_SPENT_IMAGERY_REUSED",
                "director plan reuses too many prior-imagery terms: " + ", ".join(reused),
            )
        return None

    def _review_required_magic_setup(
        self,
        *,
        next_actor: str | None,
        challenge: str | None,
        success_criteria: str | None,
        modifier: int,
        round_number: int,
    ) -> SafetyIssue | None:
        if challenge is None and success_criteria is not None:
            return SafetyIssue(
                "MAGIC_SUCCESS_CRITERIA_UNEXPECTED",
                "success criteria may be supplied only with a declared MAGIC challenge",
            )
        if challenge is not None and not (success_criteria or "").strip():
            return SafetyIssue(
                "MAGIC_SUCCESS_CRITERIA_REQUIRED",
                "every MAGIC challenge must define the concise, observable result that counts as success",
            )
        if round_number != 1:
            return None
        configured = any(
            value is not None
            for value in (
                self.required_magic_next_actor,
                self.required_magic_challenge_text,
                self.required_magic_modifier,
            )
        )
        if not configured:
            if self.require_magic_challenge and challenge is None:
                return SafetyIssue(
                    "MAGIC_CHALLENGE_REQUIRED",
                    "this rehearsal requires one meaningful MAGIC challenge in round one",
                )
            return None

        problems: list[str] = []
        if self.require_magic_challenge and challenge is None:
            problems.append("include one meaningful MAGIC challenge")
        if self.required_magic_next_actor is not None:
            expected = self.required_magic_next_actor.casefold()
            actor = next(
                (
                    candidate
                    for candidate in self.actors
                    if expected
                    in {candidate.name.casefold(), candidate.character_id.casefold()}
                ),
                None,
            )
            aliases = (
                {actor.name.casefold(), actor.character_id.casefold()}
                if actor is not None
                else {expected}
            )
            if next_actor is None or next_actor.casefold() not in aliases:
                problems.append(f"set next_actor to {self.required_magic_next_actor}")
        if (
            self.required_magic_challenge_text is not None
            and challenge != self.required_magic_challenge_text
        ):
            problems.append(
                f"use the exact MAGIC challenge {self.required_magic_challenge_text!r}"
            )
        if (
            self.required_magic_modifier is not None
            and modifier != self.required_magic_modifier
        ):
            problems.append(
                f"set MAGIC_MODIFIER to {self.required_magic_modifier}"
            )
        if problems:
            return SafetyIssue(
                "MAGIC_CHALLENGE_SETUP_REQUIRED",
                "; ".join(problems),
            )
        return None

    def _magic_rehearsal_setup_directive(self, round_number: int) -> str | None:
        if round_number != 1 or not (
            self.require_magic_challenge
            or self.required_magic_next_actor is not None
            or self.required_magic_challenge_text is not None
            or self.required_magic_modifier is not None
            or self.required_magic_opening_plan is not None
        ):
            return None
        requirements = [
            "Mandatory dice-rehearsal condition: include exactly one meaningful, safe-distance MAGIC challenge "
            "and state the concise observable MAGIC_SUCCESS_CRITERIA before the actor acts."
        ]
        if self.required_magic_next_actor is not None:
            requirements.append(f"Set next_actor to {self.required_magic_next_actor}.")
        if self.required_magic_challenge_text is not None:
            requirements.append(
                f"Use this exact MAGIC_CHALLENGE text: {self.required_magic_challenge_text!r}."
            )
        if self.required_magic_modifier is not None:
            requirements.append(
                f"Set MAGIC_MODIFIER to {self.required_magic_modifier}."
            )
        requirements.append(
            "The character chooses their own approach; do not make them approach or touch the cheetah."
        )
        if self.required_magic_opening_plan is not None:
            requirements.append(
                "This opening plan is locked: copy every field exactly. It deliberately leaves "
                "the challenge unresolved; do not add an injury diagnosis or otherwise reveal "
                "the answer before the roll. Locked plan: "
                f"{self.required_magic_opening_plan.model_dump_json()}"
            )
        return " ".join(requirements)

    def _magic_result_contract_directive(self) -> str | None:
        adjudication = self._game_state.pending_magic_adjudication
        if adjudication is None:
            return None
        outcome = adjudication.outcome.value
        requirements = [
            "The runtime has already resolved the pending MAGIC roll. The recorded outcome is "
            f"{outcome}; do not output, infer, acknowledge, or override a result, goal status, or "
            "goal answer. The runtime will derive and compile those fields from the roll and the "
            "precommitted success criteria. Supply only a short observable magic_effect_detail "
            "that makes the runtime result playable, plus magic_cost_type only when required."
        ]
        if outcome == "clean_success":
            requirements.append(
                "For clean_success, leave magic_cost_type empty and describe one concrete visible "
                "consequence of the achieved criterion. The runtime compiles the exact detail into "
                "the visible beat; keep pressure, choices, and canon compatible with it without "
                "copying the sentence."
            )
        elif outcome == "costly_success":
            requirements.append(
                "For costly_success, choose exactly one cost type from time, position, trust, access, "
                "or resources; describe the concrete observable cost in magic_effect_detail. The "
                "runtime compiles the exact detail into the visible beat; keep pressure, choices, "
                "and canon compatible with it without copying the sentence."
            )
        else:
            requirements.append(
                "For setback, leave magic_cost_type empty and describe one relevant new clue, "
                "complication, or opening in magic_effect_detail. The runtime compiles the exact "
                "detail into the visible beat; keep pressure, choices, and canon compatible with it "
                "without copying the sentence."
            )
        if self.forbidden_magic_result_terms:
            requirements.append(
                "Do not use these unsupported result terms in any director-supplied field: "
                + ", ".join(self.forbidden_magic_result_terms)
                + "."
            )
        return " ".join(requirements)

    def _magic_result_correction_directive(
        self, forbidden_magic_terms: tuple[str, ...] = ()
    ) -> str:
        """Repair only director-supplied consequence fields after runtime adjudication."""

        adjudication = self._game_state.pending_magic_adjudication
        if adjudication is None:
            return ""
        outcome = adjudication.outcome.value
        requirements = [
            "POST-ROLL MAGIC CONSEQUENCE CORRECTION: the runtime owns the recorded MAGIC outcome, "
            "goal status, and goal answer. Do not output those fields and do not change the roll. "
            "Preserve unrelated safe facts and choices; repair only the short consequence input. "
            f"The runtime outcome is {outcome}."
        ]
        if outcome == "clean_success":
            requirements.append(
                "Set magic_cost_type to none. Provide one concrete observable magic_effect_detail "
                "for the achieved criterion. The runtime compiles the exact detail into the visible "
                "beat; keep pressure, choices, and canon compatible with it without copying the sentence."
            )
        elif outcome == "costly_success":
            requirements.append(
                "Set one allowed magic_cost_type (time, position, trust, access, or resources). "
                "Provide one concrete observable magic_effect_detail cost. The runtime compiles the "
                "exact detail into the visible beat; keep pressure, choices, and canon compatible "
                "with it without copying the sentence."
            )
        else:
            requirements.append(
                "Set magic_cost_type to none. Provide one relevant new clue, complication, or opening "
                "in magic_effect_detail. The runtime compiles the exact detail into the visible beat; "
                "keep pressure, choices, and canon compatible with it without copying the sentence."
            )
        requirements.append(
            "Do not quote or reuse any forbidden unsupported-result term named in the rejection, "
            "including grammatical variants or close medical synonyms; if uncertain, describe only "
            "observable behavior and leave interpretation unresolved. Return the complete "
            "corrected structured plan with no result acknowledgement or goal-answer prose. Keep "
            "pressure to 12 words or fewer and choice_a and choice_b to 10 words or fewer."
        )
        if forbidden_magic_terms:
            requirements.append(
                "These exact terms appeared in the rejected plan and must not appear in the corrected "
                "plan: "
                + ", ".join(forbidden_magic_terms)
                + "."
            )
        return " ".join(requirements)

    def _review_magic_outcome_consequence(
        self, plan: DirectorPlanEnvelope
    ) -> SafetyIssue | None:
        adjudication = self._game_state.pending_magic_adjudication
        cost_type = plan.magic_cost_type.value if plan.magic_cost_type is not None else None
        detail = (plan.magic_effect_detail or "").strip()
        if adjudication is None:
            if plan.magic_cost_type is not None or plan.magic_effect_detail is not None:
                return SafetyIssue(
                    "MAGIC_OUTCOME_CONSEQUENCE_UNEXPECTED",
                    "MAGIC consequence fields are allowed only when resolving a recorded MAGIC roll",
                )
            return None

        problems: list[str] = []
        outcome = adjudication.outcome
        if len(detail) < 8:
            problems.append(
                f"{outcome.value} requires a short observable magic_effect_detail consequence"
            )

        if outcome is MagicOutcome.CLEAN_SUCCESS:
            if cost_type is not None:
                problems.append("clean_success must not add a MAGIC cost")
        elif outcome is MagicOutcome.COSTLY_SUCCESS:
            if plan.magic_cost_type not in set(MagicCostType):
                problems.append(
                    "costly_success requires one allowed tangible magic_cost_type"
                )
        elif outcome is MagicOutcome.SETBACK:
            if cost_type is not None:
                problems.append("setback must not add a MAGIC cost")
        else:
            return SafetyIssue(
                "MAGIC_OUTCOME_CONSEQUENCE_INVALID",
                "recorded MAGIC result has an unsupported outcome",
            )

        unsupported = self._forbidden_magic_result_terms_in_plan(plan)
        if unsupported:
            problems.append("unsupported result claims appear in the director plan: " + ", ".join(unsupported))

        if problems:
            code = "MAGIC_RESULT_CLAIM_UNSUPPORTED" if unsupported else "MAGIC_OUTCOME_CONSEQUENCE_REQUIRED"
            return SafetyIssue(code, "; ".join(problems))
        return None

    def _forbidden_magic_result_terms_in_plan(
        self, plan: DirectorPlanEnvelope
    ) -> tuple[str, ...]:
        all_plan_text = " ".join(
            (
                plan.scene_objective,
                plan.adjudication,
                plan.state_change,
                plan.pressure,
                plan.choice_a,
                plan.choice_b,
                *plan.canon_updates,
                plan.magic_effect_detail or "",
            )
        ).casefold()
        return tuple(
            term
            for term in self.forbidden_magic_result_terms
            if _magic_term_present(all_plan_text, term)
        )

    def _active_plan_spent_imagery(self) -> tuple[str, ...]:
        """Keep current state vocabulary available while blocking stale texture.

        The repetition guard is meant to prevent decorative replay, not to make
        the director avoid the active problem. Terms in the current state,
        pressure, or required episode-spine vocabulary remain live facts that a
        later plan may need to adjudicate.
        """

        spent = spent_director_imagery(self._scene_lines())
        active_text = " ".join(
            value
            for value in (
                self._game_state.last_state_change,
                self._game_state.last_pressure,
                self._game_state.pending_magic_success_criteria,
                *self.required_story_terms,
            )
            if value
        )
        return tuple(
            term
            for term in spent
            if not re.search(rf"\b{re.escape(term)}\b", active_text, flags=re.IGNORECASE)
        )

    def _review_director_plan_correction_scope(
        self,
        original: DirectorPlanEnvelope,
        corrected: DirectorPlanEnvelope,
        *,
        rejection_code: str,
    ) -> SafetyIssue | None:
        """Keep a forbidden-mechanism repair surgical and provenance-auditable."""

        if rejection_code != "EPISODE_SPINE_FALLBACK_REUSED":
            return None
        forbidden = tuple(term.casefold() for term in self.forbidden_story_terms)
        original_fields = {
            "scene_objective": original.scene_objective,
            "adjudication": original.adjudication,
            "state_change": original.state_change,
            "pressure": original.pressure,
            "choice_a": original.choice_a,
            "choice_b": original.choice_b,
        }
        corrected_fields = {
            "scene_objective": corrected.scene_objective,
            "adjudication": corrected.adjudication,
            "state_change": corrected.state_change,
            "pressure": corrected.pressure,
            "choice_a": corrected.choice_a,
            "choice_b": corrected.choice_b,
        }
        affected_fields = {
            name
            for name, value in original_fields.items()
            if any(re.search(rf"\b{re.escape(term)}\b", value, flags=re.IGNORECASE) for term in forbidden)
        }
        if original.next_actor != corrected.next_actor or original.complete != corrected.complete:
            return SafetyIssue(
                "DIRECTOR_PLAN_CORRECTION_SCOPE_DRIFT",
                "correction changed next_actor or completion state",
            )
        if original.clock_changes != corrected.clock_changes:
            return SafetyIssue(
                "DIRECTOR_PLAN_CORRECTION_SCOPE_DRIFT",
                "correction changed clock consequences",
            )
        changed_unaffected = [
            name
            for name, value in original_fields.items()
            if name not in affected_fields and corrected_fields[name] != value
        ]
        original_canon = list(original.canon_updates)
        corrected_canon = list(corrected.canon_updates)
        canon_is_affected = any(
            re.search(rf"\b{re.escape(term)}\b", update, flags=re.IGNORECASE)
            for update in original_canon
            for term in forbidden
        )
        if not canon_is_affected and original_canon != corrected_canon:
            changed_unaffected.append("canon_updates")
        if changed_unaffected:
            return SafetyIssue(
                "DIRECTOR_PLAN_CORRECTION_SCOPE_DRIFT",
                "correction changed unaffected fields: " + ", ".join(changed_unaffected),
            )
        if not affected_fields and not canon_is_affected:
            return SafetyIssue(
                "DIRECTOR_PLAN_CORRECTION_SCOPE_DRIFT",
                "correction source has no identifiable forbidden mechanism",
            )
        return None

    def _repair_director_plan_correction_scope(
        self,
        original: DirectorPlanEnvelope,
        corrected: DirectorPlanEnvelope,
        *,
        rejection_code: str,
    ) -> tuple[DirectorPlanEnvelope | None, tuple[str, ...]]:
        """Restore safe fields when a bounded model correction paraphrases them.

        The scope guard remains fail-closed for changed actors, completion state,
        clocks, or an unidentifiable forbidden mechanism. For the narrow case in
        which the model changes only otherwise-safe fields, the application can
        restore those fields from the rejected plan without inventing content.
        The derived plan is recorded separately from the raw model output.
        """

        if rejection_code != "EPISODE_SPINE_FALLBACK_REUSED":
            return None, ()
        if original.next_actor != corrected.next_actor or original.complete != corrected.complete:
            return None, ()
        if original.clock_changes != corrected.clock_changes:
            return None, ()

        forbidden = tuple(term.casefold() for term in self.forbidden_story_terms)
        field_names = (
            "scene_objective",
            "adjudication",
            "state_change",
            "pressure",
            "choice_a",
            "choice_b",
        )
        original_fields = {name: getattr(original, name) for name in field_names}
        corrected_fields = {name: getattr(corrected, name) for name in field_names}
        affected_fields = {
            name
            for name, value in original_fields.items()
            if any(re.search(rf"\b{re.escape(term)}\b", value, flags=re.IGNORECASE) for term in forbidden)
        }
        original_canon = list(original.canon_updates)
        corrected_canon = list(corrected.canon_updates)
        affected_canon = {
            index
            for index, value in enumerate(original_canon)
            if any(re.search(rf"\b{re.escape(term)}\b", value, flags=re.IGNORECASE) for term in forbidden)
        }
        if not affected_fields and not affected_canon:
            return None, ()

        updates: dict[str, object] = {}
        restored: list[str] = []
        for name in field_names:
            if name not in affected_fields and corrected_fields[name] != original_fields[name]:
                updates[name] = original_fields[name]
                restored.append(name)

        if affected_canon:
            if len(original_canon) != len(corrected_canon):
                return None, ()
            constrained_canon = [
                corrected_canon[index] if index in affected_canon else original_canon[index]
                for index in range(len(original_canon))
            ]
            if constrained_canon != corrected_canon:
                updates["canon_updates"] = constrained_canon
                restored.append("canon_updates")
        elif corrected_canon != original_canon:
            updates["canon_updates"] = original_canon
            restored.append("canon_updates")

        if not restored:
            return None, ()
        return corrected.model_copy(update=updates), tuple(restored)

    def _active_director_lore(self) -> tuple[str, ...]:
        active = list(
            WorldBookEngine().activate(
                self.world_books,
                text="\n".join(self._scene_lines()),
                recipient="__orchestrator__",
                is_director=True,
            )
        )
        seen = {entry.entry_id for entry in active}
        required = set(self.required_lore_entry_ids)
        for book in self.world_books:
            for entry in book.entries:
                if entry.entry_id in required and entry.entry_id not in seen and entry.enabled:
                    active.append(ActiveLoreEntry(entry.entry_id, entry.name, entry.content, entry.position))
                    seen.add(entry.entry_id)
        return tuple(entry.content for entry in active)

    @staticmethod
    def _review_director_render(
        narration: str,
        plan: DirectorPlanEnvelope,
        *,
        max_words: int = 120,
    ) -> SafetyIssue | None:
        normalized = narration.casefold()
        required = (
            ("PLAN_STATE_CHANGE_MISSING", plan.state_change),
            ("PLAN_PRESSURE_MISSING", plan.pressure),
            ("CHOICE_A_MISSING", f"Choice A: {plan.choice_a}"),
            ("CHOICE_B_MISSING", f"Choice B: {plan.choice_b}"),
        )
        for code, phrase in required:
            if phrase.casefold() not in normalized:
                return SafetyIssue(code, "rendered beat omitted an approved plan field")
        if len(narration.split()) > max_words:
            return SafetyIssue(
                "DIRECTOR_RENDER_TOO_VERBOSE",
                f"rendered director beat exceeds {max_words} words",
            )
        return None

    def actor_messages(self, actor: SceneActor, round_number: int) -> list[dict[str, str]]:
        """Exact ordinary actor context, also used for immutable research snapshots."""
        messages = build_actor_messages(
            ActorContext(
                actor_name=(actor.actor_sheet.name if actor.actor_sheet else actor.name),
                actor_sheet=actor.actor_sheet,
                character_name=actor.name,
                role_sheet=actor.role_sheet,
                known_memory=tuple(self._actor_memory[actor.character_id]),
                accepted_canon=tuple(self._accepted_canon),
                scene_transcript=self._scene_lines(),
                mission_clock=self._mission_clock(),
                previous_shared_outcome=self.previous_shared_outcome,
                round_number=round_number,
                character_card=actor.character_card,
                active_lore=tuple(
                    entry.content
                    for entry in WorldBookEngine().activate(
                        self.world_books,
                        text="\n".join(self._scene_lines()),
                        recipient=actor.character_id,
                    )
                ),
                prompt_profile=actor.prompt_profile,
            )
        )
        messages.append(
            {
                "role": "system",
                "content": (
                    "Return one complete actor response. Text must be exactly one shared "
                    "in-character turn under 120 words, with no response-envelope markup, "
                    "private asides, or another actor's line. Include at most two short memory "
                    "notes. Diary intent is a boolean; wellness is only an explicit out-of-world "
                    "signal. Treat every accepted actor line in CURRENT SCENE as a resolved move. "
                    "Do not repeat or paraphrase an earlier action, reuse its same procedure on "
                    "the same target, or turn an earlier decision back into a suggestion. Advance "
                    "the newest director choice with one unused decision that fits your character. "
                    "If and only if the current director beat gives you a pending MAGIC challenge, "
                    "you may include <MAGIC_STAT>Might|Authority|Gusto|Intellect|Cool</MAGIC_STAT> "
                    "to attempt it; your ACTOR_TEXT is the action being tested. Describe the attempt, "
                    "not whether it succeeded, a diagnosis, or the final answer; the app resolves "
                    "that. Omit MAGIC_STAT to decline. Never invent or narrate the dice or their result."
                ),
            }
        )
        return messages

    async def _call_actor(
        self,
        actor: SceneActor,
        round_number: int,
        *,
        correction_reason: str | None = None,
        correction_rejected_text: str | None = None,
    ) -> tuple[ActorTurnEnvelope, int, str]:
        purpose = (
            f"actor_correction:{actor.character_id}:round:{round_number}"
            if correction_reason
            else f"actor_turn:{actor.character_id}:round:{round_number}"
        )
        attempt = actor.executor.calls.next_attempt(run_id=self.run_id, purpose=purpose)
        call_kind = "correction" if correction_reason else "turn"
        call_id = (
            f"{self.run_id}:actor:{call_kind}:{actor.character_id}:"
            f"r{round_number}:a{attempt}"
        )
        messages = self.actor_messages(actor, round_number)
        if correction_reason:
            forbidden_magic_terms = self._forbidden_magic_attempt_terms_in_text(
                correction_rejected_text or ""
            )
            correction_instruction = (
                "Your previous attempt was rejected because it stated a result or diagnosis "
                "before the pending MAGIC roll. Keep the same character choice, expertise, "
                "observable method, and MAGIC_STAT, but rewrite the move as an attempt only. "
                "Do not state, imply, or name the diagnosis, success, failure, or final answer; "
                "do not repeat any matched term, inflection, or close medical synonym. Use only "
                "observation-only language about movement, position, timing, distance, or sound; "
                "the app's roll determines that. Do not add another character's action or reaction. "
                "Return one complete actor response without explaining the correction."
                if correction_reason.startswith("MAGIC_ATTEMPT_PREMATURE_RESULT:")
                else (
                    "Your previous attempt was rejected only for this issue: "
                    f"{correction_reason}. Correct it surgically. Preserve the same choice, "
                    "intention, action, dialogue, setting facts, and every safe detail. Change "
                    "only the wording or action directly necessary to remove the flagged issue. "
                    "Do not invent a replacement plan, new consequence, new information, or "
                    "actions, dialogue, decisions, or reactions for another character. Do not "
                    "change the outcome and do not explain the correction."
                )
            )
            if correction_reason.startswith("MAGIC_ATTEMPT_PREMATURE_RESULT:"):
                correction_instruction += (
                    " If you answer with JSON, put MAGIC_STAT in the magic_stat field and "
                    "memory notes in the memory_notes list; never put <MAGIC_STAT> or "
                    "[Memory: ...] inside text."
                )
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"{correction_instruction}\n"
                        f"REJECTED TURN: {correction_rejected_text or '(unavailable)'}"
                    ),
                }
            )
            if correction_reason.startswith("MAGIC_ATTEMPT_PREMATURE_RESULT:") and forbidden_magic_terms:
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "FORBIDDEN MAGIC ATTEMPT TERMS FOUND IN REJECTED TURN: "
                            + ", ".join(forbidden_magic_terms)
                            + ". These terms are instructions, not content: none may appear in "
                            "the corrected ACTOR_TEXT."
                        ),
                    }
                )
        result = await actor.executor.execute(
            call_id=call_id,
            run_id=self.run_id,
            purpose=purpose,
            attempt=attempt,
            messages=messages,
            schema_name="actor_turn",
            tagged_format_instructions=(
                "<ACTOR_TEXT>one in-character turn</ACTOR_TEXT>\n"
                "<WELLNESS_SIGNAL>optional out-of-world signal</WELLNESS_SIGNAL>\n"
                "<MEMORY_NOTE>optional private memory note</MEMORY_NOTE>\n"
                "<DIARY_INTENT>false</DIARY_INTENT>\n"
                "<MAGIC_STAT>optional: Might|Authority|Gusto|Intellect|Cool</MAGIC_STAT>"
            ),
            character_id=actor.character_id,
            prompt_version_id="scene-actor-v6-magic-attempt",
            context_version_id=f"scene:{self.run_id}:round:{round_number}:v4",
            role_sheet_version_id=f"{actor.character_id}:v{actor.role_sheet.version}",
            correction_of_call_id=(
                f"{self.run_id}:actor:turn:{actor.character_id}:r{round_number}:a1"
                if correction_reason else None
            ),
        )
        if result.status is not NormalizedCallStatus.COMPLETED:
            return self._raise_interrupt(
                f"actor_call_{actor.character_id}_{result.status.value.lower()}",
                error_type=result.error_type,
            )
        try:
            envelope = parse_actor_output(result.text)
        except StructuredOutputError:
            actor.executor.calls.record_diagnostics(
                call_id=call_id,
                parse_status="REJECTED",
                validation_status="NOT_REACHED",
                acceptance_status="REJECTED",
                render_status="NOT_RENDERED",
                validator_code="STRUCTURED_OUTPUT_INVALID",
            )
            return self._raise_interrupt(f"actor_output_invalid:{actor.character_id}")
        actor.executor.calls.record_diagnostics(
            call_id=call_id,
            parse_status="PARSED",
            validation_status="VALID",
            acceptance_status="PENDING",
            render_status="PENDING",
        )
        return envelope, attempt, call_id

    def _persist_orchestrator_decision(
        self, round_number: int, decision: OrchestratorEnvelope, attempt: int, call_id: str
    ) -> None:
        plan = self._pending_director_plans.pop(round_number, None)
        magic_adjudication = self._game_state.pending_magic_adjudication
        if magic_adjudication is not None and plan is None:
            self._raise_interrupt("magic_outcome_requires_structured_plan")
        visible_narration = decision.narration
        magic_challenge = plan.magic_challenge if plan is not None else decision.magic_challenge
        magic_success_criteria = (
            plan.magic_success_criteria if plan is not None else decision.magic_success_criteria
        )
        magic_modifier = plan.magic_modifier if plan is not None else decision.magic_modifier
        if magic_challenge:
            challenged_actor = next(
                (
                    actor
                    for actor in self.actors
                    if decision.next_actor.casefold()
                    in {actor.name.casefold(), actor.character_id.casefold()}
                ),
                None,
            )
            challenged_name = challenged_actor.name if challenged_actor else decision.next_actor
            visible_narration += (
                f"\nMAGIC CHALLENGE — {challenged_name}: {magic_challenge} "
                f"Success criteria: {magic_success_criteria}. "
                "Choose a relevant MAGIC attribute to attempt it, or omit MAGIC_STAT to decline."
            )
        artifact = self.orchestrator.audit.write_text(
            Path("runs")
            / self.run_id
            / "scene"
            / f"round-{round_number}-attempt-{attempt}.md",
            visible_narration,
        )
        accepted_sequence = self.records.insert_turn(
            turn_id=f"{self.run_id}:stage:{round_number}",
            run_id=self.run_id,
            round_number=round_number,
            character_id=_STAGE_CHARACTER_ID,
            disposition="NARRATION_ACCEPT",
            content_path=str(artifact.path),
            accepted_at=self.orchestrator.clock.now().isoformat(),
        )
        self.events.append(
            event_id=f"{self.run_id}:orchestrator:{round_number}",
            natural_key=f"{self.run_id}:orchestrator:{round_number}",
            aggregate_type="run",
            aggregate_id=self.run_id,
            event_type="OrchestratorRoundAccepted",
            payload={
                "round_number": round_number,
                "next_actor": decision.next_actor,
                "complete": decision.complete,
                "canon_updates": decision.canon_updates,
                "magic_state": (
                    None
                    if plan is not None
                    else {
                        "magic_challenge": magic_challenge,
                        "magic_success_criteria": magic_success_criteria,
                        "magic_modifier": magic_modifier,
                        "next_actor": decision.next_actor,
                    }
                ),
                "content_path": str(artifact.path),
                "accepted_sequence": accepted_sequence,
            },
        )
        if plan is not None:
            self._game_state.apply(plan, magic_adjudication=magic_adjudication)
            self.events.append(
                event_id=f"{self.run_id}:director-plan:{round_number}",
                natural_key=f"{self.run_id}:director-plan:{round_number}",
                aggregate_type="run",
                aggregate_id=self.run_id,
                event_type="DirectorPlanAccepted",
                payload={
                    "round_number": round_number,
                    "plan": plan.model_dump(mode="json"),
                    "magic_adjudication": (
                        magic_adjudication.model_dump(mode="json")
                        if magic_adjudication is not None
                        else None
                    ),
                    "game_state_after": self._game_state.as_payload(),
                },
            )
        else:
            self._game_state.apply_magic_fields(
                magic_challenge=magic_challenge,
                magic_success_criteria=magic_success_criteria,
                next_actor=decision.next_actor,
                magic_modifier=magic_modifier,
            )
        self._stage_rounds.add(round_number)
        self._accepted_stage_narrations.add(_normalized_story_text(visible_narration))
        self.orchestrator.calls.record_diagnostics(
            call_id=call_id,
            parse_status="PARSED",
            validation_status="VALID",
            acceptance_status="ACCEPTED",
            render_status="RENDERED",
            accepted_path=str(artifact.path),
            rendered_path=str(artifact.path),
        )
        self._accepted_canon.extend(decision.canon_updates)
        if visible_narration:
            self.transcript.add_direction(visible_narration)

    def _persist_actor_turn(
        self,
        actor: SceneActor,
        round_number: int,
        text: str,
        envelope: ActorTurnEnvelope,
        attempt: int,
        call_id: str,
        *,
        disposition: str = "ACCEPT",
    ) -> None:
        challenge = self._game_state.challenge_for(
            character_id=actor.character_id, name=actor.name
        )
        roll_payload: dict[str, object] | None = None
        if challenge is not None and envelope.magic_stat is not None:
            score = actor.role_sheet.magic.score_for(envelope.magic_stat)
            die_faces = self._roll_dice()
            result: MagicRollResult = resolve_magic_roll(
                attribute=envelope.magic_stat,
                attribute_score=score,
                die_faces=die_faces,
                situational_modifier=self._game_state.pending_magic_modifier,
            )
            turn_id = f"{self.run_id}:r{round_number}:{actor.character_id}"
            roll_payload = magic_roll_payload(
                run_id=self.run_id,
                round_number=round_number,
                turn_id=turn_id,
                character_id=actor.character_id,
                character_name=actor.name,
                challenge=challenge,
                action=text,
                result=result,
                recorded_at=self.orchestrator.clock.now().isoformat(),
            )
            roll_payload["success_criteria"] = self._game_state.pending_magic_success_criteria
        artifact = actor.executor.audit.write_text(
            Path("runs")
            / self.run_id
            / "turns"
            / f"round-{round_number}-{actor.character_id}-attempt-{attempt}.md",
            text,
        )
        caused_by_turn_id = f"{self.run_id}:stage:{round_number}"
        turn_id = f"{self.run_id}:r{round_number}:{actor.character_id}"
        with self.records.database.transaction():
            accepted_sequence = self.records.insert_turn(
                turn_id=turn_id,
                run_id=self.run_id,
                round_number=round_number,
                character_id=actor.character_id,
                disposition=disposition,
                content_path=str(artifact.path),
                caused_by_turn_id=caused_by_turn_id,
                accepted_at=self.orchestrator.clock.now().isoformat(),
            )
            self.records.checkpoint_run(
                run_id=self.run_id,
                turn_count=len(self._accepted) + 1,
                expected_status="RUNNING",
            )
            self.events.append(
                event_id=f"{self.run_id}:turn:{round_number}:{actor.character_id}",
                natural_key=f"{self.run_id}:turn:{round_number}:{actor.character_id}",
                aggregate_type="run",
                aggregate_id=self.run_id,
                event_type="TurnAccepted",
                payload={
                    "round_number": round_number,
                    "character_id": actor.character_id,
                    "content_path": str(artifact.path),
                    "memory_notes": envelope.memory_notes,
                    "accepted_sequence": accepted_sequence,
                    "caused_by_turn_id": caused_by_turn_id,
                    "magic_challenge_answered": challenge is not None,
                },
            )
            if roll_payload is not None:
                self.events.append(
                    event_id=f"{self.run_id}:magic-roll:{round_number}:{actor.character_id}",
                    natural_key=f"{self.run_id}:magic-roll:{round_number}:{actor.character_id}",
                    aggregate_type="run",
                    aggregate_id=self.run_id,
                    event_type="MagicRollResolved",
                    payload=roll_payload,
                )
        self._accepted.add((round_number, actor.character_id))
        self._accepted_actor_texts.add(_normalized_story_text(text))
        actor.executor.calls.record_diagnostics(
            call_id=call_id,
            parse_status="PARSED",
            validation_status="VALID",
            acceptance_status="ACCEPTED",
            render_status="RENDERED",
            accepted_path=str(artifact.path),
            rendered_path=str(artifact.path),
        )
        self._resolved.add((round_number, actor.character_id))
        self._actor_memory[actor.character_id].extend(envelope.memory_notes)
        self.transcript.add_line(actor.name, text)
        if challenge is not None:
            self._game_state.answer_magic_challenge(
                character_id=actor.character_id,
                name=actor.name,
                roll=roll_payload,
            )
        if roll_payload is not None:
            self.transcript.add_direction(_magic_roll_summary(roll_payload))

    def _roll_dice(self) -> tuple[int, int]:
        if self.die_roller is not None:
            faces = self.die_roller()
        else:
            roller = secrets.SystemRandom()
            faces = (roller.randint(1, 6), roller.randint(1, 6))
        if len(faces) != 2 or any(not 1 <= face <= 6 for face in faces):
            raise ValueError("die_roller must return exactly two d6 faces")
        return int(faces[0]), int(faces[1])

    def _persist_noncanon(
        self,
        actor: SceneActor,
        round_number: int,
        text: str,
        attempt: int,
        call_id: str,
        issue: SafetyIssue,
    ) -> None:
        key = (round_number, actor.character_id)
        phase = "correction" if key in self._correction_requested else "turn"
        artifact = actor.executor.audit.write_text(
            Path("runs")
            / self.run_id
            / "turns"
            / f"round-{round_number}-{actor.character_id}-{phase}-attempt-{attempt}-not-canon.md",
            text,
        )
        self.events.append(
            event_id=f"{self.run_id}:review:{round_number}:{actor.character_id}:{phase}:{attempt}",
            natural_key=f"{self.run_id}:review:{round_number}:{actor.character_id}:{phase}:{attempt}",
            aggregate_type="run",
            aggregate_id=self.run_id,
            event_type="TurnDisposition",
            payload={
                "round_number": round_number,
                "character_id": actor.character_id,
                "attempt": attempt,
                "disposition": "NON_CANON",
                "final": bool(key in self._correction_requested),
                "code": issue.code,
                "reason": issue.detail,
                "content_path": str(artifact.path),
            },
        )
        actor.executor.calls.record_diagnostics(
            call_id=call_id,
            parse_status="PARSED",
            validation_status="REJECTED",
            acceptance_status="REJECTED",
            render_status="NOT_RENDERED",
            validator_code=issue.code,
            validator_detail=issue.detail,
        )
        self.transcript.add_audit(
            f"CONTENT REVIEW — NOT CANON ({issue.detail})\n{text}"
        )

    def _persist_neutral_interruption(
        self, actor: SceneActor, round_number: int, issue: SafetyIssue
    ) -> None:
        challenge = self._game_state.challenge_for(
            character_id=actor.character_id, name=actor.name
        )
        content = "The scene pauses, and the unanswered moment passes without forcing anyone to repeat it."
        artifact = actor.executor.audit.write_text(
            Path("runs")
            / self.run_id
            / "turns"
            / f"round-{round_number}-{actor.character_id}-neutral.md",
            content,
        )
        caused_by_turn_id = f"{self.run_id}:stage:{round_number}"
        accepted_sequence = self.records.insert_turn(
            turn_id=f"{self.run_id}:interruption:{round_number}:{actor.character_id}",
            run_id=self.run_id,
            round_number=round_number,
            character_id=f"{_NEUTRAL_CHARACTER_PREFIX}{actor.character_id}",
            disposition="NEUTRAL_INTERRUPTION",
            content_path=str(artifact.path),
            caused_by_turn_id=caused_by_turn_id,
            accepted_at=self.orchestrator.clock.now().isoformat(),
        )
        self.events.append(
            event_id=f"{self.run_id}:neutral-interruption:{round_number}:{actor.character_id}",
            natural_key=f"{self.run_id}:neutral-interruption:{round_number}:{actor.character_id}",
            aggregate_type="run",
            aggregate_id=self.run_id,
            event_type="NeutralInterruptionInserted",
            payload={
                "round_number": round_number,
                "character_id": actor.character_id,
                "reason": issue.detail,
                "content_path": str(artifact.path),
                "magic_challenge_answered": challenge is not None,
                "accepted_sequence": accepted_sequence,
                "caused_by_turn_id": caused_by_turn_id,
            },
        )
        if challenge is not None:
            self._game_state.answer_magic_challenge(
                character_id=actor.character_id,
                name=actor.name,
            )
        key = (round_number, actor.character_id)
        self._neutral_interruptions.add(key)
        self._resolved.add(key)
        self.transcript.add_direction(content)

    def _ordered_actors(
        self, *, next_actor: str | None, remaining: list[SceneActor]
    ) -> list[SceneActor]:
        if not remaining:
            return []
        needle = (next_actor or "").strip().lower()
        start = next(
            (
                index
                for index, actor in enumerate(remaining)
                if needle in {actor.name.lower(), actor.character_id.lower()}
            ),
            0,
        )
        return remaining[start:] + remaining[:start]

    def _stage_next_actor(self, round_number: int) -> str | None:
        for row in self.events.list_for_aggregate(self.run_id):
            if row["event_type"] != "OrchestratorRoundAccepted":
                continue
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, ValueError):
                continue
            if int(payload.get("round_number", 0)) == round_number:
                return payload.get("next_actor")
        return None

    def _scene_lines(self) -> tuple[str, ...]:
        return tuple(self.transcript.script_view(include_audit=False).splitlines())

    def _orchestrator_scene_lines(self) -> tuple[str, ...]:
        """Give the director actor moves and canonical state, not prose to paraphrase."""

        return tuple(
            f"{turn.speaker}: {turn.text}"
            for turn in self.transcript.turns
            if turn.kind == "line"
        )

    def _opening_direction(self) -> str:
        rules = "; ".join(self.opening.world_rules) if self.opening.world_rules else "(none stated)"
        lines = [
            f"Set: {self.opening.set}",
            f"Setting: {self.opening.setting}",
            f"Cast: {', '.join(self.opening.cast)}",
            f"World rules: {rules}",
            f"Mission clock: {self._mission_clock()}",
        ]
        if self.previous_shared_outcome:
            lines.append(f"Previous shared outcome: {self.previous_shared_outcome}")
        return "\n".join(lines)

    def _mission_clock(self) -> str:
        period = (
            {1: "morning", 2: "evening"}[self.slot_number]
            if self.sessions_per_day == 2
            else {1: "morning", 2: "afternoon", 3: "evening"}[self.slot_number]
        )
        scheduled = (
            f" Scheduled local time: {self.scheduled_local}."
            if self.scheduled_local
            else ""
        )
        if self.slot_number == 1 and self.day_number == 1:
            passage = (
                "This is the mission's opening morning. Establish a lived-in start as well as "
                "the first playable pressure."
            )
        elif self.slot_number == 1:
            passage = (
                "An overnight sleep period has passed in the fiction. Begin with the cast waking "
                "or rising into a recognizably new day; each actor may characterize how well they "
                "slept. Do not continue the previous evening as though no time passed."
            )
        elif self.slot_number < self.sessions_per_day:
            passage = (
                "Roughly six fictional hours have passed since the morning run. Meals, work, "
                "maintenance, conversation, and off-screen attempts may have happened. Carry "
                "consequences forward without replaying the earlier scene."
            )
        else:
            passage = (
                "Roughly six fictional hours have passed since the afternoon run. This is the "
                "day's final shared period before the overnight sleep interval and day closure; "
                "leave the day in a meaningfully changed state."
            )
        return (
            f"Day {self.day_number}, {period}, session {self.slot_number} of "
            f"{self.sessions_per_day}. Episode phase: {self.episode_phase}."
            f"{scheduled} Treat this run as a substantial part of the day, not the next few "
            f"seconds after the prior run. {passage}"
        )

    def _time_limit_reached(self) -> bool:
        if not self.enforce_wall_time_limit:
            return False
        return self.orchestrator.clock.now() - self._started_at >= self.max_duration

    def _complete(self, reason: str) -> SceneRunResult:
        self.records.update_run_status(
            run_id=self.run_id,
            status="COMPLETED",
            completion_reason=reason,
            expected_status="RUNNING",
        )
        return SceneRunResult(reason=reason, turns=len(self._accepted), transcript=self.transcript)

    def _interrupt(self, reason: str) -> SceneRunResult:
        self.records.update_run_status(
            run_id=self.run_id,
            status="INTERRUPTED",
            completion_reason=reason,
            expected_status="RUNNING",
        )
        return SceneRunResult(reason=reason, turns=len(self._accepted), transcript=self.transcript)

    def _raise_interrupt(self, reason: str, *, error_type: str | None = None):
        self._interrupt(reason)
        raise SceneRunError(reason, error_type=error_type)


def _normalized_objective(value: str) -> str:
    """Ignore cosmetic whitespace without erasing word boundaries or punctuation."""

    collapsed = " ".join(value.casefold().split())
    return re.sub(r"\s*([—–])\s*", r"\1", collapsed)


def _runtime_director_plan_payload(payload: object) -> dict[str, object]:
    """Load a plan while dropping legacy model-owned MAGIC adjudication fields."""

    if not isinstance(payload, dict):
        raise TypeError("director plan payload must be an object")
    normalized = dict(payload)
    for field_name in (
        "magic_result_ack",
        "magic_goal_status",
        "magic_goal_answer",
    ):
        normalized.pop(field_name, None)
    return normalized


def _director_plan_correction_instruction(
    rejection_code: str,
    *,
    forbidden_magic_terms: tuple[str, ...] = (),
) -> str:
    if rejection_code == "MAGIC_CHALLENGE_REQUIRED":
        return (
            "Add exactly one concise MAGIC_CHALLENGE for the designated next_actor and choose a "
            "matching observable MAGIC_SUCCESS_CRITERIA and a situational modifier from -2 to +2. "
            "Preserve the objective, state change, pressure, "
            "choices, clock changes, canon, and next actor; do not make the character approach or "
            "touch the cheetah."
        )
    if rejection_code == "MAGIC_SUCCESS_CRITERIA_REQUIRED":
        return (
            "For the declared MAGIC_CHALLENGE, provide concise, observable MAGIC_SUCCESS_CRITERIA "
            "before the actor's action. Define what the check can establish without resolving it early."
        )
    if rejection_code == "MAGIC_CHALLENGE_SETUP_REQUIRED":
        return (
            "Repair the listed required round-one MAGIC setup and success-criteria fields exactly as specified in the "
            "mandatory dice-rehearsal condition. Those fields are the required exception to "
            "preservation; preserve every unrelated field and do not make the character approach "
            "or touch the cheetah."
        )
    if rejection_code == "MAGIC_REHEARSAL_OPENING_LOCKED":
        return (
            "Replace the opening with the supplied locked plan exactly. It is intentionally "
            "unresolved: do not infer, diagnose, or disclose the challenge answer before the roll."
        )
    if rejection_code == "MAGIC_OUTCOME_CONSEQUENCE_REQUIRED":
        return (
            "The runtime already owns the recorded MAGIC outcome, goal status, and goal answer. "
            "Supply only a short observable magic_effect_detail. For costly_success, add one allowed "
            "magic_cost_type. For clean_success and setback, leave magic_cost_type empty. The runtime "
            "compiles the exact detail into the visible beat; keep pressure, choices, and canon "
            "compatible with it without copying the sentence. Preserve unrelated fields."
        )
    if rejection_code == "MAGIC_PLAN_OUTCOME_COHERENCE_INVALID":
        return (
            "Resolve every listed consequence issue together. The runtime owns the outcome, goal "
            "status, and goal answer. Repair only magic_cost_type and magic_effect_detail, keeping "
            "the detail short and observable. The runtime compiles the exact detail into the visible "
            "beat; keep pressure, choices, and canon compatible with it without copying the sentence. "
            "Keep unrelated discoveries separate."
        )
    if rejection_code == "MAGIC_RESULT_CLAIM_UNSUPPORTED":
        terms = ", ".join(forbidden_magic_terms) or "the identified forbidden terms"
        return (
            "Remove every prohibited unsupported claim from every director-plan field. Do not "
            "repeat the offending term, an inflection of it, or a close medical synonym. The rejected "
            f"plan contains these forbidden MAGIC result terms: {terms}. Rewrite only the fields that "
            "contain them in observation-only language: describe visible behavior, sound, timing, or "
            "position and leave diagnosis, tissue, and severity unresolved. Preserve the runtime-owned "
            "adjudication and repair the listed consequence-field consistency issues as well."
        )
    if rejection_code == "DIRECTOR_SENSITIVE_STAKES":
        return (
            "MANDATORY LETHAL-STAKES REPAIR: preserve the deadline, urgency, scene objective, "
            "clock changes, next actor, and every unrelated fact, but replace every death, "
            "asphyxiation, fatal-heat, suicide, or self-destruction consequence. The replacement "
            "must be concrete and severe but nonlethal: loss of time, position, trust, access, "
            "propulsion, habitat capacity, cooling, data, or another named resource. This is the "
            "required exception to preserving the rejected cost. Do not use a euphemism for death."
        )
    return "Repair only the validator issue named below."


def _normalized_story_text(value: str) -> str:
    """Compare shared prose without collapsing distinct wording into a similarity score."""

    return " ".join(value.casefold().split())


def _magic_scope_terms(challenge: str) -> tuple[str, ...]:
    """Return substantive challenge words used to reject unrelated roll answers."""

    stop_words = {
        "about", "after", "before", "being", "can", "could", "does", "from", "identify",
        "into", "mara", "might", "must", "near", "onto", "read", "reveal", "reveals",
        "should", "tell", "that", "their", "them", "there", "these", "they", "this",
        "through", "touching", "under", "until", "what", "when", "where", "which", "while",
        "with", "without", "would", "your",
    }
    return tuple(
        dict.fromkeys(
            token
            for token in re.findall(r"[a-z]+", challenge.casefold())
            if len(token) >= 4 and token not in stop_words
        )
    )


def _magic_term_present(text: str, term: str) -> bool:
    normalized = " ".join(term.casefold().split())
    if not normalized:
        return False
    pattern = r"\b" + re.escape(normalized).replace(r"\ ", r"\s+") + r"(?:s|ed|ing)?\b"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _magic_roll_summary(payload: dict[str, object]) -> str:
    faces = payload.get("die_faces", [])
    face_text = " + ".join(str(face) for face in faces)
    stat_modifier = int(payload.get("stat_modifier", 0))
    situational_modifier = int(payload.get("situational_modifier", 0))
    total = int(payload.get("total", 0))
    return (
        f"MAGIC ROLL — {payload.get('character_name', 'Character')} chose "
        f"{payload.get('attribute', 'MAGIC')} ({payload.get('attribute_score', '?')}): "
        f"2d6 [{face_text}] + stat {stat_modifier:+d} + situation "
        f"{situational_modifier:+d} = {total} — {str(payload.get('outcome', 'unknown')).upper()}. "
        f"Challenge: {payload.get('challenge', '')}. "
        f"Success criteria: {payload.get('success_criteria', '')}"
    )


def _compile_director_beat(
    lead_in: str,
    plan: DirectorPlanEnvelope,
    continuity_anchor: str,
    *,
    magic_adjudication: MagicAdjudication | None = None,
) -> str:
    """Make the validated plan and runtime adjudication visible without asking twice.

    The prose model supplies atmosphere only.  The game-master's actual state
    change and choices are compiled verbatim, which preserves actor agency and
    prevents a fluent renderer from silently dropping the turn's decision. The
    MAGIC tier and goal answer come from the runtime, never from the plan.
    """

    outcome_line = None
    if magic_adjudication is not None:
        result_label = magic_adjudication.outcome.value.replace("_", " ")
        goal_status = magic_adjudication.goal_status.value.replace("_", " ")
        if magic_adjudication.outcome is MagicOutcome.COSTLY_SUCCESS:
            outcome_line = (
                f"MAGIC result: {result_label}; goal {goal_status}: "
                f"{magic_adjudication.goal_answer}; "
                f"{plan.magic_cost_type.value} cost: {plan.magic_effect_detail}"
            )
        elif magic_adjudication.outcome is MagicOutcome.SETBACK:
            outcome_line = (
                f"MAGIC result: {result_label}; goal {goal_status}: {magic_adjudication.goal_answer}; "
                f"new opening: {plan.magic_effect_detail}"
            )
        else:
            outcome_line = (
                f"MAGIC result: {result_label}; goal {goal_status}: {magic_adjudication.goal_answer}; "
                f"visible consequence: {plan.magic_effect_detail}"
            )
    return "\n".join(
        line
        for line in (
            lead_in.strip(),
            f"At {continuity_anchor}: {plan.state_change}",
            outcome_line,
            f"Pressure: {plan.pressure}",
            f"Choice A: {plan.choice_a}",
            f"Choice B: {plan.choice_b}",
        )
        if line
    )


def continuity_anchors_for_opening(opening: OpeningSnapshot) -> tuple[str, ...]:
    """Derive a small, creator-visible anchor set for director continuity checks."""

    stop_words = {
        "advanced", "inside", "through", "under", "their", "there", "where", "with",
        "that", "this", "from", "into", "your", "have", "will", "world", "rules",
    }
    words = re.findall(r"[A-Za-z]{5,}", f"{opening.set} {opening.setting}".casefold())
    return tuple(dict.fromkeys(word for word in words if word not in stop_words))


__all__ = [
    "SceneActor",
    "SceneRunError",
    "SceneRunResult",
    "SceneRunner",
    "continuity_anchors_for_opening",
]
