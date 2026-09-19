"""Typed, replay-safe commands for the season workflow shell.

This is deliberately narrower than the eventual workflow worker. Commands
validate intent, apply one durable domain transition, append an event, and
remember the response for exact request-id replay. Scene execution and model
calls belong to later implementation gates.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from ..clock import Clock, SystemClock
from ..domain import (
    CastMember,
    HiddenSeasonPlan,
    OpeningSnapshot,
    Season,
    SeasonStatus,
    arm_season,
    transition_season,
)
from ..infrastructure import (
    CommandRequestRepository,
    EventRepository,
    RecordRepository,
    SQLiteDatabase,
    SeasonRepository,
    WorkQueue,
)


class CommandError(RuntimeError):
    """Base error for rejected application commands."""


class CommandRequestConflict(CommandError):
    """Raised when a request id is reused for a different command."""


@dataclass(frozen=True)
class CommandResult:
    """Stable command response, including whether it was an exact replay."""

    request_id: str
    command_type: str
    payload: dict[str, Any]
    replayed: bool = False


class Command(Protocol):
    request_id: str
    command_type: str

    def payload(self) -> dict[str, Any]:
        """Return the canonical, request-id-free command payload."""


@dataclass(frozen=True)
class CreateSeason:
    """Create a new draft season before opening approval."""

    request_id: str
    season_id: str
    season_number: int
    title: str | None = None
    command_type: str = "CREATE_SEASON"

    def payload(self) -> dict[str, Any]:
        return {
            "season_id": self.season_id,
            "season_number": self.season_number,
            "title": self.title,
        }


@dataclass(frozen=True)
class TransitionSeason:
    """Apply one explicitly allowed domain season transition."""

    request_id: str
    season_id: str
    target: SeasonStatus
    command_type: str = "TRANSITION_SEASON"

    def __post_init__(self) -> None:
        if isinstance(self.target, str):
            object.__setattr__(self, "target", SeasonStatus(self.target))

    def payload(self) -> dict[str, Any]:
        return {"season_id": self.season_id, "target": self.target.value}


@dataclass(frozen=True)
class ReviseOpening:
    """Persist a new creator-visible opening revision before approval."""

    request_id: str
    season_id: str
    opening: OpeningSnapshot
    cast: tuple[CastMember, ...]
    command_type: str = "REVISE_OPENING"

    def payload(self) -> dict[str, Any]:
        return {
            "season_id": self.season_id,
            "opening": self.opening.model_dump(mode="json"),
            "cast": [member.model_dump(mode="json") for member in self.cast],
        }


@dataclass(frozen=True)
class PreflightSeason:
    """Record successful local preflight and lock its private configuration."""

    request_id: str
    season_id: str
    checks: dict[str, bool]
    model_manifest: dict[str, Any]
    command_type: str = "PREFLIGHT_SEASON"

    def payload(self) -> dict[str, Any]:
        return {
            "season_id": self.season_id,
            "checks": self.checks,
            "model_manifest": self.model_manifest,
        }


@dataclass(frozen=True)
class GreenSeason:
    """Approve the creator-visible opening and enqueue the 21 pilot runs."""

    request_id: str
    season_id: str
    green_at: datetime
    opening: OpeningSnapshot
    cast: tuple[CastMember, ...]
    private_plan: HiddenSeasonPlan | None = None
    command_type: str = "GREEN_SEASON"

    def payload(self) -> dict[str, Any]:
        return {
            "season_id": self.season_id,
            "green_at": self.green_at.isoformat(),
            "opening": self.opening.model_dump(mode="json"),
            "cast": [member.model_dump(mode="json") for member in self.cast],
            "private_plan": self.private_plan.model_dump(mode="json")
            if self.private_plan is not None
            else None,
        }


@dataclass(frozen=True)
class ControlSeason:
    """Apply a creator operational control without injecting story direction."""

    request_id: str
    season_id: str
    target: SeasonStatus
    expected_version: int | None = None
    review_snapshot_hash: str | None = None
    command_type: str = "CONTROL_SEASON"

    def __post_init__(self) -> None:
        if isinstance(self.target, str):
            object.__setattr__(self, "target", SeasonStatus(self.target))

    def payload(self) -> dict[str, Any]:
        return {
            "season_id": self.season_id,
            "target": self.target.value,
            "expected_version": self.expected_version,
            "review_snapshot_hash": self.review_snapshot_hash,
        }


@dataclass(frozen=True)
class SetWellnessPolicy:
    """Set the season-local automatic tap-out policy."""

    request_id: str
    season_id: str
    auto_tap_out: bool
    command_type: str = "SET_WELLNESS_POLICY"

    def payload(self) -> dict[str, Any]:
        return {"season_id": self.season_id, "auto_tap_out": self.auto_tap_out}


@dataclass(frozen=True)
class EnterRecovery:
    """Pause a running season and mark one run for creator recovery."""

    request_id: str
    season_id: str
    run_id: str
    reason: str = "model_failure"
    command_type: str = "ENTER_RECOVERY"

    def payload(self) -> dict[str, Any]:
        return {
            "season_id": self.season_id,
            "run_id": self.run_id,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ResolveRecovery:
    """Apply the creator's retry, skip, or end decision after a model wait."""

    request_id: str
    season_id: str
    run_id: str
    decision: str
    expected_season_version: int | None = None
    expected_run_version: int | None = None
    expected_recovery_version: int | None = None
    review_snapshot_hash: str | None = None
    command_type: str = "RESOLVE_RECOVERY"

    def __post_init__(self) -> None:
        if self.decision not in {"retry", "skip", "end"}:
            raise ValueError("recovery decision must be retry, skip, or end")

    def payload(self) -> dict[str, Any]:
        return {
            "season_id": self.season_id,
            "run_id": self.run_id,
            "decision": self.decision,
            "expected_season_version": self.expected_season_version,
            "expected_run_version": self.expected_run_version,
            "expected_recovery_version": self.expected_recovery_version,
            "review_snapshot_hash": self.review_snapshot_hash,
        }


class CommandHandler(Protocol):
    def __call__(self, command: Command) -> dict[str, Any]:
        """Apply a new command and return a JSON-serializable response payload."""


class CommandBus:
    """Dispatch typed commands with exact request-id replay semantics.

    The request journal, domain transition, event append, and work enqueue are
    committed in one SQLite transaction. Repositories may open their own
    transaction scopes, but :class:`SQLiteDatabase` composes them into the
    outer command transaction.
    """

    def __init__(
        self,
        database: SQLiteDatabase | str,
        *,
        season_repository: SeasonRepository | None = None,
        request_repository: CommandRequestRepository | None = None,
        event_repository: EventRepository | None = None,
        clock: Clock | None = None,
    ):
        self.database = database if isinstance(database, SQLiteDatabase) else SQLiteDatabase(database)
        self.database.migrate()
        self.clock = clock or SystemClock()
        self.seasons = season_repository or SeasonRepository(self.database)
        self.requests = request_repository or CommandRequestRepository(self.database)
        self.events = event_repository or EventRepository(self.database)
        self.records = RecordRepository(self.database)
        self.work = WorkQueue(self.database)

    def execute(self, command: Command) -> CommandResult:
        self._validate_request_id(command.request_id)
        payload = command.payload()
        fingerprint = _fingerprint(command.command_type, payload)
        with self.database.transaction():
            previous = self.requests.get(command.request_id)
            if previous is not None:
                if (
                    previous["command_type"] != command.command_type
                    or previous["fingerprint"] != fingerprint
                ):
                    raise CommandRequestConflict(
                        f"request id {command.request_id!r} was already used for different intent"
                    )
                saved = json.loads(previous["response_json"])
                return CommandResult(
                    request_id=command.request_id,
                    command_type=command.command_type,
                    payload=saved,
                    replayed=True,
                )

            response = self._dispatch(command)
            self.requests.store(
                request_id=command.request_id,
                command_type=command.command_type,
                fingerprint=fingerprint,
                response_json=json.dumps(response, sort_keys=True),
            )
            return CommandResult(
                request_id=command.request_id,
                command_type=command.command_type,
                payload=response,
            )

    def _dispatch(self, command: Command) -> dict[str, Any]:
        if isinstance(command, CreateSeason):
            season = Season(
                season_id=command.season_id,
                season_number=command.season_number,
                title=command.title,
            )
            self.seasons.create(season)
            self.events.append(
                event_id=f"event:{command.request_id}",
                natural_key=f"command:{command.request_id}",
                aggregate_type="season",
                aggregate_id=season.season_id,
                event_type="SeasonCreated",
                payload={"season_number": season.season_number, "title": season.title},
            )
            return _season_payload(season)

        if isinstance(command, TransitionSeason):
            season = self.seasons.get(command.season_id)
            transitioned = transition_season(season, command.target)
            self.seasons.update(transitioned, expected_version=season.version)
            self.events.append(
                event_id=f"event:{command.request_id}",
                natural_key=f"command:{command.request_id}",
                aggregate_type="season",
                aggregate_id=season.season_id,
                event_type="SeasonTransitioned",
                payload={"from": season.status.value, "to": transitioned.status.value},
            )
            if transitioned.status is SeasonStatus.CLOSING:
                self._enqueue_handoff(season_id=season.season_id, request_id=command.request_id)
            return _season_payload(transitioned)

        if isinstance(command, ReviseOpening):
            season = self.seasons.get(command.season_id)
            if season.status not in {SeasonStatus.DRAFT, SeasonStatus.AWAITING_GREEN}:
                raise CommandError("opening revisions are only valid before green")
            if [member.name for member in command.cast] != command.opening.cast:
                raise CommandError("cast must match the opening roster")
            updated = season.model_copy(
                update={
                    "opening": command.opening,
                    "cast": list(command.cast),
                    "preflight_passed": False,
                    "model_manifest": {},
                    "version": season.version + 1,
                }
            )
            self.seasons.update(updated, expected_version=season.version)
            opening_version = self.seasons.record_opening_version(
                season_id=season.season_id,
                opening=command.opening,
                cast=list(command.cast),
            )
            self.events.append(
                event_id=f"event:{command.request_id}",
                natural_key=f"command:{command.request_id}",
                aggregate_type="season",
                aggregate_id=season.season_id,
                event_type="OpeningRevised",
                payload={"opening_version": opening_version},
            )
            return {**_season_payload(updated), "opening_version": opening_version}

        if isinstance(command, PreflightSeason):
            season = self.seasons.get(command.season_id)
            if season.status not in {SeasonStatus.DRAFT, SeasonStatus.AWAITING_GREEN}:
                raise CommandError("preflight is only valid before the season is greenlit")
            if not command.checks:
                raise CommandError("preflight requires named checks")
            failed = sorted(name for name, passed in command.checks.items() if not passed)
            if failed:
                raise CommandError(f"preflight checks failed: {', '.join(failed)}")
            if not command.model_manifest:
                raise CommandError("preflight requires a selected model/config manifest")
            if season.opening is None or not season.cast:
                raise CommandError("preflight requires a planned opening")
            updated = season.model_copy(
                update={
                    "preflight_passed": True,
                    "model_manifest": command.model_manifest,
                    "version": season.version + 1,
                }
            )
            self.seasons.update(updated, expected_version=season.version)
            self.events.append(
                event_id=f"event:{command.request_id}",
                natural_key=f"command:{command.request_id}",
                aggregate_type="season",
                aggregate_id=season.season_id,
                event_type="PreflightPassed",
                payload={"checks": command.checks, "model_manifest": command.model_manifest},
            )
            return _season_payload(updated)

        if isinstance(command, GreenSeason):
            if command.green_at.tzinfo is None or command.green_at.utcoffset() is None:
                raise CommandError("green_at must be timezone-aware")
            season = self.seasons.get(command.season_id)
            if not season.preflight_passed or not season.model_manifest:
                raise CommandError("green requires successful preflight")
            if season.opening is None or season.opening != command.opening:
                raise CommandError("green opening must match the latest approved revision")
            existing = self.seasons.list_all()
            armed = arm_season(
                season,
                green_at=command.green_at,
                opening=command.opening,
                cast=command.cast,
                existing_seasons=existing,
                private_plan=command.private_plan,
            )
            self.seasons.update(armed, expected_version=season.version)
            scheduled_at = armed.schedule[0].scheduled_utc.isoformat()
            for slot in armed.schedule:
                self.records.insert_run(
                    run_id=slot.slot_id,
                    season_id=armed.season_id,
                    slot_id=slot.slot_id,
                    status="QUEUED",
                )
                self.work.enqueue(
                    work_id=f"work:{slot.slot_id}",
                    natural_key=f"run:{slot.slot_id}",
                    kind="RUN_SCENE",
                    payload={
                        "season_id": armed.season_id,
                        "run_id": slot.slot_id,
                        "slot_id": slot.slot_id,
                        "day_number": slot.day_number,
                        "run_number": slot.run_number,
                    },
                    available_at=slot.scheduled_utc.isoformat(),
                    priority=slot.run_number,
                )
            self.events.append(
                event_id=f"event:{command.request_id}",
                natural_key=f"command:{command.request_id}",
                aggregate_type="season",
                aggregate_id=armed.season_id,
                event_type="SeasonGreenlit",
                payload={"run_count": len(armed.schedule), "first_run_at": scheduled_at},
            )
            return {
                **_season_payload(armed),
                "first_run_at": scheduled_at,
                "run_count": len(armed.schedule),
            }

        if isinstance(command, ControlSeason):
            season = self.seasons.get(command.season_id)
            if command.expected_version is not None and season.version != command.expected_version:
                raise CommandError(
                    f"stale season version: expected {command.expected_version}, found {season.version}"
                )
            controlled = transition_season(season, command.target)
            self.seasons.update(controlled, expected_version=season.version)
            self.events.append(
                event_id=f"event:{command.request_id}",
                natural_key=f"command:{command.request_id}",
                aggregate_type="season",
                aggregate_id=season.season_id,
                event_type="SeasonControlled",
                payload={"from": season.status.value, "to": controlled.status.value},
            )
            if controlled.status is SeasonStatus.CLOSING:
                self._enqueue_handoff(season_id=season.season_id, request_id=command.request_id)
            return _season_payload(controlled)

        if isinstance(command, SetWellnessPolicy):
            season = self.seasons.get(command.season_id)
            if season.is_terminal:
                raise CommandError("wellness policy cannot change after season close")
            updated = season.model_copy(
                update={
                    "auto_tap_out": command.auto_tap_out,
                    "version": season.version + 1,
                }
            )
            self.seasons.update(updated, expected_version=season.version)
            self.events.append(
                event_id=f"event:{command.request_id}",
                natural_key=f"command:{command.request_id}",
                aggregate_type="season",
                aggregate_id=season.season_id,
                event_type="WellnessPolicyChanged",
                payload={
                    "auto_tap_out": command.auto_tap_out,
                    "manual_review": not command.auto_tap_out,
                },
            )
            return _season_payload(updated)

        if isinstance(command, EnterRecovery):
            season = self.seasons.get(command.season_id)
            if season.status is not SeasonStatus.RUNNING:
                raise CommandError("recovery can only be entered from a running season")
            run = self.records.get_run(command.run_id)
            if run is None or run["season_id"] != command.season_id:
                raise CommandError("recovery run does not belong to the season")
            if run["status"] not in {
                "QUEUED",
                "RUNNING",
                "WAITING_FOR_MODEL",
                "INTERRUPTED",
            }:
                raise CommandError(f"run {command.run_id} cannot enter recovery from {run['status']}")
            recovering = transition_season(season, SeasonStatus.RECOVERY_REQUIRED)
            self.seasons.update(recovering, expected_version=season.version)
            self.records.update_run_status(
                run_id=command.run_id,
                status="RECOVERY_REQUIRED",
                completion_reason=command.reason,
                expected_status=run["status"],
            )
            recovery = self.records.get_recovery(command.run_id)
            if recovery is None:
                self.records.insert_recovery(
                    recovery_id=f"recovery:manual:{command.run_id}:{command.request_id}",
                    season_id=command.season_id,
                    run_id=command.run_id,
                    status="RECOVERY_REQUIRED",
                    created_at=self.clock.now().isoformat(),
                )
            else:
                self.records.update_recovery(
                    recovery_id=recovery["recovery_id"],
                    status="RECOVERY_REQUIRED",
                )
            self.events.append(
                event_id=f"event:{command.request_id}",
                natural_key=f"command:{command.request_id}",
                aggregate_type="run",
                aggregate_id=command.run_id,
                event_type="RecoveryRequired",
                payload={"season_id": command.season_id, "reason": command.reason},
            )
            return {
                **_season_payload(recovering),
                "run_id": command.run_id,
                "reason": command.reason,
            }

        if isinstance(command, ResolveRecovery):
            season = self.seasons.get(command.season_id)
            if (
                command.expected_season_version is not None
                and season.version != command.expected_season_version
            ):
                raise CommandError(
                    "stale season version: expected "
                    f"{command.expected_season_version}, found {season.version}"
                )
            if season.status not in {SeasonStatus.RECOVERY_REQUIRED, SeasonStatus.ARMED}:
                raise CommandError("recovery decisions require a season in recovery")
            run = self.records.get_run(command.run_id)
            if run is None or run["season_id"] != command.season_id:
                raise CommandError("recovery run does not belong to the season")
            if (
                command.expected_run_version is not None
                and int(run["version"]) != command.expected_run_version
            ):
                raise CommandError(
                    "stale run version: expected "
                    f"{command.expected_run_version}, found {int(run['version'])}"
                )
            # A first due run can fail before the worker has promoted an ARMED
            # season to RUNNING.  Accept that durable legacy shape so the
            # creator can resolve the already-recorded run-level recovery.
            if season.status is SeasonStatus.ARMED and run["status"] != "RECOVERY_REQUIRED":
                raise CommandError("recovery decisions require a season in recovery")
            recovery = self.records.get_recovery(command.run_id)
            if command.expected_recovery_version is not None:
                if recovery is None:
                    raise CommandError("expected recovery record is missing")
                if int(recovery["version"]) != command.expected_recovery_version:
                    raise CommandError(
                        "stale recovery version: expected "
                        f"{command.expected_recovery_version}, found {int(recovery['version'])}"
                    )
            if command.decision == "retry":
                if run["status"] != "RECOVERY_REQUIRED":
                    raise CommandError("retry requires a run in recovery")
                self.records.update_run_status(
                    run_id=command.run_id,
                    status="QUEUED",
                    completion_reason="creator_retry",
                    expected_status="RECOVERY_REQUIRED",
                )
                self.work.enqueue(
                    work_id=f"work:retry:{command.run_id}:{command.request_id}",
                    natural_key=f"retry:{command.run_id}:{command.request_id}",
                    kind="RUN_SCENE",
                    payload={"season_id": command.season_id, "run_id": command.run_id},
                    available_at=self.clock.now().isoformat(),
                    priority=-100,
                )
                resumed = transition_season(season, SeasonStatus.RUNNING)
                self.seasons.update(resumed, expected_version=season.version)
                response = {**_season_payload(resumed), "run_id": command.run_id, "decision": "retry"}
            elif command.decision == "skip":
                if run["status"] != "RECOVERY_REQUIRED":
                    raise CommandError("skip requires a run in recovery")
                self.records.update_run_status(
                    run_id=command.run_id,
                    status="SKIPPED",
                    completion_reason="creator_skip",
                    expected_status="RECOVERY_REQUIRED",
                )
                resumed = transition_season(season, SeasonStatus.RUNNING)
                self.seasons.update(resumed, expected_version=season.version)
                response = {**_season_payload(resumed), "run_id": command.run_id, "decision": "skip"}
            else:
                if run["status"] != "RECOVERY_REQUIRED":
                    raise CommandError("end requires a run in recovery")
                ended = transition_season(season, SeasonStatus.CLOSING)
                self.seasons.update(ended, expected_version=season.version)
                self._enqueue_handoff(season_id=season.season_id, request_id=command.request_id)
                response = {**_season_payload(ended), "run_id": command.run_id, "decision": "end"}
            if recovery is not None:
                recovery_status = {
                    "retry": "RETRY",
                    "skip": "SKIPPED",
                    "end": "ENDED",
                }[command.decision]
                self.records.update_recovery(
                    recovery_id=recovery["recovery_id"],
                    status=recovery_status,
                    decision=command.decision,
                    resolved_at=self.clock.now().isoformat(),
                    expected_version=command.expected_recovery_version,
                )
            self.events.append(
                event_id=f"event:{command.request_id}",
                natural_key=f"command:{command.request_id}",
                aggregate_type="run",
                aggregate_id=command.run_id,
                event_type="RecoveryResolved",
                payload={"season_id": command.season_id, "decision": command.decision},
            )
            return response

        raise CommandError(f"unsupported command type: {command.command_type}")

    def _enqueue_handoff(self, *, season_id: str, request_id: str) -> None:
        self.work.enqueue(
            work_id=f"work:handoff:{season_id}:{request_id}",
            natural_key=f"handoff:{season_id}:{request_id}",
            kind="BUILD_HANDOFF",
            payload={"season_id": season_id},
            available_at=self.clock.now().isoformat(),
        )

    @staticmethod
    def _validate_request_id(request_id: str) -> None:
        if not request_id or not request_id.strip():
            raise CommandError("request_id must be a non-empty string")


def _season_payload(season: Season) -> dict[str, Any]:
    return {
        "season_id": season.season_id,
        "season_number": season.season_number,
        "title": season.title,
        "preflight_passed": season.preflight_passed,
        "opening": season.opening.creator_view() if season.opening is not None else None,
        "status": season.status.value,
        "auto_tap_out": season.auto_tap_out,
        "version": season.version,
    }


def _fingerprint(command_type: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"command_type": command_type, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
