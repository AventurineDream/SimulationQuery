"""Versioned dashboard HTTP contracts shared by read and command slices."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class DashboardError(RuntimeError):
    """Raised for an invalid authenticated dashboard action."""


class DashboardNotFound(DashboardError):
    """Raised when a selected dashboard resource does not exist."""


class Freshness(str, Enum):
    FRESH = "fresh"
    STALE_READABLE = "stale_readable"
    DISCONNECTED = "disconnected"
    PARTIAL = "partial"


class DashboardMeta(BaseModel):
    """Shared evidence metadata for future `/api/v2` read responses."""

    model_config = ConfigDict(extra="forbid")

    contract_version: int = Field(default=1, frozen=True)
    checked_at: AwareDatetime
    environment: Literal["sandbox", "production"]
    season_id: str | None = None
    season_version: int | None = None
    freshness: Freshness


class DashboardEnvelope(BaseModel):
    """Stable outer shape for future versioned dashboard reads."""

    model_config = ConfigDict(extra="forbid")

    meta: DashboardMeta
    data: dict[str, Any]


class SeasonSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    season_id: str
    title: str | None
    status: str
    version: int
    updated_at: AwareDatetime
    selected: bool = False


class NavigationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination: Literal["home", "prepare", "live", "review", "diagnostics", "seasons"]
    label: str
    href: str
    implemented: bool


class DashboardContextData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_season_id: str | None
    seasons: list[SeasonSummary]
    navigation: list[NavigationItem]


class HomeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str
    message: str
    tone: Literal["calm", "attention", "partial", "empty"]


class AttentionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["recovery", "waiting_for_model", "expired_lease", "notification"]
    title: str
    detail: str
    href: str


class AttentionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=0)
    highest_priority: AttentionItem | None
    remaining_count: int = Field(ge=0)


class RunProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheduled: int = Field(ge=0)
    resolved: int = Field(ge=0)
    completed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    unresolved: int = Field(ge=0)
    days_closed: int = Field(ge=0)
    days_scheduled: int = Field(ge=0)


class LastAcceptedBeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    run_id: str | None = None
    run_number: int | None = None
    day_number: int | None = None
    slot_number: int | None = None
    character_id: str | None = None
    speaker_name: str | None = None
    round_number: int | None = None
    turn_count: int | None = None
    receipt: str | None = None
    excerpt: str | None = None
    accepted_at: AwareDatetime | None = None
    evidence_basis: str | None = None


class NextSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    run_id: str | None = None
    run_number: int | None = None
    day_number: int | None = None
    slot_number: int | None = None
    status: str | None = None
    scheduled_local: AwareDatetime | None = None
    scheduled_utc: AwareDatetime | None = None


class CastSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: str
    name: str
    status: str


class DayCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    day_number: int | None = None
    state: Literal["not_scheduled", "open", "closed", "closed_with_unresolved"]
    complete: bool
    scheduled_runs: int = Field(ge=0)
    resolved_runs: int = Field(ge=0)
    diary_counts: dict[str, int]
    review_href: str | None = None


class WorkerSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["active_lease", "expired_lease", "no_active_lease"]
    label: str
    queue_total: int = Field(ge=0)
    queue_due: int = Field(ge=0)
    active_leases: int = Field(ge=0)
    expired_leases: int = Field(ge=0)


class HealthSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database_integrity: str
    state_storage_reachable: bool
    private_storage_reachable: bool
    public_storage_reachable: bool
    artifact_outbox_pending: int = Field(ge=0)
    model_availability: Literal["not_probed"] = "not_probed"


class HomeData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["ready", "no_season"]
    context: DashboardContextData
    summary: HomeSummary
    lifecycle: SeasonSummary | None
    attention: AttentionSummary
    progress: RunProgress
    last_accepted_beat: LastAcceptedBeat
    next_slot: NextSlot
    cast: list[CastSummary]
    day_completion: DayCompletion
    worker: WorkerSummary
    health: HealthSummary
    recent_seasons: list[SeasonSummary]
    partial_reasons: list[str]


class ReviewDayState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day_number: int = Field(ge=1, le=7)
    original_date: str | None
    cutoff_at: AwareDatetime | None
    closed: bool
    scheduled_runs: int = Field(ge=0)
    resolved_runs: int = Field(ge=0)
    evidence_state: Literal["confirmed", "partial", "unavailable"]
    evidence_notes: list[str]


class FictionClockFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    day_number: int = Field(ge=1, le=7)
    slot_number: int = Field(ge=1, le=3)
    basis: Literal["schedule_derived"] = "schedule_derived"


class AcceptedStoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str
    accepted_sequence: int = Field(ge=1)
    sequence_source: Literal["persisted", "derived"]
    caused_by_turn_id: str | None
    round_number: int = Field(ge=1)
    kind: Literal["director_beat", "actor_turn", "neutral_interruption"]
    character_id: str | None
    speaker_name: str
    disposition: str
    content: str | None
    accepted_at: AwareDatetime | None
    evidence_state: Literal["confirmed", "partial", "unavailable"]
    evidence_note: str | None


class ReviewRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    run_number: int = Field(ge=1)
    slot_number: int = Field(ge=1, le=3)
    status: str
    selected: bool
    scheduled_local: AwareDatetime
    scheduled_utc: AwareDatetime
    actual_started_at: AwareDatetime | None
    actual_completed_at: AwareDatetime | None
    delay: str | None
    stored_actor_turn_count: int = Field(ge=0)
    accepted_record_count: int = Field(ge=0)
    accepted_actor_turn_count: int = Field(ge=0)
    accepted_round_count: int = Field(ge=0)
    completion_reason: str
    completion_evidence: Literal["confirmed", "partial", "not_applicable"]
    order_evidence: Literal["persisted", "derived", "unavailable"]
    order_explanation: str
    fiction_clock: FictionClockFrame
    records: list[AcceptedStoryRecord]
    evidence_notes: list[str]


class DiaryReviewSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diary_id: str
    character_id: str
    character_name: str
    status: str
    chosen_slot_number: int | None
    late: bool
    word_count: int | None
    content_available: bool
    attempt_available: bool
    evidence_state: Literal["written", "held_private", "late", "missing", "expected", "unavailable"]
    evidence_note: str
    disclosure_href: str | None


class ReviewCastMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: str
    name: str
    status: str
    memory_version: int = Field(ge=0)
    memory_href: str
    character_card_version: int | None
    pronouns: str | None
    public_brief: str | None
    occupation_skills: list[str]
    voice_anchors: list[str]
    habits: list[str]


class CanonReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canon_id: str
    version: int = Field(ge=1)
    claim: str
    status: str


class ContinuitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canon: list[CanonReviewItem]
    unresolved_state: Literal["available", "none_stored", "unavailable"]
    unresolved_notes: list[str]


class ReviewDayData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["ready", "no_season"]
    context: DashboardContextData
    day: ReviewDayState | None
    selected_run_id: str | None
    runs: list[ReviewRunSummary]
    diaries: list[DiaryReviewSummary]
    cast: list[ReviewCastMember]
    continuity: ContinuitySummary
    diary_counts: dict[str, int]
    accepted_record_count: int = Field(ge=0)
    partial_reasons: list[str]


class DiaryAttemptDisclosure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diary_id: str
    season_id: str
    character_id: str
    character_name: str
    day_number: int = Field(ge=1, le=7)
    status: str
    source: Literal["accepted_diary", "private_attempt", "no_content", "unavailable"]
    content: str | None
    wellness_signal_present: bool
    attempt_number: int | None
    evidence_note: str
    immutable_read: Literal[True] = True


class DiagnosticsCallSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    run_id: str | None
    character_id: str | None
    purpose: str
    attempt: int = Field(ge=1)
    status: str
    error_type: str | None
    response_format_mode: str | None
    started_at: AwareDatetime | None
    ended_at: AwareDatetime | None
    latency_ms: int | None
    selected: bool
    detail_href: str


class DiagnosticsStage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Literal["raw", "parsed", "validated", "accepted", "rendered"]
    state: Literal["available", "passed", "failed", "accepted", "rendered", "absent", "unavailable"]
    summary: str
    content: str | None = None


class DiagnosticsProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_version_id: str | None
    schema_version_id: str | None
    context_version_id: str | None
    role_sheet_version_id: str | None
    character_card_version_id: str | None


class DiagnosticsCallDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    run_id: str | None
    character_id: str | None
    purpose: str
    attempt: int = Field(ge=1)
    backend: str | None
    model: str | None
    status: str
    response_format_mode: str | None
    started_at: AwareDatetime | None
    ended_at: AwareDatetime | None
    latency_ms: int | None
    finish_reason: str | None
    cancelled: bool
    error_type: str | None
    total_tokens: int | None
    stages: list[DiagnosticsStage]
    validator_code: str | None
    validator_detail: str | None
    correction_of_call_id: str | None
    correction_call_ids: list[str]
    provenance: DiagnosticsProvenance
    raw_disclosure_href: str | None
    review_href: str | None
    review_position: str
    immutable_read: Literal[True] = True


class DiagnosticsData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["ready", "no_season", "empty"]
    context: DashboardContextData
    calls: list[DiagnosticsCallSummary]
    selected_call: DiagnosticsCallDetail | None
    filters: dict[str, str | int | None]
    excluded_private_attempt_count: int = Field(ge=0)
    partial_reasons: list[str]


class CallRawDisclosure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    season_id: str
    content: str
    evidence_note: str
    immutable_read: Literal[True] = True


class PreparationStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int = Field(ge=1, le=8)
    key: Literal["idea", "opening", "character_cards", "model_assignment", "preflight", "private_preparation", "schedule_preview", "green_review"]
    label: str
    status: Literal["approved", "complete", "ready", "ready_for_review", "blocked", "not_started"]
    detail: str
    selected: bool


class CharacterCardVersionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    pronouns: str
    public_brief: str
    occupation_skills: list[str]
    voice_anchors: list[str]
    habits: list[str]


class CharacterCardSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: str
    name: str
    version: int = Field(ge=1)
    status: str
    pronouns: str
    public_brief: str
    occupation_skills: list[str]
    voice_anchors: list[str]
    habits: list[str]
    derived_opening_version: int = Field(ge=1)
    created_at: AwareDatetime
    approved_at: AwareDatetime | None
    prior_versions: list[int]
    approved_truth: CharacterCardVersionSnapshot | None


class ModelAssignmentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    status: str
    manifest_name: str
    assignments: dict[str, str]
    automatic_selection: Literal[False] = False


class PreparationInvalidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    source_step: str
    source_version: int = Field(ge=1)
    invalidated_steps: list[str]
    reason: str
    created_at: AwareDatetime


class PrivatePreparationArtifactSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: str
    character_name: str
    artifact_kind: Literal["role_sheet", "orientation"]
    version: int = Field(ge=1)
    source_character_card_version: int = Field(ge=1)
    status: str
    disclosure_href: str


class PrivatePreparationDisclosure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    season_id: str
    character_id: str
    character_name: str
    artifact_kind: Literal["role_sheet", "orientation"]
    version: int = Field(ge=1)
    source_character_card_version: int = Field(ge=1)
    content: dict[str, Any]
    evidence_note: str
    immutable_read: Literal[True] = True


class PreparationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["ready", "no_season", "unavailable"]
    context: DashboardContextData
    workspace_version: int | None
    idea: str | None
    idea_version: int | None
    opening_version: int | None
    selected_step: str | None
    steps: list[PreparationStep]
    cards: list[CharacterCardSummary]
    selected_character_id: str | None
    model_assignment: ModelAssignmentSummary | None
    latest_receipts: dict[str, dict[str, Any]]
    invalidations: list[PreparationInvalidation]
    private_artifacts: list[PrivatePreparationArtifactSummary]
    production_state_unchanged: Literal[True] = True
    model_calls_performed: Literal[0] = 0
    partial_reasons: list[str]


class LiveCallProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str | None = None
    purpose: str | None = None
    character_id: str | None = None
    attempt: int | None = None
    status: str | None = None
    started_at: AwareDatetime | None = None
    detail_href: str | None = None


class LiveRunState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    version: int = Field(ge=0)
    status: str
    run_number: int = Field(ge=1)
    day_number: int = Field(ge=1, le=7)
    slot_number: int = Field(ge=1, le=3)
    scheduled_local: AwareDatetime
    scheduled_utc: AwareDatetime
    actual_started_at: AwareDatetime | None
    elapsed_seconds: int | None = Field(default=None, ge=0)
    delay: str | None
    accepted_count: int = Field(ge=0)
    accepted_rounds: int = Field(ge=0)
    active_purpose: str
    call: LiveCallProgress


class LiveWorkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_id: str
    kind: str
    status: str
    available_at: AwareDatetime
    lease_owner: str | None
    lease_until: AwareDatetime | None
    attempts: int = Field(ge=0)
    priority: int


class LiveRecoveryState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recovery_id: str
    version: int = Field(ge=1)
    run_id: str
    status: str
    reason: str
    failed_call_id: str | None
    failed_call_href: str | None
    queue_effect: str
    last_accepted_anchor: str
    actions: list[Literal["retry", "skip", "private_close"]]
    selected_action: None = None


class LiveControl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["pause", "resume"]
    available: bool
    disabled_reason: str | None
    review_href: str | None


class LiveData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["ready", "no_season"]
    context: DashboardContextData
    lifecycle: SeasonSummary | None
    run: LiveRunState | None
    worker: WorkerSummary
    active_work: LiveWorkItem | None
    queued_work: list[LiveWorkItem]
    last_accepted_beat: LastAcceptedBeat
    transcript_href: str | None
    transcript_accepted_count: int = Field(ge=0)
    day_completion: DayCompletion
    recovery: LiveRecoveryState | None
    controls: list[LiveControl]
    next_direction: str
    partial_reasons: list[str]


class LiveTranscriptData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    season_id: str
    run_id: str
    run_version: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    records: list[AcceptedStoryRecord]
    immutable_read: Literal[True] = True


__all__ = [
    "DashboardEnvelope",
    "DashboardError",
    "DashboardNotFound",
    "DashboardMeta",
    "DashboardContextData",
    "CastSummary",
    "CallRawDisclosure",
    "DiagnosticsData",
    "DiaryAttemptDisclosure",
    "HomeData",
    "Freshness",
    "PreparationData",
    "LiveData",
    "LiveTranscriptData",
    "PrivatePreparationDisclosure",
    "ReviewDayData",
    "SeasonSummary",
]
