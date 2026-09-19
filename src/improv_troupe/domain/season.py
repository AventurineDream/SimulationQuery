"""Pure season-domain models and pilot calendar/state rules.

This module intentionally does not import the filesystem, database, web layer,
or model clients.  It is a separate schema from the stable ProductionPlan v1
contract in :mod:`improv_troupe.domain.plan`.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .magic import MagicScores

SEASON_SCHEMA_VERSION = "1.0"
PACIFIC_TIMEZONE = "America/Los_Angeles"
PACIFIC = ZoneInfo(PACIFIC_TIMEZONE)
PILOT_DAYS = 7
PILOT_SLOTS_PER_DAY = 3
PILOT_RUNS = PILOT_DAYS * PILOT_SLOTS_PER_DAY
PILOT_SLOT_TIMES = (time(6, 0), time(12, 0), time(18, 0))
DIARY_CUTOFF_AFTER_RUN = timedelta(hours=2)


class DomainStateError(ValueError):
    """Raised when a domain transition or invariant is violated."""


class SeasonStatus(str, Enum):
    DRAFT = "DRAFT"
    AWAITING_GREEN = "AWAITING_GREEN"
    ARMED = "ARMED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    CLOSING = "CLOSING"
    PRIVATE_COMPLETE = "PRIVATE_COMPLETE"
    SEASON_COMPLETE = "SEASON_COMPLETE"
    AWAITING_PUBLISH_REVIEW = "AWAITING_PUBLISH_REVIEW"
    PUBLISHED = "PUBLISHED"


class RunStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_MODEL = "WAITING_FOR_MODEL"
    PAUSED = "PAUSED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    INTERRUPTED = "INTERRUPTED"


class ModelCallStatus(str, Enum):
    PENDING = "PENDING"
    STREAMING = "STREAMING"
    RAW_COMPLETE = "RAW_COMPLETE"
    VALIDATING = "VALIDATING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    WAITING_FOR_MODEL = "WAITING_FOR_MODEL"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class CastMemberStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DEPARTED = "DEPARTED"
    REPLACED = "REPLACED"


class DiaryStatus(str, Enum):
    EXPECTED = "EXPECTED"
    WRITTEN = "WRITTEN"
    LATE = "LATE"
    MISSING = "MISSING"
    PRIVATE = "PRIVATE"


class PublicationStatus(str, Enum):
    PRIVATE = "PRIVATE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CLEARED = "CLEARED"
    PUBLISHED = "PUBLISHED"


class RecoveryStatus(str, Enum):
    NONE = "NONE"
    WAITING_FOR_MODEL = "WAITING_FOR_MODEL"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    RETRY = "RETRY"
    SKIPPED = "SKIPPED"
    ENDED = "ENDED"


class OpeningSnapshot(BaseModel):
    """The complete creator-visible opening and nothing beyond it."""

    model_config = ConfigDict(extra="forbid")

    set: str
    setting: str
    cast: list[str] = Field(..., min_length=1)
    world_rules: list[str] = Field(default_factory=list)

    @field_validator("cast")
    @classmethod
    def _unique_cast(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("opening cast names must be unique")
        return value

    def creator_view(self) -> dict[str, object]:
        """Return the allowlisted opening payload for creator presentation."""
        return self.model_dump(mode="json")


class RoleSheet(BaseModel):
    """Private post-green information for one character."""

    model_config = ConfigDict(extra="forbid")

    character_id: str
    objectives: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)
    knowledge: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)
    magic: MagicScores = Field(default_factory=MagicScores)
    play_style: str = ""
    voice_guidance: str = ""
    version: int = Field(1, ge=1)


class ActorSheet(BaseModel):
    """Private performer identity, deliberately separate from a character."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    pronouns: str = Field(min_length=1)
    performance_contract: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)
    ensemble_approach: str = ""
    diary_approach: str = ""
    version: int = Field(1, ge=1)


class CastingAssignment(BaseModel):
    """Season-local casting of one performer as one fictional character."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str = Field(min_length=1)
    character_id: str = Field(min_length=1)


class CharacterCard(BaseModel):
    """Portable character identity, shaped after common character-card fields."""

    model_config = ConfigDict(extra="forbid")

    character_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    pronouns: str = Field(min_length=1)
    description: str = ""
    personality: str = ""
    scenario: str = ""
    first_mes: str = ""
    mes_example: str = ""
    creator_notes: str = ""
    system_prompt: str = ""
    post_history_instructions: str = ""
    alternate_greetings: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    creator: str = ""
    character_version: str = "1"
    extensions: dict[str, Any] = Field(default_factory=dict)


class WorldBookEntry(BaseModel):
    """One deterministic lore injection with explicit privacy boundaries."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    keys: list[str] = Field(default_factory=list)
    secondary_keys: list[str] = Field(default_factory=list)
    content: str = Field(min_length=1)
    enabled: bool = True
    constant: bool = False
    selective: bool = False
    case_sensitive: bool = False
    insertion_order: int = 100
    priority: int = 100
    position: str = "before_character"
    visibility: str = "SHARED"
    character_ids: list[str] = Field(default_factory=list)
    extensions: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _valid_world_book_entry(self) -> "WorldBookEntry":
        if self.position not in {"before_character", "after_character"}:
            raise ValueError("world-book position must be before_character or after_character")
        if self.visibility not in {"SHARED", "CHARACTER_PRIVATE", "DIRECTOR_ONLY"}:
            raise ValueError("invalid world-book visibility")
        if not self.constant and not self.keys:
            raise ValueError("non-constant world-book entries require activation keys")
        if self.visibility == "CHARACTER_PRIVATE" and not self.character_ids:
            raise ValueError("character-private world-book entries require character IDs")
        return self


class WorldBook(BaseModel):
    """A bounded, portable collection of world facts."""

    model_config = ConfigDict(extra="forbid")

    world_book_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    scan_depth: int = Field(8, ge=1, le=100)
    token_budget: int = Field(800, ge=1)
    recursive_scanning: bool = False
    entries: list[WorldBookEntry] = Field(default_factory=list)
    extensions: dict[str, Any] = Field(default_factory=dict)


class HiddenSeasonPlan(BaseModel):
    """Private orchestration material never included in an opening snapshot."""

    model_config = ConfigDict(extra="forbid")

    premise: str = ""
    planned_tensions: list[str] = Field(default_factory=list)
    hidden_mysteries: list[str] = Field(default_factory=list)
    role_sheets: list[RoleSheet] = Field(default_factory=list)
    version: int = Field(1, ge=1)


class CastMember(BaseModel):
    """Persistent character identity and season-local state."""

    model_config = ConfigDict(extra="forbid")

    character_id: str
    name: str
    status: CastMemberStatus = CastMemberStatus.ACTIVE
    role_sheet_version: int = Field(0, ge=0)
    memory_version: int = Field(0, ge=0)
    distress_signal_count: int = Field(0, ge=0)


class ScheduleSlot(BaseModel):
    """One immutable original schedule position."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slot_id: str
    season_id: str
    day_number: int = Field(..., ge=1, le=PILOT_DAYS)
    slot_number: int = Field(..., ge=1, le=PILOT_SLOTS_PER_DAY)
    run_number: int = Field(..., ge=1, le=PILOT_RUNS)
    scheduled_local: datetime
    scheduled_utc: datetime
    utc_offset: str

    def model_copy(
        self, *, update: Mapping[str, Any] | None = None, deep: bool = False
    ) -> "ScheduleSlot":
        """Copy through validation so immutable schedule metadata stays trustworthy."""
        data = self.model_dump()
        if update:
            data.update(update)
        return type(self).model_validate(data)

    @model_validator(mode="after")
    def _validate_timestamps(self) -> "ScheduleSlot":
        if self.scheduled_local.tzinfo is None or self.scheduled_local.utcoffset() is None:
            raise ValueError("scheduled_local must be timezone-aware")
        if self.scheduled_utc.tzinfo is None or self.scheduled_utc.utcoffset() is None:
            raise ValueError("scheduled_utc must be timezone-aware")
        pacific = self.scheduled_local.astimezone(PACIFIC)
        expected_time = PILOT_SLOT_TIMES[self.slot_number - 1]
        if pacific.time().replace(microsecond=0, tzinfo=None) != expected_time:
            raise ValueError("scheduled_local must match the slot's Pacific wall-clock time")
        if self.scheduled_local.utcoffset() != pacific.utcoffset():
            raise ValueError("scheduled_local must use the active Pacific UTC offset")
        if self.scheduled_local.astimezone(timezone.utc) != self.scheduled_utc.astimezone(
            timezone.utc
        ):
            raise ValueError("scheduled_local and scheduled_utc must represent the same instant")
        if self.utc_offset != _format_offset(self.scheduled_local.utcoffset()):
            raise ValueError("utc_offset must match scheduled_local")
        return self


class Day(BaseModel):
    """The three-run and diary-closure unit for one original local date."""

    model_config = ConfigDict(extra="forbid")

    season_id: str
    day_number: int = Field(..., ge=1, le=PILOT_DAYS)
    original_date: date
    run_ids: list[str] = Field(default_factory=list, max_length=PILOT_SLOTS_PER_DAY)
    diary_ids: list[str] = Field(default_factory=list)
    cutoff_at: datetime | None = None
    closed: bool = False


class Run(BaseModel):
    """Durable ledger identity for one scheduled shared scene."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    season_id: str
    slot_id: str
    status: RunStatus = RunStatus.SCHEDULED
    turn_count: int = Field(0, ge=0, le=16)
    completion_reason: str | None = None


class ModelCall(BaseModel):
    """Metadata and disposition for one immutable model-call attempt."""

    model_config = ConfigDict(extra="forbid")

    call_id: str
    run_id: str | None = None
    purpose: str
    attempt: int = Field(1, ge=1)
    status: ModelCallStatus = ModelCallStatus.PENDING
    backend: str | None = None
    model: str | None = None
    prompt_path: str | None = None
    output_path: str | None = None


class Diary(BaseModel):
    """One immutable first-attempt diary obligation/result."""

    model_config = ConfigDict(extra="forbid")

    diary_id: str
    season_id: str
    character_id: str
    day_number: int = Field(..., ge=1, le=PILOT_DAYS)
    chosen_slot_number: int | None = Field(None, ge=1, le=PILOT_SLOTS_PER_DAY)
    status: DiaryStatus = DiaryStatus.EXPECTED
    word_count: int | None = Field(None, ge=0)
    late: bool = False
    content_path: str | None = None


class Publication(BaseModel):
    """Season-qualified publication state."""

    model_config = ConfigDict(extra="forbid")

    publication_id: str
    season_id: str
    version: int = Field(1, ge=1)
    status: PublicationStatus = PublicationStatus.PRIVATE
    eligible_diary_ids: list[str] = Field(default_factory=list)
    output_path: str | None = None


class WellnessEvent(BaseModel):
    """Observational, private wellness evidence."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    season_id: str
    character_id: str
    context: str
    signal_number: int = Field(..., ge=1)
    observed_at: datetime
    intervention: str = ""


class RecoveryState(BaseModel):
    """Explicit recovery decision state for a blocked work item."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: RecoveryStatus = RecoveryStatus.NONE
    resolved_at: datetime | None = None
    decision: str | None = None


class Season(BaseModel):
    """Season aggregate without persistence or model dependencies."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SEASON_SCHEMA_VERSION
    season_id: str
    season_number: int = Field(..., ge=1)
    title: str | None = None
    start_date: date | None = None
    idea: str = ""
    preflight_passed: bool = False
    model_manifest: dict[str, Any] = Field(default_factory=dict)
    status: SeasonStatus = SeasonStatus.DRAFT
    opening: OpeningSnapshot | None = None
    private_plan: HiddenSeasonPlan | None = None
    actors: list[ActorSheet] = Field(default_factory=list)
    casting: list[CastingAssignment] = Field(default_factory=list)
    character_cards: list[CharacterCard] = Field(default_factory=list)
    world_books: list[WorldBook] = Field(default_factory=list)
    cast: list[CastMember] = Field(default_factory=list)
    schedule: list[ScheduleSlot] = Field(default_factory=list)
    auto_tap_out: bool = True
    version: int = Field(0, ge=0)

    @model_validator(mode="after")
    def _actor_casting_is_one_to_one(self) -> "Season":
        if not self.casting:
            return self
        actor_ids = [actor.actor_id for actor in self.actors]
        if len(actor_ids) != len(set(actor_ids)):
            raise ValueError("actor sheet IDs must be unique")
        assigned_actors = [assignment.actor_id for assignment in self.casting]
        assigned_characters = [assignment.character_id for assignment in self.casting]
        if len(assigned_actors) != len(set(assigned_actors)):
            raise ValueError("an actor may be cast only once per season")
        if len(assigned_characters) != len(set(assigned_characters)):
            raise ValueError("a character may be assigned only one actor")
        unknown_actors = set(assigned_actors) - set(actor_ids)
        unknown_characters = set(assigned_characters) - {
            member.character_id for member in self.cast
        }
        if unknown_actors or unknown_characters:
            raise ValueError("casting must reference declared actors and characters")
        if set(assigned_characters) != {member.character_id for member in self.cast}:
            raise ValueError("actor-aware seasons require one assignment per cast character")
        card_ids = [card.character_id for card in self.character_cards]
        if len(card_ids) != len(set(card_ids)):
            raise ValueError("character-card IDs must be unique")
        cast_ids = {member.character_id for member in self.cast}
        if set(card_ids) - cast_ids:
            raise ValueError("character cards must reference declared characters")
        for book in self.world_books:
            for entry in book.entries:
                if set(entry.character_ids) - cast_ids:
                    raise ValueError("world-book character IDs must reference declared characters")
        return self

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            SeasonStatus.SEASON_COMPLETE,
            SeasonStatus.PRIVATE_COMPLETE,
            SeasonStatus.AWAITING_PUBLISH_REVIEW,
            SeasonStatus.PUBLISHED,
        }


_SEASON_TRANSITIONS: dict[SeasonStatus, frozenset[SeasonStatus]] = {
    SeasonStatus.DRAFT: frozenset({SeasonStatus.AWAITING_GREEN}),
    SeasonStatus.AWAITING_GREEN: frozenset({SeasonStatus.ARMED}),
    SeasonStatus.ARMED: frozenset(
        {SeasonStatus.RUNNING, SeasonStatus.PAUSED, SeasonStatus.RECOVERY_REQUIRED, SeasonStatus.CLOSING}
    ),
    SeasonStatus.RUNNING: frozenset(
        {SeasonStatus.PAUSED, SeasonStatus.RECOVERY_REQUIRED, SeasonStatus.CLOSING}
    ),
    SeasonStatus.PAUSED: frozenset({SeasonStatus.RUNNING, SeasonStatus.CLOSING}),
    SeasonStatus.RECOVERY_REQUIRED: frozenset(
        {SeasonStatus.RUNNING, SeasonStatus.PAUSED, SeasonStatus.CLOSING}
    ),
    SeasonStatus.CLOSING: frozenset({SeasonStatus.PRIVATE_COMPLETE, SeasonStatus.SEASON_COMPLETE}),
    SeasonStatus.PRIVATE_COMPLETE: frozenset({SeasonStatus.AWAITING_PUBLISH_REVIEW}),
    SeasonStatus.SEASON_COMPLETE: frozenset({SeasonStatus.AWAITING_PUBLISH_REVIEW}),
    SeasonStatus.AWAITING_PUBLISH_REVIEW: frozenset({SeasonStatus.PUBLISHED}),
    SeasonStatus.PUBLISHED: frozenset(),
}

_RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.SCHEDULED: frozenset({RunStatus.QUEUED, RunStatus.SKIPPED}),
    RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.SKIPPED}),
    RunStatus.RUNNING: frozenset(
        {RunStatus.WAITING_FOR_MODEL, RunStatus.PAUSED, RunStatus.COMPLETED, RunStatus.INTERRUPTED}
    ),
    RunStatus.WAITING_FOR_MODEL: frozenset({RunStatus.RECOVERY_REQUIRED, RunStatus.RUNNING}),
    RunStatus.PAUSED: frozenset({RunStatus.RUNNING, RunStatus.INTERRUPTED}),
    RunStatus.RECOVERY_REQUIRED: frozenset(
        {RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.SKIPPED, RunStatus.INTERRUPTED}
    ),
    RunStatus.INTERRUPTED: frozenset({RunStatus.QUEUED, RunStatus.RUNNING}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.SKIPPED: frozenset(),
}


def next_season_id(existing_ids: Iterable[str]) -> tuple[str, int]:
    """Return the next sequential ``SNN`` identifier and its number."""
    numbers: list[int] = []
    for value in existing_ids:
        if value.startswith("S") and value[1:].isdigit():
            numbers.append(int(value[1:]))
    number = max(numbers, default=0) + 1
    return f"S{number:02d}", number


def next_0600_pacific(green_at: datetime) -> datetime:
    """Return the first 06:00 Pacific boundary strictly after ``green_at``."""
    _require_aware(green_at, "green_at")
    local = green_at.astimezone(PACIFIC)
    candidate = datetime.combine(local.date(), time(6, 0), tzinfo=PACIFIC)
    if candidate <= local:
        candidate = datetime.combine(local.date() + timedelta(days=1), time(6, 0), tzinfo=PACIFIC)
    return candidate


def generate_schedule(season_id: str, green_at: datetime) -> list[ScheduleSlot]:
    """Generate exactly 21 immutable pilot slots from an approval instant."""
    first = next_0600_pacific(green_at)
    slots: list[ScheduleSlot] = []
    for day_index in range(PILOT_DAYS):
        local_date = first.date() + timedelta(days=day_index)
        for slot_index, slot_time in enumerate(PILOT_SLOT_TIMES, start=1):
            scheduled_local = datetime.combine(local_date, slot_time, tzinfo=PACIFIC)
            run_number = day_index * PILOT_SLOTS_PER_DAY + slot_index
            slots.append(
                ScheduleSlot(
                    slot_id=f"{season_id}-run-{run_number:02d}",
                    season_id=season_id,
                    day_number=day_index + 1,
                    slot_number=slot_index,
                    run_number=run_number,
                    scheduled_local=scheduled_local,
                    scheduled_utc=scheduled_local.astimezone(timezone.utc),
                    utc_offset=_format_offset(scheduled_local.utcoffset()),
                )
            )
    return slots


def diary_cutoff_at(third_run_resolved_at: datetime) -> datetime:
    """Return the fixed diary cutoff after the third run is resolved."""
    _require_aware(third_run_resolved_at, "third_run_resolved_at")
    return third_run_resolved_at + DIARY_CUTOFF_AFTER_RUN


def format_delay(delay: timedelta) -> str:
    """Format an execution delay as the signed ``+HH:MM:SS`` provenance value."""
    total_seconds = int(delay.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    absolute = abs(total_seconds)
    hours, remainder = divmod(absolute, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}"


def transition_season(season: Season, target: SeasonStatus) -> Season:
    """Apply one explicitly allowed season transition."""
    allowed = _SEASON_TRANSITIONS[season.status]
    if target not in allowed:
        raise DomainStateError(f"cannot transition season {season.status.value} -> {target.value}")
    return season.model_copy(update={"status": target, "version": season.version + 1})


def transition_run(run: Run, target: RunStatus) -> Run:
    """Apply one explicitly allowed run transition."""
    allowed = _RUN_TRANSITIONS[run.status]
    if target not in allowed:
        raise DomainStateError(f"cannot transition run {run.status.value} -> {target.value}")
    return run.model_copy(update={"status": target})


def arm_season(
    season: Season,
    *,
    green_at: datetime,
    opening: OpeningSnapshot,
    cast: Sequence[CastMember],
    existing_seasons: Iterable[Season] = (),
    private_plan: HiddenSeasonPlan | None = None,
) -> Season:
    """Approve an opening and create its immutable 21-slot pilot schedule."""
    if season.status is not SeasonStatus.AWAITING_GREEN:
        raise DomainStateError("green is valid only while a season awaits approval")
    if not season.preflight_passed:
        raise DomainStateError("green requires successful preflight")
    assert_single_active_season(existing_seasons, exclude_season_id=season.season_id)
    if [member.name for member in cast] != opening.cast:
        raise DomainStateError("cast must match the approved opening roster")
    schedule = generate_schedule(season.season_id, green_at)
    armed = transition_season(season, SeasonStatus.ARMED)
    return armed.model_copy(
        update={
            "opening": opening,
            "private_plan": private_plan,
            "cast": list(cast),
            "schedule": schedule,
            "start_date": schedule[0].scheduled_local.date(),
        }
    )


def assert_single_active_season(
    seasons: Iterable[Season], *, exclude_season_id: str | None = None
) -> None:
    """Reject overlapping non-terminal seasons at the domain boundary."""
    active = [
        season
        for season in seasons
        if season.season_id != exclude_season_id and not season.is_terminal
    ]
    if active:
        ids = ", ".join(season.season_id for season in active)
        raise DomainStateError(f"an active season already exists: {ids}")


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _format_offset(offset: timedelta | None) -> str:
    if offset is None:
        raise ValueError("a UTC offset is required")
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    return f"{sign}{total_minutes // 60:02d}:{total_minutes % 60:02d}"
