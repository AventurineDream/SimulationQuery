"""Truthful, privacy-bounded read projections for dashboard v2."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

from ..application import ServicePaths
from ..infrastructure import SQLiteDatabase
from ..llm.structured import StructuredOutputError, parse_diary_output
from .dashboard_contracts import (
    AcceptedStoryRecord,
    AttentionItem,
    AttentionSummary,
    CanonReviewItem,
    CallRawDisclosure,
    CastSummary,
    ContinuitySummary,
    DashboardContextData,
    DashboardEnvelope,
    DashboardMeta,
    DashboardNotFound,
    DayCompletion,
    DiaryAttemptDisclosure,
    DiaryReviewSummary,
    DiagnosticsCallDetail,
    DiagnosticsCallSummary,
    DiagnosticsData,
    DiagnosticsProvenance,
    DiagnosticsStage,
    FictionClockFrame,
    Freshness,
    HealthSummary,
    HomeData,
    HomeSummary,
    LastAcceptedBeat,
    LiveCallProgress,
    LiveControl,
    LiveData,
    LiveRecoveryState,
    LiveRunState,
    LiveTranscriptData,
    LiveWorkItem,
    NavigationItem,
    NextSlot,
    CharacterCardSummary,
    ModelAssignmentSummary,
    PreparationData,
    PreparationInvalidation,
    PreparationStep,
    PrivatePreparationArtifactSummary,
    PrivatePreparationDisclosure,
    ReviewCastMember,
    ReviewDayData,
    ReviewDayState,
    ReviewRunSummary,
    RunProgress,
    SeasonSummary,
    WorkerSummary,
)


ACTIVE_SEASON_STATUSES = {
    "ARMED",
    "RUNNING",
    "PAUSED",
    "RECOVERY_REQUIRED",
    "CLOSING",
}
RESOLVED_RUN_STATUSES = {"COMPLETED", "SKIPPED"}
ACCEPTED_TURN_DISPOSITIONS = {
    "ACCEPT",
    "ACCEPT_AFTER_CORRECTION",
    "NARRATION_ACCEPT",
    "NEUTRAL_INTERRUPTION",
}
NAVIGATION: tuple[tuple[str, str, bool], ...] = (
    ("home", "Home", True),
    ("prepare", "Prepare", True),
    ("live", "Live", True),
    ("review", "Review", True),
    ("diagnostics", "Diagnostics", True),
    ("seasons", "Seasons", True),
)


class DashboardReadModels:
    """Build allowlisted v2 responses from durable SQLite and storage evidence."""

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        paths: ServicePaths,
        environment: Literal["sandbox", "production"],
        now: datetime,
    ) -> None:
        self.database = database
        self.connection = database.connection
        self.paths = paths
        self.environment = environment
        self.now = _aware(now)

    def context(self, season_id: str | None = None) -> DashboardEnvelope:
        context = self._context(season_id)
        lifecycle = self._selected(context)
        return DashboardEnvelope(
            meta=self._meta(lifecycle, Freshness.FRESH),
            data=context.model_dump(mode="json"),
        )

    def home(self, season_id: str | None = None) -> DashboardEnvelope:
        context = self._context(season_id)
        lifecycle = self._selected(context)
        health, health_reasons = self._health()
        worker = self._worker()
        if lifecycle is None:
            attention = self._attention(None)
            data = HomeData(
                state="no_season",
                context=context,
                summary=HomeSummary(
                    heading="No season is stored yet.",
                    message="Home will populate after a season has durable state.",
                    tone="empty",
                ),
                lifecycle=None,
                attention=attention,
                progress=RunProgress(
                    scheduled=0,
                    resolved=0,
                    completed=0,
                    skipped=0,
                    unresolved=0,
                    days_closed=0,
                    days_scheduled=0,
                ),
                last_accepted_beat=LastAcceptedBeat(available=False),
                next_slot=NextSlot(available=False),
                cast=[],
                day_completion=DayCompletion(
                    available=False,
                    state="not_scheduled",
                    complete=False,
                    scheduled_runs=0,
                    resolved_runs=0,
                    diary_counts={},
                ),
                worker=worker,
                health=health,
                recent_seasons=context.seasons[:5],
                partial_reasons=health_reasons,
            )
            freshness = Freshness.PARTIAL if health_reasons else Freshness.FRESH
            return DashboardEnvelope(
                meta=self._meta(None, freshness),
                data=data.model_dump(mode="json"),
            )

        selected_id = lifecycle.season_id
        progress = self._progress(selected_id)
        day_completion = self._day_completion(selected_id)
        attention = self._attention(selected_id)
        last_beat, beat_reason = self._last_accepted_beat(selected_id)
        partial_reasons = list(health_reasons)
        if day_completion.state == "closed_with_unresolved":
            partial_reasons.append("A closed day still has unresolved scheduled runs.")
        if lifecycle.status == "RECOVERY_REQUIRED" and not self._has_active_recovery(selected_id):
            partial_reasons.append(
                "The selected season expects recovery detail, but no active request is stored."
            )
        if beat_reason:
            partial_reasons.append(beat_reason)
        summary = self._summary(attention, partial_reasons)
        data = HomeData(
            state="ready",
            context=context,
            summary=summary,
            lifecycle=lifecycle,
            attention=attention,
            progress=progress,
            last_accepted_beat=last_beat,
            next_slot=self._next_slot(selected_id),
            cast=self._cast(selected_id),
            day_completion=day_completion,
            worker=worker,
            health=health,
            recent_seasons=context.seasons[:5],
            partial_reasons=partial_reasons,
        )
        freshness = Freshness.PARTIAL if partial_reasons else Freshness.FRESH
        return DashboardEnvelope(
            meta=self._meta(lifecycle, freshness),
            data=data.model_dump(mode="json"),
        )

    def prepare(
        self,
        season_id: str | None = None,
        *,
        step: str | None = None,
        character_id: str | None = None,
    ) -> DashboardEnvelope:
        """Project one versioned preparation rehearsal without private generated text."""
        context = self._context(season_id)
        lifecycle = self._selected(context)
        if lifecycle is None:
            data = PreparationData(
                state="no_season", context=context, workspace_version=None, idea=None,
                idea_version=None, opening_version=None, selected_step=None, steps=[], cards=[],
                selected_character_id=None, model_assignment=None, latest_receipts={},
                invalidations=[], private_artifacts=[], partial_reasons=[],
            )
            return DashboardEnvelope(meta=self._meta(None, Freshness.FRESH), data=data.model_dump(mode="json"))
        workspace = self.connection.execute(
            "SELECT * FROM preparation_workspaces WHERE season_id = ?", (lifecycle.season_id,)
        ).fetchone()
        if workspace is None:
            data = PreparationData(
                state="unavailable", context=context, workspace_version=None, idea=None,
                idea_version=None, opening_version=None, selected_step=None, steps=[], cards=[],
                selected_character_id=None, model_assignment=None, latest_receipts={},
                invalidations=[], private_artifacts=[],
                partial_reasons=["No preparation rehearsal ledger is stored for this season."],
            )
            return DashboardEnvelope(meta=self._meta(lifecycle, Freshness.PARTIAL), data=data.model_dump(mode="json"))
        valid_steps = {
            "idea", "opening", "character_cards", "model_assignment", "preflight",
            "private_preparation", "schedule_preview", "green_review",
        }
        selected_step = step if step in valid_steps else "character_cards"
        latest_receipts: dict[str, dict[str, object]] = {}
        for row in self.connection.execute(
            "SELECT * FROM preparation_receipts WHERE season_id = ? ORDER BY workspace_version",
            (lifecycle.season_id,),
        ):
            detail: dict[str, object] = {}
            try:
                decoded = json.loads(str(row["detail_json"]))
                if isinstance(decoded, dict): detail = decoded
            except (TypeError, ValueError):
                pass
            latest_receipts[str(row["step"])] = {
                "receipt_id": str(row["receipt_id"]), "status": str(row["status"]),
                "workspace_version": int(row["workspace_version"]), "detail": detail,
                "created_at": str(row["created_at"]),
            }
        cards: list[CharacterCardSummary] = []
        card_rows = self.connection.execute(
            "SELECT cc.* FROM character_card_versions cc WHERE cc.season_id = ? "
            "AND cc.version = (SELECT MAX(version) FROM character_card_versions latest "
            "WHERE latest.season_id = cc.season_id AND latest.character_id = cc.character_id) "
            "ORDER BY cc.character_id", (lifecycle.season_id,),
        ).fetchall()
        for row in card_rows:
            prior = [int(item["version"]) for item in self.connection.execute(
                "SELECT version FROM character_card_versions WHERE season_id = ? AND character_id = ? "
                "AND version < ? ORDER BY version DESC",
                (lifecycle.season_id, str(row["character_id"]), int(row["version"])),
            )]
            approved_row = self.connection.execute(
                "SELECT * FROM character_card_versions WHERE season_id = ? AND character_id = ? "
                "AND status = 'APPROVED' AND version < ? ORDER BY version DESC LIMIT 1",
                (lifecycle.season_id, str(row["character_id"]), int(row["version"])),
            ).fetchone()
            approved_truth = None
            if approved_row is not None:
                approved_truth = {
                    "version": int(approved_row["version"]),
                    "pronouns": str(approved_row["pronouns"]),
                    "public_brief": str(approved_row["public_brief"]),
                    "occupation_skills": self._json_string_list(approved_row["occupation_skills_json"]),
                    "voice_anchors": self._json_string_list(approved_row["voice_anchors_json"]),
                    "habits": self._json_string_list(approved_row["habits_json"]),
                }
            cards.append(CharacterCardSummary(
                character_id=str(row["character_id"]), name=str(row["name"]),
                version=int(row["version"]), status=str(row["status"]),
                pronouns=str(row["pronouns"]), public_brief=str(row["public_brief"]),
                occupation_skills=self._json_string_list(row["occupation_skills_json"]),
                voice_anchors=self._json_string_list(row["voice_anchors_json"]),
                habits=self._json_string_list(row["habits_json"]),
                derived_opening_version=int(row["derived_opening_version"]),
                created_at=_parse_datetime(str(row["created_at"])),
                approved_at=_parse_optional_datetime(row["approved_at"]), prior_versions=prior,
                approved_truth=approved_truth,
            ))
        approved_cards = sum(card.status == "APPROVED" for card in cards)
        all_cards = bool(cards) and approved_cards == len(cards)
        labels = (
            ("idea", "Season idea"), ("opening", "Opening"),
            ("character_cards", "Character cards"), ("model_assignment", "Model assignment"),
            ("preflight", "Preflight"), ("private_preparation", "Private preparation"),
            ("schedule_preview", "Schedule preview"), ("green_review", "Green review"),
        )
        steps: list[PreparationStep] = []
        for number, (key, label) in enumerate(labels, start=1):
            receipt = latest_receipts.get(key)
            if receipt:
                raw_status = str(receipt["status"]).lower()
                status_value = "ready" if raw_status == "ready" else ("approved" if raw_status == "approved" else "complete")
                detail = f"Receipt at workspace v{receipt['workspace_version']}"
            elif key == "character_cards":
                status_value = "approved" if all_cards else "ready_for_review"
                detail = f"{approved_cards} of {len(cards)} approved"
            else:
                previous_key = labels[number - 2][0] if number > 1 else None
                previous_complete = previous_key is None or previous_key in latest_receipts or (previous_key == "character_cards" and all_cards)
                status_value = "not_started" if previous_complete else "blocked"
                detail = "Ready for deliberate evidence" if previous_complete else "Prior step is incomplete"
            steps.append(PreparationStep(
                number=number, key=key, label=label, status=status_value,
                detail=detail, selected=key == selected_step,
            ))
        assignment_row = self.connection.execute(
            "SELECT * FROM model_assignment_versions WHERE season_id = ? ORDER BY version DESC LIMIT 1",
            (lifecycle.season_id,),
        ).fetchone()
        assignment = None
        if assignment_row is not None:
            assignments: dict[str, str] = {}
            if selected_step == "model_assignment":
                try:
                    decoded = json.loads(str(assignment_row["assignments_json"]))
                    if isinstance(decoded, dict): assignments = {str(k): str(v) for k, v in decoded.items()}
                except (TypeError, ValueError):
                    pass
            assignment = ModelAssignmentSummary(
                version=int(assignment_row["version"]), status=str(assignment_row["status"]),
                manifest_name=str(assignment_row["manifest_name"]), assignments=assignments,
            )
        invalidations = [PreparationInvalidation(
            event_id=str(row["event_id"]), source_step=str(row["source_step"]),
            source_version=int(row["source_version"]),
            invalidated_steps=self._json_string_list(row["invalidated_steps_json"]),
            reason=str(row["reason"]), created_at=_parse_datetime(str(row["created_at"])),
        ) for row in self.connection.execute(
            "SELECT * FROM preparation_invalidation_events WHERE season_id = ? ORDER BY created_at DESC",
            (lifecycle.season_id,),
        )]
        private_artifacts: list[PrivatePreparationArtifactSummary] = []
        if selected_step == "private_preparation":
            for row in self.connection.execute(
                "SELECT p.*, c.name FROM private_preparation_versions p "
                "JOIN cast_members c ON c.season_id = p.season_id AND c.character_id = p.character_id "
                "WHERE p.season_id = ? AND p.version = ("
                "SELECT MAX(version) FROM private_preparation_versions latest "
                "WHERE latest.season_id = p.season_id AND latest.character_id = p.character_id "
                "AND latest.artifact_kind = p.artifact_kind) "
                "ORDER BY p.character_id, p.artifact_kind",
                (lifecycle.season_id,),
            ):
                query = urlencode({
                    "season_id": lifecycle.season_id,
                    "character_id": str(row["character_id"]),
                    "artifact_kind": str(row["artifact_kind"]),
                })
                private_artifacts.append(PrivatePreparationArtifactSummary(
                    character_id=str(row["character_id"]),
                    character_name=str(row["name"]),
                    artifact_kind=str(row["artifact_kind"]),
                    version=int(row["version"]),
                    source_character_card_version=int(row["source_character_card_version"]),
                    status=str(row["status"]),
                    disclosure_href=f"/api/v2/prepare/private-artifact?{query}",
                ))
        selected_character = character_id if any(card.character_id == character_id for card in cards) else (cards[0].character_id if cards else None)
        data = PreparationData(
            state="ready", context=context, workspace_version=int(workspace["version"]),
            idea=str(workspace["idea"]), idea_version=int(workspace["idea_version"]),
            opening_version=int(workspace["opening_version"]), selected_step=selected_step,
            steps=steps, cards=cards, selected_character_id=selected_character,
            model_assignment=assignment, latest_receipts=latest_receipts,
            invalidations=invalidations, private_artifacts=private_artifacts,
            partial_reasons=[],
        )
        return DashboardEnvelope(meta=self._meta(lifecycle, Freshness.FRESH), data=data.model_dump(mode="json"))

    def private_preparation_artifact(
        self, season_id: str, *, character_id: str, artifact_kind: str
    ) -> DashboardEnvelope:
        """Deliberately disclose one fixture artifact without exposing paths or wellness wording."""
        if artifact_kind not in {"role_sheet", "orientation"}:
            raise DashboardNotFound("unknown private preparation artifact")
        context = self._context(season_id)
        lifecycle = self._selected(context)
        if lifecycle is None or lifecycle.season_id != season_id:
            raise DashboardNotFound("season is unavailable")
        row = self.connection.execute(
            "SELECT p.*, c.name FROM private_preparation_versions p "
            "JOIN cast_members c ON c.season_id = p.season_id AND c.character_id = p.character_id "
            "WHERE p.season_id = ? AND p.character_id = ? AND p.artifact_kind = ? "
            "ORDER BY p.version DESC LIMIT 1",
            (season_id, character_id, artifact_kind),
        ).fetchone()
        if row is None:
            raise DashboardNotFound("private preparation artifact is unavailable")
        try:
            content = json.loads(str(row["content_json"]))
        except (TypeError, ValueError) as exc:
            raise DashboardNotFound("private preparation artifact is unreadable") from exc
        if not isinstance(content, dict):
            raise DashboardNotFound("private preparation artifact is unreadable")
        if artifact_kind == "orientation":
            content.pop("wellness_signal", None)
            content.pop("raw_wellness", None)
        disclosure = PrivatePreparationDisclosure(
            season_id=season_id,
            character_id=character_id,
            character_name=str(row["name"]),
            artifact_kind=artifact_kind,
            version=int(row["version"]),
            source_character_card_version=int(row["source_character_card_version"]),
            content=content,
            evidence_note=(
                "Private fixture evidence disclosed deliberately; paths and raw wellness wording remain withheld."
            ),
        )
        return DashboardEnvelope(
            meta=self._meta(lifecycle, Freshness.FRESH),
            data=disclosure.model_dump(mode="json"),
        )

    @staticmethod
    def _json_string_list(raw: object) -> list[str]:
        try:
            decoded = json.loads(str(raw))
        except (TypeError, ValueError):
            return []
        return [str(item) for item in decoded] if isinstance(decoded, list) else []

    def review_day(
        self,
        season_id: str | None = None,
        *,
        day_number: int | None = None,
        run_id: str | None = None,
    ) -> DashboardEnvelope:
        """Project one causal, privacy-bounded day reading surface."""
        context = self._context(season_id)
        lifecycle = self._selected(context)
        if lifecycle is None:
            data = ReviewDayData(
                state="no_season",
                context=context,
                day=None,
                selected_run_id=None,
                runs=[],
                diaries=[],
                cast=[],
                continuity=ContinuitySummary(
                    canon=[],
                    unresolved_state="unavailable",
                    unresolved_notes=[
                        "No season is selected, so continuity evidence is unavailable."
                    ],
                ),
                diary_counts={},
                accepted_record_count=0,
                partial_reasons=[],
            )
            return DashboardEnvelope(
                meta=self._meta(None, Freshness.FRESH),
                data=data.model_dump(mode="json"),
            )

        selected_day = self._review_day_number(lifecycle.season_id, day_number)
        day, day_reasons = self._review_day_state(lifecycle.season_id, selected_day)
        run_rows = self.connection.execute(
            "SELECT r.run_id, r.status, r.turn_count, r.completion_reason, "
            "r.actual_started_at, r.actual_completed_at, r.delay, "
            "s.run_number, s.slot_number, s.scheduled_local, s.scheduled_utc "
            "FROM runs r JOIN schedule_slots s ON s.slot_id = r.slot_id "
            "WHERE r.season_id = ? AND s.day_number = ? ORDER BY s.slot_number, r.run_id",
            (lifecycle.season_id, selected_day),
        ).fetchall()
        available_ids = {str(row["run_id"]) for row in run_rows}
        if run_id is not None and run_id not in available_ids:
            raise DashboardNotFound("selected run does not belong to the selected day")
        selected_run_id = run_id or (str(run_rows[0]["run_id"]) if run_rows else None)
        cast_names = {
            str(row["character_id"]): str(row["name"])
            for row in self.connection.execute(
                "SELECT character_id, name FROM cast_members WHERE season_id = ?",
                (lifecycle.season_id,),
            )
        }
        runs = [
            self._review_run(row, cast_names, selected_run_id=selected_run_id)
            for row in run_rows
        ]
        diaries = self._review_diaries(lifecycle.season_id, selected_day, cast_names)
        continuity = self._continuity(lifecycle.season_id)
        partial_reasons = list(day_reasons)
        for run in runs:
            partial_reasons.extend(run.evidence_notes)
        if continuity.unresolved_state == "unavailable":
            partial_reasons.extend(continuity.unresolved_notes)
        partial_reasons = list(dict.fromkeys(partial_reasons))
        diary_counts: dict[str, int] = {}
        for diary in diaries:
            diary_counts[diary.status] = diary_counts.get(diary.status, 0) + 1
        data = ReviewDayData(
            state="ready",
            context=context,
            day=day,
            selected_run_id=selected_run_id,
            runs=runs,
            diaries=diaries,
            cast=self._review_cast(lifecycle.season_id, selected_day, selected_run_id),
            continuity=continuity,
            diary_counts=diary_counts,
            accepted_record_count=sum(run.accepted_record_count for run in runs),
            partial_reasons=partial_reasons,
        )
        freshness = Freshness.PARTIAL if partial_reasons else Freshness.FRESH
        return DashboardEnvelope(
            meta=self._meta(lifecycle, freshness),
            data=data.model_dump(mode="json"),
        )

    def live(self, season_id: str | None = None) -> DashboardEnvelope:
        """Project current operational truth without opening the transcript pane."""
        context = self._context(season_id)
        lifecycle = self._selected(context)
        if lifecycle is None:
            data = LiveData(
                state="no_season", context=context, lifecycle=None, run=None,
                worker=self._worker(), active_work=None, queued_work=[],
                last_accepted_beat=LastAcceptedBeat(available=False), transcript_href=None,
                transcript_accepted_count=0,
                day_completion=DayCompletion(available=False, state="not_scheduled", complete=False,
                                             scheduled_runs=0, resolved_runs=0, diary_counts={}),
                recovery=None, controls=[], next_direction="No season is selected.",
                partial_reasons=[],
            )
            return DashboardEnvelope(meta=self._meta(None, Freshness.FRESH), data=data.model_dump(mode="json"))

        selected_id = lifecycle.season_id
        partial: list[str] = []
        run_row = self._live_run_row(selected_id)
        run = self._live_run(run_row) if run_row is not None else None
        work_rows = self.connection.execute(
            "SELECT * FROM work_items WHERE json_extract(payload_json, '$.season_id') = ? "
            "AND status IN ('LEASED', 'QUEUED') ORDER BY CASE status WHEN 'LEASED' THEN 0 ELSE 1 END, "
            "priority, available_at, work_id",
            (selected_id,),
        ).fetchall()
        work = [self._live_work(row) for row in work_rows]
        active_work = next((item for item in work if item.status == "LEASED"), None)
        queued_work = [item for item in work if item.status == "QUEUED"]
        last_beat, beat_reason = self._last_accepted_beat(selected_id)
        if beat_reason:
            partial.append(beat_reason)
        recovery = self._live_recovery(selected_id, run_row)
        if lifecycle.status == "RECOVERY_REQUIRED" and recovery is None:
            partial.append("The season is in recovery but no active recovery record is stored.")
        accepted_count = run.accepted_count if run else 0
        transcript_href = None
        if run is not None:
            transcript_href = "/api/v2/live/transcript?" + urlencode(
                {"season_id": selected_id, "run_id": run.run_id}
            )
        controls = [
            LiveControl(
                action="pause", available=lifecycle.status == "RUNNING",
                disabled_reason=None if lifecycle.status == "RUNNING" else "Pause is available only while the season is running.",
                review_href=("/api/v2/live/impact-review?" + urlencode({"season_id": selected_id, "action": "pause"})) if lifecycle.status == "RUNNING" else None,
            ),
            LiveControl(
                action="resume", available=lifecycle.status == "PAUSED",
                disabled_reason=None if lifecycle.status == "PAUSED" else "Resume is available only while the season is paused.",
                review_href=("/api/v2/live/impact-review?" + urlencode({"season_id": selected_id, "action": "resume"})) if lifecycle.status == "PAUSED" else None,
            ),
        ]
        data = LiveData(
            state="ready", context=context, lifecycle=lifecycle, run=run,
            worker=self._worker(), active_work=active_work, queued_work=queued_work,
            last_accepted_beat=last_beat, transcript_href=transcript_href,
            transcript_accepted_count=accepted_count,
            day_completion=self._day_completion(selected_id), recovery=recovery,
            controls=controls,
            next_direction=(
                "Resolve the recorded recovery before later queue work can proceed."
                if recovery else
                ("The current lease owns execution; closing this dashboard does not affect it."
                 if active_work else "The durable queue will advance when due work is claimed.")
            ),
            partial_reasons=partial,
        )
        freshness = Freshness.PARTIAL if partial else Freshness.FRESH
        return DashboardEnvelope(meta=self._meta(lifecycle, freshness), data=data.model_dump(mode="json"))

    def live_transcript(self, season_id: str, *, run_id: str) -> DashboardEnvelope:
        """Deliberately open one immutable accepted transcript snapshot."""
        context = self._context(season_id)
        lifecycle = self._selected(context)
        row = self.connection.execute(
            "SELECT r.*, s.run_number, s.day_number, s.slot_number, s.scheduled_local, s.scheduled_utc "
            "FROM runs r JOIN schedule_slots s ON s.slot_id = r.slot_id "
            "WHERE r.season_id = ? AND r.run_id = ?",
            (season_id, run_id),
        ).fetchone()
        if row is None:
            raise DashboardNotFound("selected live run does not exist")
        cast_names = {
            str(item["character_id"]): str(item["name"])
            for item in self.connection.execute(
                "SELECT character_id, name FROM cast_members WHERE season_id = ?", (season_id,)
            )
        }
        reviewed = self._review_run(row, cast_names, selected_run_id=run_id)
        data = LiveTranscriptData(
            season_id=season_id, run_id=run_id, run_version=int(row["version"]),
            accepted_count=len(reviewed.records), records=reviewed.records,
        )
        return DashboardEnvelope(meta=self._meta(lifecycle, Freshness.FRESH), data=data.model_dump(mode="json"))

    def _live_run_row(self, season_id: str):
        return self.connection.execute(
            "SELECT r.*, s.run_number, s.day_number, s.slot_number, s.scheduled_local, s.scheduled_utc "
            "FROM runs r JOIN schedule_slots s ON s.slot_id = r.slot_id WHERE r.season_id = ? "
            "ORDER BY CASE r.status WHEN 'RECOVERY_REQUIRED' THEN 0 WHEN 'RUNNING' THEN 1 "
            "WHEN 'WAITING_FOR_MODEL' THEN 2 WHEN 'QUEUED' THEN 3 ELSE 4 END, s.run_number LIMIT 1",
            (season_id,),
        ).fetchone()

    def _live_run(self, row) -> LiveRunState:
        call = self.connection.execute(
            "SELECT * FROM model_calls WHERE run_id = ? ORDER BY CASE status WHEN 'STREAMING' THEN 0 "
            "WHEN 'STARTED' THEN 1 ELSE 2 END, attempt DESC, started_at DESC LIMIT 1",
            (str(row["run_id"]),),
        ).fetchone()
        accepted = self.connection.execute(
            "SELECT COUNT(*) AS count, COUNT(DISTINCT round_number) AS rounds FROM turns "
            "WHERE run_id = ? AND disposition IN ('ACCEPT','ACCEPT_AFTER_CORRECTION','NARRATION_ACCEPT','NEUTRAL_INTERRUPTION')",
            (str(row["run_id"]),),
        ).fetchone()
        started = _parse_optional_datetime(row["actual_started_at"])
        elapsed = max(0, int((self.now - started).total_seconds())) if started else None
        call_progress = LiveCallProgress()
        if call is not None:
            call_id = str(call["call_id"])
            call_progress = LiveCallProgress(
                call_id=call_id, purpose=str(call["purpose"]),
                character_id=str(call["character_id"]) if call["character_id"] else None,
                attempt=int(call["attempt"]), status=str(call["status"]),
                started_at=_parse_optional_datetime(call["started_at"]),
                detail_href=f"/v2/diagnostics?{urlencode({'season_id': str(row['season_id']), 'call_id': call_id})}",
            )
        purpose = str(call["purpose"]) if call is not None else {
            "RECOVERY_REQUIRED": "Awaiting creator recovery decision",
            "QUEUED": "Waiting in durable queue",
            "RUNNING": "Advancing accepted scene work",
        }.get(str(row["status"]), "No active model purpose stored")
        return LiveRunState(
            run_id=str(row["run_id"]), version=int(row["version"]), status=str(row["status"]),
            run_number=int(row["run_number"]), day_number=int(row["day_number"]),
            slot_number=int(row["slot_number"]), scheduled_local=_parse_datetime(str(row["scheduled_local"])),
            scheduled_utc=_parse_datetime(str(row["scheduled_utc"])), actual_started_at=started,
            elapsed_seconds=elapsed, delay=str(row["delay"]) if row["delay"] else None,
            accepted_count=int(accepted["count"] or 0), accepted_rounds=int(accepted["rounds"] or 0),
            active_purpose=purpose, call=call_progress,
        )

    @staticmethod
    def _live_work(row) -> LiveWorkItem:
        return LiveWorkItem(
            work_id=str(row["work_id"]), kind=str(row["kind"]), status=str(row["status"]),
            available_at=_parse_datetime(str(row["available_at"])),
            lease_owner=str(row["lease_owner"]) if row["lease_owner"] else None,
            lease_until=_parse_optional_datetime(row["lease_until"]), attempts=int(row["attempts"]),
            priority=int(row["priority"]),
        )

    def _live_recovery(self, season_id: str, run_row) -> LiveRecoveryState | None:
        row = self.connection.execute(
            "SELECT * FROM recovery_requests WHERE season_id = ? AND status IN "
            "('RECOVERY_REQUIRED','WAITING_FOR_MODEL') ORDER BY created_at DESC LIMIT 1",
            (season_id,),
        ).fetchone()
        if row is None:
            return None
        failed = self.connection.execute(
            "SELECT call_id, error_type FROM model_calls WHERE run_id = ? AND status NOT IN "
            "('ACCEPTED','RENDERED') ORDER BY ended_at DESC, started_at DESC LIMIT 1",
            (str(row["run_id"]),),
        ).fetchone()
        call_id = str(failed["call_id"]) if failed is not None else None
        beat, _ = self._last_accepted_beat(season_id)
        anchor = beat.receipt or "No accepted causal anchor is stored."
        reason = (
            str(run_row["completion_reason"])
            if run_row is not None and str(run_row["run_id"]) == str(row["run_id"]) and run_row["completion_reason"]
            else (str(failed["error_type"]) if failed is not None and failed["error_type"] else "Recorded model failure")
        )
        return LiveRecoveryState(
            recovery_id=str(row["recovery_id"]), version=int(row["version"]),
            run_id=str(row["run_id"]), status=str(row["status"]), reason=reason,
            failed_call_id=call_id,
            failed_call_href=(f"/v2/diagnostics?{urlencode({'season_id': season_id, 'call_id': call_id})}" if call_id else None),
            queue_effect="Later scheduled work remains queued until this recovery is resolved.",
            last_accepted_anchor=anchor, actions=["retry", "skip", "private_close"],
        )

    def diary_attempt(
        self, season_id: str | None, *, diary_id: str
    ) -> DashboardEnvelope:
        """Deliberately disclose one diary text projection without mutating state."""
        context = self._context(season_id)
        lifecycle = self._selected(context)
        if lifecycle is None:
            raise DashboardNotFound("selected season does not exist")
        row = self.connection.execute(
            "SELECT d.*, c.name AS character_name FROM diaries d "
            "LEFT JOIN cast_members c ON c.season_id = d.season_id "
            "AND c.character_id = d.character_id "
            "WHERE d.diary_id = ? AND d.season_id = ?",
            (diary_id, lifecycle.season_id),
        ).fetchone()
        if row is None:
            raise DashboardNotFound("diary does not belong to the selected season")

        source: Literal["accepted_diary", "private_attempt", "no_content", "unavailable"]
        content: str | None = None
        wellness_signal_present = False
        attempt_number: int | None = None
        evidence_note: str
        if row["content_path"]:
            content = self._private_text(str(row["content_path"]))
            if content is None:
                source = "unavailable"
                evidence_note = "The accepted diary artifact is outside readable private storage."
            else:
                source = "accepted_diary"
                evidence_note = "Read from the accepted private diary artifact."
        else:
            attempt = self._latest_diary_attempt(row)
            if attempt is None:
                source = "no_content"
                evidence_note = "No accepted diary text or readable private attempt is stored."
            else:
                attempt_number = int(attempt["attempt"])
                raw_output = self._private_text(str(attempt["output_path"]))
                if raw_output is None:
                    source = "unavailable"
                    evidence_note = "The private attempt is outside readable private storage."
                else:
                    try:
                        envelope = parse_diary_output(raw_output)
                    except StructuredOutputError:
                        source = "unavailable"
                        evidence_note = (
                            "A private attempt exists, but its diary text cannot be safely "
                            "separated from the raw response envelope."
                        )
                    else:
                        source = "private_attempt"
                        content = envelope.text.strip() or None
                        wellness_signal_present = bool(envelope.wellness_signal)
                        evidence_note = (
                            "Diary text was safely separated from a held private attempt; "
                            "wellness wording remains undisclosed."
                            if wellness_signal_present
                            else "Diary text was safely separated from a private attempt."
                        )

        disclosure = DiaryAttemptDisclosure(
            diary_id=str(row["diary_id"]),
            season_id=str(row["season_id"]),
            character_id=str(row["character_id"]),
            character_name=str(row["character_name"] or row["character_id"]),
            day_number=int(row["day_number"]),
            status=str(row["status"]),
            source=source,
            content=content,
            wellness_signal_present=wellness_signal_present,
            attempt_number=attempt_number,
            evidence_note=evidence_note,
        )
        freshness = Freshness.PARTIAL if source == "unavailable" else Freshness.FRESH
        return DashboardEnvelope(
            meta=self._meta(lifecycle, freshness),
            data=disclosure.model_dump(mode="json"),
        )

    def diagnostics(
        self,
        season_id: str | None = None,
        *,
        call_id: str | None = None,
        run_id: str | None = None,
        character_id: str | None = None,
        purpose: str | None = None,
        status: str | None = None,
        attempt: int | None = None,
        error: str | None = None,
    ) -> DashboardEnvelope:
        """Explain stored call evidence without reading raw private output."""
        context = self._context(season_id)
        lifecycle = self._selected(context)
        filters: dict[str, str | int | None] = {
            "call_id": call_id, "run_id": run_id, "character_id": character_id,
            "purpose": purpose, "status": status, "attempt": attempt, "error": error,
        }
        if lifecycle is None:
            data = DiagnosticsData(
                state="no_season", context=context, calls=[], selected_call=None,
                filters=filters, excluded_private_attempt_count=0, partial_reasons=[],
            )
            return DashboardEnvelope(
                meta=self._meta(None, Freshness.FRESH), data=data.model_dump(mode="json")
            )

        clauses = ["r.season_id = ?", "mc.run_id IS NOT NULL"]
        parameters: list[object] = [lifecycle.season_id]
        for column, value in (
            ("mc.run_id", run_id), ("mc.character_id", character_id),
            ("mc.purpose", purpose), ("mc.status", status),
            ("mc.attempt", attempt), ("mc.error_type", error),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                parameters.append(value)
        rows = self.connection.execute(
            "SELECT mc.*, s.day_number, s.slot_number, s.run_number "
            "FROM model_calls mc JOIN runs r ON r.run_id = mc.run_id "
            "JOIN schedule_slots s ON s.slot_id = r.slot_id "
            f"WHERE {' AND '.join(clauses)} ORDER BY mc.started_at DESC, mc.call_id DESC",
            tuple(parameters),
        ).fetchall()
        if call_id is not None and not any(str(row["call_id"]) == call_id for row in rows):
            raise DashboardNotFound("selected call does not belong to the filtered season evidence")
        selected_id = call_id or (str(rows[0]["call_id"]) if rows else None)
        selected_row = next((row for row in rows if str(row["call_id"]) == selected_id), None)
        partial_reasons: list[str] = []
        if selected_row is not None and selected_row["response_format_mode"] is None:
            partial_reasons.append(
                "Legacy call provenance is unavailable; Diagnostics does not infer a response format."
            )
        excluded = int(self.connection.execute(
            "SELECT COUNT(*) FROM model_calls WHERE run_id IS NULL "
            "AND (call_id LIKE ? OR purpose LIKE ? OR purpose LIKE ?)",
            (f"{lifecycle.season_id}:%", f"diary:{lifecycle.season_id}:%", f"orientation:{lifecycle.season_id}:%"),
        ).fetchone()[0])
        data = DiagnosticsData(
            state="ready" if rows else "empty", context=context,
            calls=[self._diagnostics_summary(row, selected_id, lifecycle.season_id) for row in rows],
            selected_call=(self._diagnostics_detail(selected_row, lifecycle.season_id) if selected_row is not None else None),
            filters=filters, excluded_private_attempt_count=excluded,
            partial_reasons=partial_reasons,
        )
        freshness = Freshness.PARTIAL if partial_reasons else Freshness.FRESH
        return DashboardEnvelope(
            meta=self._meta(lifecycle, freshness), data=data.model_dump(mode="json")
        )

    def call_raw(self, season_id: str | None, *, call_id: str) -> DashboardEnvelope:
        """Deliberately disclose one non-wellness raw call artifact."""
        context = self._context(season_id)
        lifecycle = self._selected(context)
        if lifecycle is None:
            raise DashboardNotFound("selected season does not exist")
        row = self.connection.execute(
            "SELECT mc.* FROM model_calls mc JOIN runs r ON r.run_id = mc.run_id "
            "WHERE mc.call_id = ? AND r.season_id = ?",
            (call_id, lifecycle.season_id),
        ).fetchone()
        if row is None:
            raise DashboardNotFound("call does not belong to the selected season")
        content = self._private_text(str(row["output_path"] or ""))
        if content is None or self._contains_wellness_signal(content):
            raise DashboardNotFound("raw call evidence is unavailable through Diagnostics")
        payload = CallRawDisclosure(
            call_id=call_id, season_id=lifecycle.season_id, content=content,
            evidence_note="Owner-requested raw artifact read; no state was changed.",
        )
        return DashboardEnvelope(
            meta=self._meta(lifecycle, Freshness.FRESH), data=payload.model_dump(mode="json")
        )

    def _diagnostics_summary(
        self, row, selected_id: str | None, season_id: str
    ) -> DiagnosticsCallSummary:
        query = urlencode({"season_id": season_id, "call_id": str(row["call_id"])})
        return DiagnosticsCallSummary(
            call_id=str(row["call_id"]), run_id=str(row["run_id"]) if row["run_id"] else None,
            character_id=str(row["character_id"]) if row["character_id"] else None,
            purpose=str(row["purpose"]), attempt=int(row["attempt"]), status=str(row["status"]),
            error_type=str(row["error_type"]) if row["error_type"] else None,
            response_format_mode=str(row["response_format_mode"]) if row["response_format_mode"] else None,
            started_at=_parse_optional_datetime(row["started_at"]),
            ended_at=_parse_optional_datetime(row["ended_at"]),
            latency_ms=int(row["latency_ms"]) if row["latency_ms"] is not None else None,
            selected=str(row["call_id"]) == selected_id,
            detail_href=f"/v2/diagnostics?{query}",
        )

    def _diagnostics_detail(self, row, season_id: str) -> DiagnosticsCallDetail:
        raw = self._private_text(str(row["output_path"] or ""))
        raw_allowed = raw is not None and not self._contains_wellness_signal(raw)
        stages = [DiagnosticsStage(
            stage="raw", state="available" if raw_allowed else "unavailable",
            summary=("Raw private output is stored behind deliberate disclosure."
                     if raw_allowed else "No safely disclosable raw artifact is available."),
        )]
        for name, column, path_column in (
            ("parsed", "parse_status", "parsed_path"),
            ("validated", "validation_status", "validated_path"),
            ("accepted", "acceptance_status", "accepted_path"),
            ("rendered", "render_status", "rendered_path"),
        ):
            stored = str(row[column]).upper() if row[column] else "UNAVAILABLE"
            content = None
            if name in {"accepted", "rendered"} and row[path_column]:
                content = self._private_text(str(row[path_column]))
            stages.append(DiagnosticsStage(
                stage=name, state=self._diagnostic_stage_state(stored),
                summary=self._diagnostic_stage_summary(name, stored), content=content,
            ))
        usage: dict[str, object] = {}
        if row["usage_json"]:
            try:
                decoded = json.loads(str(row["usage_json"]))
                if isinstance(decoded, dict): usage = decoded
            except (TypeError, ValueError):
                pass
        review_href, review_position = self._diagnostics_review_link(row, season_id)
        corrections = self.connection.execute(
            "SELECT call_id FROM model_calls WHERE correction_of_call_id = ? ORDER BY attempt, call_id",
            (str(row["call_id"]),),
        ).fetchall()
        raw_href = None
        if raw_allowed:
            raw_href = "/api/v2/diagnostics/call-raw?" + urlencode(
                {"season_id": season_id, "call_id": str(row["call_id"])}
            )
        provenance = DiagnosticsProvenance(**{
            field: (str(row[field]) if row[field] else None) for field in (
                "prompt_version_id", "schema_version_id", "context_version_id",
                "role_sheet_version_id", "character_card_version_id",
            )
        })
        total_tokens = usage.get("total_tokens")
        return DiagnosticsCallDetail(
            call_id=str(row["call_id"]), run_id=str(row["run_id"]) if row["run_id"] else None,
            character_id=str(row["character_id"]) if row["character_id"] else None,
            purpose=str(row["purpose"]), attempt=int(row["attempt"]),
            backend=str(row["backend"]) if row["backend"] else None,
            model=str(row["model"]) if row["model"] else None, status=str(row["status"]),
            response_format_mode=str(row["response_format_mode"]) if row["response_format_mode"] else None,
            started_at=_parse_optional_datetime(row["started_at"]),
            ended_at=_parse_optional_datetime(row["ended_at"]),
            latency_ms=int(row["latency_ms"]) if row["latency_ms"] is not None else None,
            finish_reason=str(row["finish_reason"]) if row["finish_reason"] else None,
            cancelled=bool(row["cancelled"]),
            error_type=str(row["error_type"]) if row["error_type"] else None,
            total_tokens=int(total_tokens) if isinstance(total_tokens, (int, float)) else None,
            stages=stages, validator_code=str(row["validator_code"]) if row["validator_code"] else None,
            validator_detail=str(row["validator_detail"]) if row["validator_detail"] else None,
            correction_of_call_id=str(row["correction_of_call_id"]) if row["correction_of_call_id"] else None,
            correction_call_ids=[str(item["call_id"]) for item in corrections], provenance=provenance,
            raw_disclosure_href=raw_href, review_href=review_href, review_position=review_position,
        )

    @staticmethod
    def _diagnostic_stage_state(stored: str):
        if stored in {"AVAILABLE", "PARSED"}: return "available"
        if stored in {"PASSED", "VALID"}: return "passed"
        if stored == "ACCEPTED": return "accepted"
        if stored == "RENDERED": return "rendered"
        if stored in {"FAILED", "INVALID"}: return "failed"
        if stored in {"ABSENT", "REJECTED", "NOT_REACHED", "NOT_RENDERED"}: return "absent"
        return "unavailable"

    @staticmethod
    def _diagnostic_stage_summary(name: str, stored: str) -> str:
        if stored == "UNAVAILABLE":
            return f"{name.capitalize()} evidence was not recorded for this call."
        return f"Stored {name} state: {stored.lower().replace('_', ' ')}."

    def _diagnostics_review_link(self, row, season_id: str) -> tuple[str | None, str]:
        turn_id = row["review_turn_id"]
        if not turn_id:
            return None, "No exact accepted Review position is stored for this call."
        turn = self.connection.execute(
            "SELECT t.accepted_sequence, r.run_id, s.day_number FROM turns t "
            "JOIN runs r ON r.run_id = t.run_id JOIN schedule_slots s ON s.slot_id = r.slot_id "
            "WHERE t.turn_id = ? AND r.season_id = ?", (turn_id, season_id),
        ).fetchone()
        if turn is None:
            return None, "The stored Review link no longer resolves to accepted evidence."
        query = urlencode({
            "season_id": season_id, "day": int(turn["day_number"]),
            "run_id": str(turn["run_id"]), "tab": "script", "turn_id": str(turn_id),
        })
        sequence = turn["accepted_sequence"]
        position = (f"Return to accepted #{int(sequence)}." if sequence is not None
                    else "Return to the stored accepted turn; sequence is legacy-derived.")
        return f"/v2/review?{query}", position

    @staticmethod
    def _contains_wellness_signal(content: str) -> bool:
        if "<WELLNESS_SIGNAL>" in content.upper():
            return True
        try:
            decoded = json.loads(content)
        except (TypeError, ValueError):
            return False
        return isinstance(decoded, dict) and bool(decoded.get("wellness_signal"))

    def _review_day_number(self, season_id: str, requested: int | None) -> int:
        if requested is not None:
            if requested not in range(1, 8):
                raise DashboardNotFound("selected day must be from 1 through 7")
            return requested
        row = self.connection.execute(
            "SELECT MAX(day_number) AS day_number FROM ("
            "SELECT day_number FROM schedule_slots WHERE season_id = ? "
            "UNION SELECT day_number FROM days WHERE season_id = ?)",
            (season_id, season_id),
        ).fetchone()
        return int(row["day_number"] or 1)

    def _review_day_state(
        self, season_id: str, day_number: int
    ) -> tuple[ReviewDayState, list[str]]:
        schedule = self.connection.execute(
            "SELECT COUNT(s.slot_id) AS scheduled, "
            "SUM(CASE WHEN r.status IN ('COMPLETED', 'SKIPPED') THEN 1 ELSE 0 END) AS resolved "
            "FROM schedule_slots s LEFT JOIN runs r ON r.slot_id = s.slot_id "
            "WHERE s.season_id = ? AND s.day_number = ?",
            (season_id, day_number),
        ).fetchone()
        scheduled = int(schedule["scheduled"] or 0)
        resolved = int(schedule["resolved"] or 0)
        row = self.connection.execute(
            "SELECT original_date, cutoff_at, closed FROM days "
            "WHERE season_id = ? AND day_number = ?",
            (season_id, day_number),
        ).fetchone()
        notes: list[str] = []
        if row is None:
            state: Literal["confirmed", "partial", "unavailable"] = (
                "partial" if scheduled else "unavailable"
            )
            notes.append(
                "Scheduled runs exist without a durable day-close record."
                if scheduled
                else "No durable schedule or day-close record exists for this day."
            )
            original_date = None
            cutoff_at = None
            closed = False
        else:
            state = "confirmed"
            original_date = str(row["original_date"])
            cutoff_at = _parse_optional_datetime(row["cutoff_at"])
            closed = bool(row["closed"])
        if closed and resolved < scheduled:
            state = "partial"
            notes.append(
                "The day is marked closed while one or more scheduled runs remain unresolved."
            )
        return (
            ReviewDayState(
                day_number=day_number,
                original_date=original_date,
                cutoff_at=cutoff_at,
                closed=closed,
                scheduled_runs=scheduled,
                resolved_runs=resolved,
                evidence_state=state,
                evidence_notes=notes,
            ),
            notes,
        )

    def _review_run(
        self,
        row,
        cast_names: dict[str, str],
        *,
        selected_run_id: str | None,
    ) -> ReviewRunSummary:
        run_id = str(row["run_id"])
        ordered, order_evidence, order_explanation = self._causal_turn_rows(run_id)
        records: list[AcceptedStoryRecord] = []
        evidence_notes: list[str] = []
        for turn, display_sequence, inferred_parent in ordered:
            disposition = str(turn["disposition"])
            if disposition == "NARRATION_ACCEPT":
                kind = "director_beat"
                character_id = None
                speaker_name = "Director"
            elif disposition == "NEUTRAL_INTERRUPTION":
                kind = "neutral_interruption"
                character_id = str(turn["character_id"])
                speaker_name = "Director interruption"
            else:
                kind = "actor_turn"
                character_id = str(turn["character_id"])
                speaker_name = cast_names.get(character_id, character_id)
            content = (
                self._private_text(str(turn["content_path"]))
                if turn["content_path"]
                else None
            )
            if content is None:
                evidence_state = "unavailable"
                evidence_note = "Accepted text is missing or unreadable inside private storage."
                evidence_notes.append(f"{turn['turn_id']}: {evidence_note}")
            elif order_evidence == "derived":
                evidence_state = "partial"
                evidence_note = "Text is accepted; its displayed causal position is derived."
            else:
                evidence_state = "confirmed"
                evidence_note = None
            records.append(
                AcceptedStoryRecord(
                    turn_id=str(turn["turn_id"]),
                    accepted_sequence=display_sequence,
                    sequence_source=order_evidence,
                    caused_by_turn_id=(
                        str(turn["caused_by_turn_id"])
                        if turn["caused_by_turn_id"] is not None
                        else inferred_parent
                    ),
                    round_number=int(turn["round_number"]),
                    kind=kind,
                    character_id=character_id,
                    speaker_name=speaker_name,
                    disposition=disposition,
                    content=content,
                    accepted_at=_parse_optional_datetime(turn["accepted_at"]),
                    evidence_state=evidence_state,
                    evidence_note=evidence_note,
                )
            )
        if order_evidence == "derived":
            evidence_notes.append(
                "Accepted order is derived because complete causal fields are not stored for this run."
            )

        status = str(row["status"])
        stored_reason = str(row["completion_reason"] or "").strip()
        if status == "COMPLETED":
            if stored_reason:
                completion_reason = stored_reason
                completion_evidence = "confirmed"
            else:
                completion_reason = "unavailable"
                completion_evidence = "partial"
                evidence_notes.append("Completed run has no stored completion reason.")
        elif stored_reason:
            completion_reason = stored_reason
            completion_evidence = "confirmed"
        elif status in {"RECOVERY_REQUIRED", "INTERRUPTED", "FAILED"}:
            completion_reason = "unavailable"
            completion_evidence = "partial"
            evidence_notes.append(f"{status.lower()} run has no stored reason.")
        else:
            completion_reason = "run_not_completed"
            completion_evidence = "not_applicable"

        actor_turn_count = sum(record.kind == "actor_turn" for record in records)
        stored_actor_turn_count = int(row["turn_count"] or 0)
        if stored_actor_turn_count != actor_turn_count:
            evidence_notes.append(
                "Stored actor turn count does not match the accepted actor records currently readable."
            )
        evidence_notes = list(dict.fromkeys(evidence_notes))
        slot_number = int(row["slot_number"])
        day_number = self._run_day_number(run_id)
        period = {1: "morning", 2: "afternoon", 3: "evening"}[slot_number]
        return ReviewRunSummary(
            run_id=run_id,
            run_number=int(row["run_number"]),
            slot_number=slot_number,
            status=status,
            selected=run_id == selected_run_id,
            scheduled_local=_parse_datetime(str(row["scheduled_local"])),
            scheduled_utc=_parse_datetime(str(row["scheduled_utc"])),
            actual_started_at=_parse_optional_datetime(row["actual_started_at"]),
            actual_completed_at=_parse_optional_datetime(row["actual_completed_at"]),
            delay=str(row["delay"]) if row["delay"] is not None else None,
            stored_actor_turn_count=stored_actor_turn_count,
            accepted_record_count=len(records),
            accepted_actor_turn_count=actor_turn_count,
            accepted_round_count=len({record.round_number for record in records}),
            completion_reason=completion_reason,
            completion_evidence=completion_evidence,
            order_evidence=order_evidence if records else "unavailable",
            order_explanation=order_explanation,
            fiction_clock=FictionClockFrame(
                label=f"Day {day_number}, {period}",
                day_number=day_number,
                slot_number=slot_number,
            ),
            records=records,
            evidence_notes=evidence_notes,
        )

    def _run_day_number(self, run_id: str) -> int:
        row = self.connection.execute(
            "SELECT s.day_number FROM runs r JOIN schedule_slots s ON s.slot_id = r.slot_id "
            "WHERE r.run_id = ?",
            (run_id,),
        ).fetchone()
        return int(row["day_number"]) if row is not None else 1

    def _causal_turn_rows(self, run_id: str):
        rows = self.connection.execute(
            "SELECT rowid AS insertion_order, * FROM turns WHERE run_id = ? "
            "AND disposition IN ('ACCEPT', 'ACCEPT_AFTER_CORRECTION', "
            "'NARRATION_ACCEPT', 'NEUTRAL_INTERRUPTION')",
            (run_id,),
        ).fetchall()
        if not rows:
            return [], "derived", "No accepted story record is stored for this run."
        turn_by_id = {str(row["turn_id"]): row for row in rows}
        persisted = all(row["accepted_sequence"] is not None for row in rows)
        if persisted:
            sequences = [int(row["accepted_sequence"]) for row in rows]
            persisted = len(sequences) == len(set(sequences))
        if persisted:
            for row in rows:
                if str(row["disposition"]) == "NARRATION_ACCEPT":
                    continue
                parent_id = row["caused_by_turn_id"]
                parent = turn_by_id.get(str(parent_id)) if parent_id else None
                if (
                    parent is None
                    or str(parent["disposition"]) != "NARRATION_ACCEPT"
                    or int(parent["round_number"]) != int(row["round_number"])
                    or int(parent["accepted_sequence"]) >= int(row["accepted_sequence"])
                ):
                    persisted = False
                    break
        if persisted:
            ordered = sorted(rows, key=lambda item: int(item["accepted_sequence"]))
            return (
                [(item, int(item["accepted_sequence"]), None) for item in ordered],
                "persisted",
                "Durable accepted sequence and cause links establish this reading order.",
            )

        ordered = sorted(
            rows,
            key=lambda item: (
                int(item["round_number"]),
                0 if str(item["disposition"]) == "NARRATION_ACCEPT" else 1,
                int(item["insertion_order"]),
            ),
        )
        director_by_round = {
            int(item["round_number"]): str(item["turn_id"])
            for item in ordered
            if str(item["disposition"]) == "NARRATION_ACCEPT"
        }
        return (
            [
                (
                    item,
                    index,
                    None
                    if str(item["disposition"]) == "NARRATION_ACCEPT"
                    else director_by_round.get(int(item["round_number"])),
                )
                for index, item in enumerate(ordered, start=1)
            ],
            "derived",
            "Legacy or incomplete evidence: order is derived by run, round, director beat, then durable insertion order.",
        )

    def _review_diaries(
        self, season_id: str, day_number: int, cast_names: dict[str, str]
    ) -> list[DiaryReviewSummary]:
        summaries: list[DiaryReviewSummary] = []
        for row in self.connection.execute(
            "SELECT * FROM diaries WHERE season_id = ? AND day_number = ? "
            "ORDER BY character_id",
            (season_id, day_number),
        ):
            content_available = bool(
                row["content_path"] and self._private_path_readable(str(row["content_path"]))
            )
            attempt = self._latest_diary_attempt(row)
            attempt_available = bool(
                attempt is not None
                and attempt["output_path"]
                and self._private_path_readable(str(attempt["output_path"]))
            )
            status = str(row["status"])
            evidence_state, note = {
                "WRITTEN": ("written", "Accepted private diary text is stored."),
                "PRIVATE": (
                    "held_private",
                    "A diary attempt is held private and is not accepted or publishable.",
                ),
                "LATE": ("late", "The diary is stored and marked late."),
                "MISSING": ("missing", "No diary entry was accepted before day close."),
                "EXPECTED": ("expected", "A diary obligation remains expected."),
            }.get(status, ("unavailable", "Diary status is not recognized by this review contract."))
            disclosure_href = None
            if content_available or attempt_available:
                disclosure_href = "/api/v2/review/diary-attempt?" + urlencode(
                    {"season_id": season_id, "diary_id": str(row["diary_id"])}
                )
            summaries.append(
                DiaryReviewSummary(
                    diary_id=str(row["diary_id"]),
                    character_id=str(row["character_id"]),
                    character_name=cast_names.get(
                        str(row["character_id"]), str(row["character_id"])
                    ),
                    status=status,
                    chosen_slot_number=(
                        int(row["chosen_slot_number"])
                        if row["chosen_slot_number"] is not None
                        else None
                    ),
                    late=bool(row["late"]),
                    word_count=int(row["word_count"]) if row["word_count"] is not None else None,
                    content_available=content_available,
                    attempt_available=attempt_available,
                    evidence_state=evidence_state,
                    evidence_note=note,
                    disclosure_href=disclosure_href,
                )
            )
        return summaries

    def _latest_diary_attempt(self, diary_row):
        return self.connection.execute(
            "SELECT attempt, output_path FROM model_calls "
            "WHERE run_id IS NULL AND purpose LIKE ? AND output_path IS NOT NULL "
            "ORDER BY attempt DESC, ended_at DESC LIMIT 1",
            (
                f"diary:{diary_row['season_id']}:{diary_row['character_id']}:"
                f"day:{diary_row['day_number']}:slot:%",
            ),
        ).fetchone()

    def _review_cast(
        self, season_id: str, day_number: int, run_id: str | None
    ) -> list[ReviewCastMember]:
        members: list[ReviewCastMember] = []
        for row in self.connection.execute(
            "SELECT character_id, name, status, memory_version FROM cast_members "
            "WHERE season_id = ? ORDER BY character_id",
            (season_id,),
        ):
            query: dict[str, str | int] = {
                "season_id": season_id,
                "day": day_number,
                "tab": "cast",
                "character_id": str(row["character_id"]),
            }
            if run_id:
                query["run_id"] = run_id
            card = self.connection.execute(
                "SELECT * FROM character_card_versions WHERE season_id = ? AND character_id = ? "
                "AND status = 'APPROVED' ORDER BY version DESC LIMIT 1",
                (season_id, str(row["character_id"])),
            ).fetchone()
            members.append(
                ReviewCastMember(
                    character_id=str(row["character_id"]),
                    name=str(row["name"]),
                    status=str(row["status"]),
                    memory_version=int(row["memory_version"] or 0),
                    memory_href=f"/v2/review?{urlencode(query)}",
                    character_card_version=int(card["version"]) if card is not None else None,
                    pronouns=str(card["pronouns"]) if card is not None else None,
                    public_brief=str(card["public_brief"]) if card is not None else None,
                    occupation_skills=(self._json_string_list(card["occupation_skills_json"]) if card is not None else []),
                    voice_anchors=(self._json_string_list(card["voice_anchors_json"]) if card is not None else []),
                    habits=(self._json_string_list(card["habits_json"]) if card is not None else []),
                )
            )
        return members

    def _continuity(self, season_id: str) -> ContinuitySummary:
        canon = [
            CanonReviewItem(
                canon_id=str(row["canon_id"]),
                version=int(row["version"]),
                claim=str(row["claim"]),
                status=str(row["status"]),
            )
            for row in self.connection.execute(
                "SELECT canon_id, version, claim, status FROM canon_entries "
                "WHERE season_id = ? ORDER BY version, canon_id",
                (season_id,),
            )
        ]
        return ContinuitySummary(
            canon=canon,
            unresolved_state="unavailable",
            unresolved_notes=[
                "No dedicated unresolved-continuity ledger is stored; the review does not infer one from private plans or role sheets."
            ],
        )

    def _private_path_readable(self, raw_path: str) -> bool:
        candidate = Path(raw_path).expanduser().resolve(strict=False)
        private_root = self.paths.roots.private.resolve(strict=False)
        try:
            candidate.relative_to(private_root)
        except ValueError:
            return False
        return candidate.is_file() and os.access(candidate, os.R_OK)

    def _private_text(self, raw_path: str) -> str | None:
        if not self._private_path_readable(raw_path):
            return None
        try:
            return Path(raw_path).expanduser().resolve(strict=False).read_text(
                encoding="utf-8"
            ).strip()
        except (OSError, UnicodeError):
            return None

    def _context(self, requested_season_id: str | None) -> DashboardContextData:
        rows = self.connection.execute(
            "SELECT season_id, title, status, version, updated_at "
            "FROM seasons ORDER BY season_number DESC, season_id DESC"
        ).fetchall()
        if requested_season_id and not any(
            str(row["season_id"]) == requested_season_id for row in rows
        ):
            raise DashboardNotFound("selected season does not exist")

        selected_id = requested_season_id
        if selected_id is None:
            active = next(
                (
                    str(row["season_id"])
                    for row in rows
                    if str(row["status"]) in ACTIVE_SEASON_STATUSES
                ),
                None,
            )
            selected_id = active or (str(rows[0]["season_id"]) if rows else None)

        seasons = [self._season(row, selected_id) for row in rows]
        return DashboardContextData(
            selected_season_id=selected_id,
            seasons=seasons,
            navigation=[
                NavigationItem(
                    destination=destination,
                    label=label,
                    href=_href(destination, selected_id),
                    implemented=implemented,
                )
                for destination, label, implemented in NAVIGATION
            ],
        )

    @staticmethod
    def _selected(context: DashboardContextData) -> SeasonSummary | None:
        return next((season for season in context.seasons if season.selected), None)

    def _meta(
        self,
        season: SeasonSummary | None,
        freshness: Freshness,
    ) -> DashboardMeta:
        return DashboardMeta(
            checked_at=self.now,
            environment=self.environment,
            season_id=season.season_id if season else None,
            season_version=season.version if season else None,
            freshness=freshness,
        )

    @staticmethod
    def _season(row, selected_id: str | None) -> SeasonSummary:
        season_id = str(row["season_id"])
        return SeasonSummary(
            season_id=season_id,
            title=str(row["title"]) if row["title"] is not None else None,
            status=str(row["status"]),
            version=int(row["version"]),
            updated_at=_parse_datetime(str(row["updated_at"])),
            selected=season_id == selected_id,
        )

    def _health(self) -> tuple[HealthSummary, list[str]]:
        integrity_value = str(
            self.connection.execute("PRAGMA integrity_check").fetchone()[0]
        )
        integrity = "ok" if integrity_value == "ok" else "not_ok"
        state_reachable = _readable_directory(self.paths.roots.state)
        private_reachable = _readable_directory(self.paths.roots.private)
        public_reachable = _readable_directory(self.paths.roots.public)
        pending = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM artifact_outbox WHERE status = 'PENDING'"
            ).fetchone()[0]
        )
        reasons: list[str] = []
        if integrity != "ok":
            reasons.append("Database integrity check did not return ok.")
        if not state_reachable:
            reasons.append("State storage could not be read.")
        if not private_reachable:
            reasons.append("Private storage could not be read.")
        if not public_reachable:
            reasons.append("Public storage could not be read.")
        return (
            HealthSummary(
                database_integrity=integrity,
                state_storage_reachable=state_reachable,
                private_storage_reachable=private_reachable,
                public_storage_reachable=public_reachable,
                artifact_outbox_pending=pending,
            ),
            reasons,
        )

    def _worker(self) -> WorkerSummary:
        now_text = self.now.isoformat()
        queue_total = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM work_items WHERE status = 'QUEUED'"
            ).fetchone()[0]
        )
        queue_due = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM work_items "
                "WHERE status = 'QUEUED' AND available_at <= ?",
                (now_text,),
            ).fetchone()[0]
        )
        active_leases = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM work_items "
                "WHERE status = 'LEASED' AND lease_until > ?",
                (now_text,),
            ).fetchone()[0]
        )
        expired_leases = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM work_items "
                "WHERE status = 'LEASED' AND (lease_until IS NULL OR lease_until <= ?)",
                (now_text,),
            ).fetchone()[0]
        )
        if active_leases:
            state = "active_lease"
            label = "Active lease observed"
        elif expired_leases:
            state = "expired_lease"
            label = "Expired lease observed"
        else:
            state = "no_active_lease"
            label = "No active lease observed"
        return WorkerSummary(
            state=state,
            label=label,
            queue_total=queue_total,
            queue_due=queue_due,
            active_leases=active_leases,
            expired_leases=expired_leases,
        )

    def _progress(self, season_id: str) -> RunProgress:
        row = self.connection.execute(
            "SELECT COUNT(s.slot_id) AS scheduled, "
            "SUM(CASE WHEN r.status IN ('COMPLETED', 'SKIPPED') THEN 1 ELSE 0 END) AS resolved, "
            "SUM(CASE WHEN r.status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed, "
            "SUM(CASE WHEN r.status = 'SKIPPED' THEN 1 ELSE 0 END) AS skipped, "
            "COUNT(DISTINCT s.day_number) AS days_scheduled "
            "FROM schedule_slots s LEFT JOIN runs r ON r.slot_id = s.slot_id "
            "WHERE s.season_id = ?",
            (season_id,),
        ).fetchone()
        scheduled = int(row["scheduled"] or 0)
        resolved = int(row["resolved"] or 0)
        days_closed = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM days WHERE season_id = ? AND closed = 1",
                (season_id,),
            ).fetchone()[0]
        )
        return RunProgress(
            scheduled=scheduled,
            resolved=resolved,
            completed=int(row["completed"] or 0),
            skipped=int(row["skipped"] or 0),
            unresolved=max(scheduled - resolved, 0),
            days_closed=days_closed,
            days_scheduled=int(row["days_scheduled"] or 0),
        )

    def _next_slot(self, season_id: str) -> NextSlot:
        row = self.connection.execute(
            "SELECT r.run_id, r.status, s.run_number, s.day_number, s.slot_number, "
            "s.scheduled_local, s.scheduled_utc "
            "FROM schedule_slots s LEFT JOIN runs r ON r.slot_id = s.slot_id "
            "WHERE s.season_id = ? AND (r.status IS NULL OR r.status NOT IN ('COMPLETED', 'SKIPPED')) "
            "ORDER BY s.run_number LIMIT 1",
            (season_id,),
        ).fetchone()
        if row is None:
            return NextSlot(available=False)
        return NextSlot(
            available=True,
            run_id=str(row["run_id"]) if row["run_id"] is not None else None,
            run_number=int(row["run_number"]),
            day_number=int(row["day_number"]),
            slot_number=int(row["slot_number"]),
            status=str(row["status"]) if row["status"] is not None else "NOT_CREATED",
            scheduled_local=_parse_datetime(str(row["scheduled_local"])),
            scheduled_utc=_parse_datetime(str(row["scheduled_utc"])),
        )

    def _day_completion(self, season_id: str) -> DayCompletion:
        day_rows = self.connection.execute(
            "SELECT s.day_number, COUNT(s.slot_id) AS scheduled, "
            "SUM(CASE WHEN r.status IN ('COMPLETED', 'SKIPPED') THEN 1 ELSE 0 END) AS resolved "
            "FROM schedule_slots s LEFT JOIN runs r ON r.slot_id = s.slot_id "
            "WHERE s.season_id = ? GROUP BY s.day_number ORDER BY s.day_number",
            (season_id,),
        ).fetchall()
        day_row = next(
            (
                row
                for row in day_rows
                if int(row["resolved"] or 0) < int(row["scheduled"] or 0)
            ),
            day_rows[-1] if day_rows else None,
        )
        if day_row is None:
            return DayCompletion(
                available=False,
                state="not_scheduled",
                complete=False,
                scheduled_runs=0,
                resolved_runs=0,
                diary_counts={},
            )
        day_number = int(day_row["day_number"])
        scheduled = int(day_row["scheduled"] or 0)
        resolved = int(day_row["resolved"] or 0)
        closed_row = self.connection.execute(
            "SELECT closed FROM days WHERE season_id = ? AND day_number = ?",
            (season_id, day_number),
        ).fetchone()
        closed = bool(closed_row["closed"]) if closed_row is not None else False
        if closed and resolved == scheduled:
            state = "closed"
            complete = True
        elif closed:
            state = "closed_with_unresolved"
            complete = False
        else:
            state = "open"
            complete = False
        diary_counts = {
            str(row["status"]): int(row["count"])
            for row in self.connection.execute(
                "SELECT status, COUNT(*) AS count FROM diaries "
                "WHERE season_id = ? AND day_number = ? GROUP BY status ORDER BY status",
                (season_id, day_number),
            )
        }
        return DayCompletion(
            available=True,
            day_number=day_number,
            state=state,
            complete=complete,
            scheduled_runs=scheduled,
            resolved_runs=resolved,
            diary_counts=diary_counts,
            review_href=_href("review", season_id, day=day_number),
        )

    def _last_accepted_beat(
        self, season_id: str
    ) -> tuple[LastAcceptedBeat, str | None]:
        run = self.connection.execute(
            "SELECT r.run_id, r.turn_count, s.run_number, s.day_number, s.slot_number "
            "FROM runs r JOIN schedule_slots s ON s.slot_id = r.slot_id "
            "WHERE r.season_id = ? AND EXISTS (SELECT 1 FROM turns t "
            "WHERE t.run_id = r.run_id AND t.disposition IN "
            "('ACCEPT', 'ACCEPT_AFTER_CORRECTION', 'NARRATION_ACCEPT', "
            "'NEUTRAL_INTERRUPTION')) ORDER BY s.run_number DESC LIMIT 1",
            (season_id,),
        ).fetchone()
        if run is None:
            return LastAcceptedBeat(available=False), None

        ordered, order_evidence, order_explanation = self._causal_turn_rows(
            str(run["run_id"])
        )
        if not ordered:
            return LastAcceptedBeat(available=False), None
        row = ordered[-1][0]

        excerpt = None
        reason = None
        if row["content_path"]:
            excerpt = self._private_excerpt(str(row["content_path"]))
            if excerpt is None:
                reason = "The latest accepted artifact could not be read inside private storage."
        return (
            LastAcceptedBeat(
                available=True,
                run_id=str(run["run_id"]),
                run_number=int(run["run_number"]),
                day_number=int(run["day_number"]),
                slot_number=int(run["slot_number"]),
                character_id=str(row["character_id"]),
                speaker_name=(
                    self._cast_name(season_id, str(row["character_id"]))
                ),
                round_number=int(row["round_number"]),
                turn_count=int(run["turn_count"]),
                receipt=str(row["turn_id"]),
                excerpt=excerpt,
                accepted_at=_parse_optional_datetime(row["accepted_at"]),
                evidence_basis=f"{order_evidence.capitalize()} order. {order_explanation}",
            ),
            reason,
        )

    def _cast_name(self, season_id: str, character_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT name FROM cast_members WHERE season_id = ? AND character_id = ?",
            (season_id, character_id),
        ).fetchone()
        return str(row["name"]) if row is not None else None

    def _private_excerpt(self, raw_path: str) -> str | None:
        candidate = Path(raw_path).expanduser().resolve(strict=False)
        private_root = self.paths.roots.private.resolve(strict=False)
        try:
            candidate.relative_to(private_root)
        except ValueError:
            return None
        try:
            text = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return None
        normalized = " ".join(text.split())
        if len(normalized) <= 360:
            return normalized
        return normalized[:357].rstrip() + "…"

    def _cast(self, season_id: str) -> list[CastSummary]:
        return [
            CastSummary(
                character_id=str(row["character_id"]),
                name=str(row["name"]),
                status=str(row["status"]),
            )
            for row in self.connection.execute(
                "SELECT character_id, name, status FROM cast_members "
                "WHERE season_id = ? ORDER BY character_id",
                (season_id,),
            )
        ]

    def _has_active_recovery(self, season_id: str) -> bool:
        return (
            self.connection.execute(
                "SELECT 1 FROM recovery_requests WHERE season_id = ? "
                "AND status IN ('WAITING_FOR_MODEL', 'RECOVERY_REQUIRED') LIMIT 1",
                (season_id,),
            ).fetchone()
            is not None
        )

    def _attention(self, season_id: str | None) -> AttentionSummary:
        items: list[AttentionItem] = []
        recovery_rows = (
            self.connection.execute(
                "SELECT status, run_id FROM recovery_requests WHERE season_id = ? "
                "AND status IN ('WAITING_FOR_MODEL', 'RECOVERY_REQUIRED') "
                "ORDER BY CASE status WHEN 'RECOVERY_REQUIRED' THEN 0 ELSE 1 END, created_at",
                (season_id,),
            ).fetchall()
            if season_id
            else []
        )
        active_recovery_statuses: set[str] = set()
        for row in recovery_rows:
            status = str(row["status"])
            active_recovery_statuses.add(status)
            if status == "RECOVERY_REQUIRED":
                kind = "recovery"
                title = "Recovery decision required"
                detail = f"{row['run_id']} is waiting for creator review."
            else:
                kind = "waiting_for_model"
                title = "Run is waiting for a model"
                detail = f"{row['run_id']} is inside its durable waiting window."
            items.append(
                AttentionItem(
                    kind=kind,
                    title=title,
                    detail=detail,
                    href=_href("live", season_id),
                )
            )

        notification_rows = (
            self.connection.execute(
                "SELECT kind FROM notifications WHERE read_at IS NULL "
                "AND (season_id = ? OR season_id IS NULL) ORDER BY created_at",
                (season_id,),
            )
            if season_id
            else self.connection.execute(
                "SELECT kind FROM notifications WHERE read_at IS NULL "
                "AND season_id IS NULL ORDER BY created_at"
            )
        )
        for row in notification_rows:
            if str(row["kind"]) in active_recovery_statuses:
                continue
            items.append(
                AttentionItem(
                    kind="notification",
                    title="Unread operator notification",
                    detail="A durable notification is waiting for review.",
                    href=_href("live", season_id),
                )
            )

        expired = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM work_items WHERE status = 'LEASED' "
                "AND (lease_until IS NULL OR lease_until <= ?)",
                (self.now.isoformat(),),
            ).fetchone()[0]
        )
        if expired:
            items.append(
                AttentionItem(
                    kind="expired_lease",
                    title="Expired worker lease observed",
                    detail=f"{expired} leased work item{'s' if expired != 1 else ''} expired.",
                    href=_href("diagnostics", season_id),
                )
            )
        return AttentionSummary(
            count=len(items),
            highest_priority=items[0] if items else None,
            remaining_count=max(len(items) - 1, 0),
        )

    @staticmethod
    def _summary(attention: AttentionSummary, partial_reasons: list[str]) -> HomeSummary:
        if partial_reasons:
            return HomeSummary(
                heading="Some durable evidence needs a closer look.",
                message=f"{len(partial_reasons)} snapshot condition{'s' if len(partial_reasons) != 1 else ''} could not be presented as complete.",
                tone="partial",
            )
        if attention.count:
            return HomeSummary(
                heading="Operator review is waiting.",
                message=f"{attention.count} durable item{'s' if attention.count != 1 else ''} currently need attention.",
                tone="attention",
            )
        return HomeSummary(
            heading="No unresolved operator item is stored.",
            message="Worker process health remains separate from queue and lease evidence.",
            tone="calm",
        )


def _href(destination: str, season_id: str | None, *, day: int | None = None) -> str:
    query: dict[str, str | int] = {}
    if season_id:
        query["season_id"] = season_id
    if day is not None:
        query["day"] = day
    suffix = f"?{urlencode(query)}" if query else ""
    return f"/v2/{destination}{suffix}"


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _aware(parsed)


def _parse_optional_datetime(value: object) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    return _parse_datetime(str(value))


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _readable_directory(path: Path) -> bool:
    return path.is_dir() and os.access(path, os.R_OK | os.X_OK)


__all__ = ["DashboardReadModels"]
