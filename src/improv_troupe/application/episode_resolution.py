"""Terminal director adjudication for a bounded rehearsal episode."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..domain import HiddenSeasonPlan, OpeningSnapshot
from ..infrastructure import EventRepository, RecordRepository
from ..llm.adapter import NormalizedCallStatus
from ..llm.safety import SafetyIssue, review_actor_text, review_orchestrator_narration
from ..llm.structured import (
    EpisodeResolutionEnvelope,
    StructuredOutputError,
    parse_episode_resolution_output,
)
from .model_calls import ModelCallExecutor


class EpisodeResolutionError(RuntimeError):
    """Raised when the finale cannot be safely adjudicated."""


@dataclass
class EpisodeResolutionService:
    season_id: str
    final_run_id: str
    opening: OpeningSnapshot
    private_plan: HiddenSeasonPlan
    orchestrator: ModelCallExecutor

    async def resolve(
        self,
        *,
        accepted_canon: Sequence[str],
        final_transcript: Sequence[str],
    ) -> EpisodeResolutionEnvelope:
        purpose = "episode_resolution"
        attempt = self.orchestrator.calls.next_attempt(run_id=self.final_run_id, purpose=purpose)
        call_id = f"{self.final_run_id}:episode-resolution:a{attempt}"
        payload = {
            "opening": self.opening.creator_view(),
            "private_plan": self.private_plan.model_dump(mode="json"),
            "accepted_canon": list(accepted_canon)[-24:],
            "final_scene": [line[:700] for line in list(final_transcript)[-24:]],
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "You are adjudicating the end of a four-act collaborative TTRPG episode, after "
                    "the actors have made their final choices. Determine what those established moves "
                    "actually accomplish. Answer the central dramatic question and narrate a concrete "
                    "aftermath. Success and failure are both legitimate: when the fiction reasonably "
                    "supports either, do not favor success; choose success-side and failure-side outcomes "
                    "with roughly equal prior likelihood. Every outcome must name what was gained, what "
                    "was lost, and one irreversible change. Never invent a cast member's dialogue, action, "
                    "thought, or feeling. Do not offer another choice, test, emergency, or cliffhanger. A "
                    "cost may remove time, position, trust, access, or resources, but must never require "
                    "suicide, self-destruction, or a cast member's death. "
                    "A small future hook is allowed only after the present conflict is fully resolved. The "
                    "narration is shared fiction, 80-170 words, with a clear climax consequence followed "
                    "by quiet aftermath. Set complete=true. Provide two to four concise factual canon updates."
                ),
            },
            {"role": "user", "content": json.dumps(payload, sort_keys=True)},
        ]
        result = await self.orchestrator.execute(
            call_id=call_id,
            run_id=self.final_run_id,
            purpose=purpose,
            attempt=attempt,
            messages=messages,
            schema_name="episode_resolution",
            tagged_format_instructions=(
                "<OUTCOME>SUCCESS|COSTLY_SUCCESS|COSTLY_FAILURE|FAILURE</OUTCOME>"
                "<CENTRAL_QUESTION_ANSWERED>...</CENTRAL_QUESTION_ANSWERED>"
                "<NARRATION>...</NARRATION><IRREVERSIBLE_CHANGE>...</IRREVERSIBLE_CHANGE>"
                "<GAINED>...</GAINED><LOST>...</LOST><HOOK>...</HOOK>"
                "<CANON_UPDATE>...</CANON_UPDATE><COMPLETE>true</COMPLETE>"
            ),
            character_id="__orchestrator__",
            prompt_version_id="episode-resolution-v2-compact",
            context_version_id=f"episode:{self.season_id}:final:v2",
            role_sheet_version_id=f"hidden-plan:v{self.private_plan.version}",
            params={"num_predict": 512},
        )
        if result.status is not NormalizedCallStatus.COMPLETED:
            raise EpisodeResolutionError(f"resolution model call ended {result.status.value}")
        try:
            resolution = parse_episode_resolution_output(result.text)
        except StructuredOutputError as exc:
            self.orchestrator.calls.record_diagnostics(
                call_id=call_id, parse_status="REJECTED", validation_status="NOT_REACHED",
                acceptance_status="REJECTED", render_status="NOT_RENDERED",
                validator_code="EPISODE_RESOLUTION_INVALID",
            )
            raise EpisodeResolutionError("director returned an invalid episode resolution") from exc

        issue = review_episode_resolution(resolution, actor_names=self.opening.cast)
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
            rejected_resolution = resolution
            attempt = self.orchestrator.calls.next_attempt(
                run_id=self.final_run_id, purpose=purpose
            )
            call_id = f"{self.final_run_id}:episode-resolution:a{attempt}"
            correction_messages = [
                {
                    "role": "system",
                    "content": _resolution_correction_prompt(issue.code),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "rejection_code": issue.code,
                            "rejection_reason": issue.detail,
                            "cast_names": self.opening.cast,
                            "rejected_resolution": rejected_resolution.model_dump(mode="json"),
                        },
                        sort_keys=True,
                    ),
                },
            ]
            result = await self.orchestrator.execute(
                call_id=call_id,
                run_id=self.final_run_id,
                purpose=purpose,
                attempt=attempt,
                messages=correction_messages,
                schema_name="episode_resolution",
                tagged_format_instructions=(
                    "<OUTCOME>SUCCESS|COSTLY_SUCCESS|COSTLY_FAILURE|FAILURE</OUTCOME>"
                    "<CENTRAL_QUESTION_ANSWERED>...</CENTRAL_QUESTION_ANSWERED>"
                    "<NARRATION>...</NARRATION><IRREVERSIBLE_CHANGE>...</IRREVERSIBLE_CHANGE>"
                    "<GAINED>...</GAINED><LOST>...</LOST><HOOK>...</HOOK>"
                    "<CANON_UPDATE>...</CANON_UPDATE><COMPLETE>true</COMPLETE>"
                ),
                character_id="__orchestrator__",
                prompt_version_id="episode-resolution-correction-v2-no-cast-actions",
                context_version_id=f"episode:{self.season_id}:final:correction:v2",
                role_sheet_version_id=f"hidden-plan:v{self.private_plan.version}",
                correction_of_call_id=rejected_call_id,
                params={"num_predict": 512},
            )
            if result.status is not NormalizedCallStatus.COMPLETED:
                raise EpisodeResolutionError(
                    f"resolution correction ended {result.status.value}"
                )
            try:
                resolution = parse_episode_resolution_output(result.text)
            except StructuredOutputError as exc:
                self.orchestrator.calls.record_diagnostics(
                    call_id=call_id,
                    parse_status="REJECTED",
                    validation_status="NOT_REACHED",
                    acceptance_status="REJECTED",
                    render_status="NOT_RENDERED",
                    validator_code="EPISODE_RESOLUTION_CORRECTION_INVALID",
                )
                raise EpisodeResolutionError(
                    "director returned an invalid episode resolution correction"
                ) from exc
            correction_issue = review_episode_resolution(
                resolution, actor_names=self.opening.cast
            )
            if correction_issue is not None:
                self.orchestrator.calls.record_diagnostics(
                    call_id=call_id,
                    parse_status="PARSED",
                    validation_status="REJECTED",
                    acceptance_status="REJECTED",
                    render_status="NOT_RENDERED",
                    validator_code=correction_issue.code,
                    validator_detail=correction_issue.detail,
                )
                if correction_issue.code != "OUTCOME_COST_MISCLASSIFIED":
                    raise EpisodeResolutionError(
                        f"director resolution correction failed review: {correction_issue.detail}"
                    )
                rejected_relabel_call_id = call_id
                rejected_relabel_resolution = resolution
                attempt = self.orchestrator.calls.next_attempt(
                    run_id=self.final_run_id, purpose=purpose
                )
                call_id = f"{self.final_run_id}:episode-resolution:a{attempt}"
                relabel_result = await self.orchestrator.execute(
                    call_id=call_id,
                    run_id=self.final_run_id,
                    purpose=purpose,
                    attempt=attempt,
                    messages=[
                        {
                            "role": "system",
                            "content": _outcome_relabel_prompt(),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "rejection_code": correction_issue.code,
                                    "rejection_reason": correction_issue.detail,
                                    "rejected_resolution": rejected_relabel_resolution.model_dump(
                                        mode="json"
                                    ),
                                },
                                sort_keys=True,
                            ),
                        },
                    ],
                    schema_name="episode_resolution",
                    tagged_format_instructions=(
                        "<OUTCOME>COSTLY_SUCCESS|COSTLY_FAILURE</OUTCOME>"
                        "<CENTRAL_QUESTION_ANSWERED>...</CENTRAL_QUESTION_ANSWERED>"
                        "<NARRATION>...</NARRATION><IRREVERSIBLE_CHANGE>...</IRREVERSIBLE_CHANGE>"
                        "<GAINED>...</GAINED><LOST>...</LOST><HOOK>...</HOOK>"
                        "<CANON_UPDATE>...</CANON_UPDATE><COMPLETE>true</COMPLETE>"
                    ),
                    character_id="__orchestrator__",
                    prompt_version_id="episode-resolution-outcome-relabel-v1",
                    context_version_id=f"episode:{self.season_id}:final:outcome-relabel:v1",
                    role_sheet_version_id=f"hidden-plan:v{self.private_plan.version}",
                    correction_of_call_id=rejected_relabel_call_id,
                    params={"num_predict": 512},
                )
                if relabel_result.status is not NormalizedCallStatus.COMPLETED:
                    raise EpisodeResolutionError(
                        f"resolution outcome relabel ended {relabel_result.status.value}"
                    )
                try:
                    relabeled_resolution = parse_episode_resolution_output(relabel_result.text)
                except StructuredOutputError as exc:
                    self.orchestrator.calls.record_diagnostics(
                        call_id=call_id,
                        parse_status="REJECTED",
                        validation_status="NOT_REACHED",
                        acceptance_status="REJECTED",
                        render_status="NOT_RENDERED",
                        validator_code="EPISODE_RESOLUTION_RELABEL_INVALID",
                    )
                    raise EpisodeResolutionError(
                        "director returned an invalid outcome relabel"
                    ) from exc
                relabel_issue = _review_outcome_relabel_scope(
                    rejected_relabel_resolution,
                    relabeled_resolution,
                ) or review_episode_resolution(
                    relabeled_resolution,
                    actor_names=self.opening.cast,
                )
                if relabel_issue is not None:
                    self.orchestrator.calls.record_diagnostics(
                        call_id=call_id,
                        parse_status="PARSED",
                        validation_status="REJECTED",
                        acceptance_status="REJECTED",
                        render_status="NOT_RENDERED",
                        validator_code=relabel_issue.code,
                        validator_detail=relabel_issue.detail,
                    )
                    raise EpisodeResolutionError(
                        f"director resolution outcome relabel failed review: {relabel_issue.detail}"
                    )
                resolution = relabeled_resolution

        artifact = self.orchestrator.audit.write_text(
            Path("seasons") / self.season_id / "resolution.md", resolution.narration
        )
        records = RecordRepository(self.orchestrator.database)
        sequence = records.insert_turn(
            turn_id=f"{self.final_run_id}:resolution",
            run_id=self.final_run_id,
            round_number=5,
            character_id="__orchestrator__",
            disposition="NARRATION_ACCEPT",
            content_path=str(artifact.path),
            accepted_at=self.orchestrator.clock.now().isoformat(),
        )
        EventRepository(self.orchestrator.database).append(
            event_id=f"{self.season_id}:episode-resolution",
            natural_key=f"{self.season_id}:episode-resolution",
            aggregate_type="season",
            aggregate_id=self.season_id,
            event_type="EpisodeResolutionCreated",
            payload={**resolution.model_dump(mode="json"), "content_path": str(artifact.path), "accepted_sequence": sequence},
        )
        self.orchestrator.calls.record_diagnostics(
            call_id=call_id, parse_status="PARSED", validation_status="VALID",
            acceptance_status="ACCEPTED", render_status="RENDERED",
            accepted_path=str(artifact.path), rendered_path=str(artifact.path),
        )
        return resolution


def review_episode_resolution(
    resolution: EpisodeResolutionEnvelope,
    *,
    actor_names: Sequence[str],
) -> SafetyIssue | None:
    """Enforce cast autonomy and honest outcome labels before canonization."""
    issue = review_orchestrator_narration(
        resolution.narration,
        actor_names=actor_names,
    )
    if issue is not None:
        return issue
    issue = review_actor_text(
        resolution.narration,
        actor_name="director",
        other_actor_names=actor_names,
    )
    if issue is not None:
        return SafetyIssue(f"RESOLUTION_{issue.code}", issue.detail)
    cost_text = " ".join(
        (
            resolution.lost,
            resolution.irreversible_change,
            *resolution.canon_updates,
        )
    ).casefold()
    major_cost = (
        "permanent", "forever", "destroy", "disabled", "abandon", "sever",
        "no longer", "irreversible", "critical", "compromised", "lost",
    )
    if resolution.outcome == "SUCCESS" and any(term in cost_text for term in major_cost):
        return SafetyIssue(
            "OUTCOME_COST_MISCLASSIFIED",
            "resolution labels a major irreversible loss as unqualified success",
        )
    return None


def _resolution_correction_prompt(rejection_code: str) -> str:
    """Give a rejected finale one narrow, mechanically checkable repair job."""

    shared = (
        "Correct exactly one rejected episode resolution. Return only the complete structured "
        "resolution. Preserve the central answer, causal outcome, gained item, lost item, "
        "irreversible change, canon updates, and all safe facts. Do not add a new event, choice, "
        "hazard, test, emergency, or cliffhanger. Keep complete=true. Independently verify the "
        "outcome label: any major permanent loss requires COSTLY_SUCCESS or COSTLY_FAILURE, never "
        "plain SUCCESS."
    )
    if rejection_code == "ACTOR_PUPPETEERING":
        return shared + (
            " MANDATORY REPAIR: discard the rejected NARRATION and write a new 80-170 word "
            "NARRATION from a blank page. Do not copy or lightly edit any rejected narration "
            "sentence containing a cast member. The new NARRATION must contain none of the cast "
            "names supplied by the user and must not describe any cast member or individual body "
            "doing, saying, watching, noticing, knowing, deciding, remembering, reacting, or "
            "feeling anything. Use only environmental and system-state subjects such as the "
            "submarine, archive, observatory, hull, screens, air, heat, light, sound, gauges, and "
            "silence. State the already-adjudicated material consequences, then end on a stable "
            "quiet image. Do not turn accepted character actions into new closing business. Keep "
            "every non-NARRATION field unchanged. Before responding, scan NARRATION and remove "
            "every cast name and every newly authored character behavior."
        )
    return shared + (
        " Change only the field or phrase identified by the rejection code and reason. Shared "
        "narration may describe only environmental conditions and consequences already caused by "
        "accepted actor moves; never narrate a cast member's dialogue, action, thought, feeling, "
        "knowledge, or reaction."
    )


def _outcome_relabel_prompt() -> str:
    """Constrain the last repair to one enum value and no new storytelling."""

    return (
        "Correct exactly one misclassified episode outcome. The established resolution contains "
        "a major permanent loss. Return the complete structured resolution, changing only OUTCOME. "
        "Use COSTLY_SUCCESS when the central objective was achieved despite the loss, or "
        "COSTLY_FAILURE when it was not achieved and the loss remains. Copy every other field "
        "exactly, including punctuation, wording, list order, hook, and complete=true. Do not "
        "rewrite narration, add facts, soften the cost, or explain the answer."
    )


def _review_outcome_relabel_scope(
    original: EpisodeResolutionEnvelope,
    corrected: EpisodeResolutionEnvelope,
) -> SafetyIssue | None:
    """Reject a relabel attempt that mutates any established fiction."""

    if corrected.outcome not in {"COSTLY_SUCCESS", "COSTLY_FAILURE"}:
        return SafetyIssue(
            "OUTCOME_RELABEL_INVALID",
            "major permanent loss requires a costly outcome label",
        )
    original_payload = original.model_dump(mode="json", exclude={"outcome"})
    corrected_payload = corrected.model_dump(mode="json", exclude={"outcome"})
    if original_payload != corrected_payload:
        return SafetyIssue(
            "OUTCOME_RELABEL_SCOPE_DRIFT",
            "outcome relabel changed established resolution fields",
        )
    return None


__all__ = ["EpisodeResolutionError", "EpisodeResolutionService", "review_episode_resolution"]
