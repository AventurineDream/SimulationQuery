"""A production-isolated, deterministic one-day operator rehearsal.

This is deliberately a synthetic acceptance artifact, not a model comparison or
a live-season command. It exercises the same durable scene, diary, day-close,
and next-day-direction paths while keeping every output under a caller-chosen
nonproduction root.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator
from zoneinfo import ZoneInfo

from ..clock import VirtualClock
from ..config import AppConfig, BackendConfig
from ..domain import (
    CastMember,
    HiddenSeasonPlan,
    OpeningSnapshot,
    RoleSheet,
    ScheduleSlot,
    Season,
    SeasonStatus,
)
from ..infrastructure import DataRoots, EventRepository, RecordRepository, SQLiteDatabase, SeasonRepository, ScheduleRepository, WorkQueue
from .live_runtime import LiveSceneFactory, SceneModelManifest, validate_model_manifest
from .season_days import SeasonDayCoordinator
from .worker import DurableWorkflowWorker


PRODUCTION_DATA_ROOT = Path("/var/lib/improv-troupe").resolve()
REHEARSAL_SEASON_ID = "S02-ONE-DAY"


class OneDayRehearsalError(RuntimeError):
    """Raised when a rehearsal root or durable result is unsafe or incomplete."""


@dataclass(frozen=True)
class OneDayRehearsalReport:
    """Portable, non-secret receipt for the complete synthetic day."""

    season_id: str
    model_mode: str
    slots: tuple[dict[str, object], ...]
    diary_counts: dict[str, int]
    day_closed: bool
    next_day_direction_recorded: bool
    receipt_ids: tuple[str, ...]
    receipt_event_types: tuple[str, ...]
    provenance: dict[str, object]
    audit_summary: dict[str, int]
    model_call_count: int
    private_archive_sha256: str
    public_archive_sha256: str
    unresolved: tuple[dict[str, str], ...]
    publication: str
    creator_judgment_prompts: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "season_id": self.season_id,
            "model_mode": self.model_mode,
            "slots": list(self.slots),
            "diary_counts": self.diary_counts,
            "day_closed": self.day_closed,
            "next_day_direction_recorded": self.next_day_direction_recorded,
            "receipt_ids": list(self.receipt_ids),
            "receipt_event_types": list(self.receipt_event_types),
            "provenance": self.provenance,
            "audit_summary": self.audit_summary,
            "model_call_count": self.model_call_count,
            "private_archive_sha256": self.private_archive_sha256,
            "public_archive_sha256": self.public_archive_sha256,
            "unresolved": list(self.unresolved),
            "publication": self.publication,
            "creator_judgment_prompts": list(self.creator_judgment_prompts),
        }


class DeterministicRehearsalClient:
    """A no-network client with structured responses for the real parsers."""

    def __init__(self) -> None:
        self._orchestrator_calls = 0
        self._director_plan_calls = 0
        self._actor_calls = 0

    async def list_models(self) -> list[str]:
        return ["synthetic-director", "synthetic-actor"]

    async def stream_chat(
        self, model: str, messages: list[dict[str, str]], **_: object
    ) -> AsyncIterator[str]:
        instruction = "\n".join(message["content"] for message in messages)
        if "<OUTCOME>" in instruction:
            yield (
                "<OUTCOME>COSTLY_SUCCESS</OUTCOME>"
                "<CENTRAL_QUESTION_ANSWERED>The Aether crosses the caldera, but cannot preserve every margin.</CENTRAL_QUESTION_ANSWERED>"
                "<NARRATION>The final committed maneuver carries the Aether beyond the collapsing thermal seam. The hull clears the caldera while the abandoned reserve chamber buckles behind it, sealing away the route that brought them here. Instruments settle into ordinary disagreement instead of alarms. No display proves whether the caldera answered them, but the vessel is alive, moving, and permanently lighter. In the quieter compartment beyond the crossing, the surviving systems hold just enough power for the crew to choose what comes after survival rather than what might postpone it.</NARRATION>"
                "<IRREVERSIBLE_CHANGE>The reserve chamber and return route are permanently lost.</IRREVERSIBLE_CHANGE>"
                "<GAINED>The Aether survives the crossing with usable knowledge.</GAINED>"
                "<LOST>The reserve chamber and any possibility of retracing the route.</LOST>"
                "<HOOK>The unexplained pattern remains in the archived readings.</HOOK>"
                "<CANON_UPDATE>The Aether crossed the caldera.</CANON_UPDATE>"
                "<CANON_UPDATE>The reserve chamber and return route were lost.</CANON_UPDATE>"
                "<COMPLETE>true</COMPLETE>"
            )
            return
        if "<DIARY_SLOT>" in instruction:
            diary_text = " ".join(f"detail{number}" for number in range(1, 321))
            matches = re.findall(r"original day \d+, slot (\d+)", instruction)
            slot = int(matches[-1]) if matches else 1
            yield (
                f"<DIARY_SLOT>{slot}</DIARY_SLOT><WRITE_NOW>true</WRITE_NOW>"
                f"<DIARY_TEXT>{diary_text}</DIARY_TEXT>"
                "<EVIDENCE_REFS>1</EVIDENCE_REFS>"
            )
            return
        if "<SCENE_OBJECTIVE>" in instruction:
            self._director_plan_calls += 1
            index = (self._director_plan_calls - 1) % 4
            plan_payload = json.loads(
                next(
                    message["content"]
                    for message in reversed(messages)
                    if message["role"] == "user"
                )
            )
            next_actor = str(plan_payload["opening"]["cast"][0])
            required_terms = list(plan_payload.get("required_story_terms", []))
            spine_subject = str(required_terms[0]) if required_terms else "lighthouse signal"
            state_changes = (
                "A brass pass rises from the dry well.",
                "A sealed gallery hatch unlocks above the stair.",
                "A weather vane points toward an unmarked service door.",
                "A signal lens exposes the keeper's hidden route.",
            )
            pressures = (
                "The pass will dissolve when the next bell sounds.",
                "The hatch seals again if the stair is left unattended.",
                "The service door will admit only one carried object.",
                "The route closes at dawn unless the signal is answered.",
            )
            choices_a = (
                "Use the brass pass to enter the dry well.",
                "Climb through the gallery hatch before it seals.",
                "Carry the map through the service door.",
                "Answer the keeper's route through the signal lens.",
            )
            choices_b = (
                "Study the pass and risk the next bell.",
                "Hold the stair and inspect the hatch from below.",
                "Carry the signal lens through the service door.",
                "Archive the route and leave the signal unanswered.",
            )
            clock = ("mystery", "danger", "mission", "relationship")[index]
            if int(plan_payload.get("round_number", 1)) == 1 and required_terms:
                state_changes = (
                    f"The {spine_subject} becomes materially relevant.",
                    *state_changes[1:],
                )
            yield (
                f"<SCENE_OBJECTIVE>Decide what to do about the {spine_subject} before this run ends.</SCENE_OBJECTIVE>"
                "<ADJUDICATION>A prior shared attempt exposes a usable consequence.</ADJUDICATION>"
                f"<STATE_CHANGE>{state_changes[index]}</STATE_CHANGE>"
                f"<PRESSURE>{pressures[index]}</PRESSURE>"
                f"<CHOICE_A>{choices_a[index]}</CHOICE_A><CHOICE_B>{choices_b[index]}</CHOICE_B>"
                f"<NEXT_ACTOR>{next_actor}</NEXT_ACTOR><COMPLETE>false</COMPLETE>"
                f"<CLOCK_CHANGE>{clock}:+1</CLOCK_CHANGE><CANON_UPDATE>{state_changes[index]}</CANON_UPDATE>"
            )
            return
        if "<NARRATION>" in instruction:
            self._orchestrator_calls += 1
            index = (self._orchestrator_calls - 1) % 4
            render_payload = json.loads(
                next(message["content"] for message in reversed(messages) if message["role"] == "user")
            )
            anchor = str(render_payload["continuity_anchors"][0])
            state_changes = (
                "A brass pass rises from the dry well.",
                "A sealed gallery hatch unlocks above the stair.",
                "A weather vane points toward an unmarked service door.",
                "A signal lens exposes the keeper's hidden route.",
            )
            pressures = (
                "The pass will dissolve when the next bell sounds.",
                "The hatch seals again if the stair is left unattended.",
                "The service door will admit only one carried object.",
                "The route closes at dawn unless the signal is answered.",
            )
            choices_a = (
                "Use the brass pass to enter the dry well.",
                "Climb through the gallery hatch before it seals.",
                "Carry the map through the service door.",
                "Answer the keeper's route through the signal lens.",
            )
            choices_b = (
                "Study the pass and risk the next bell.",
                "Hold the stair and test the hatch from below.",
                "Carry the signal lens through the service door.",
                "Archive the route and leave the signal unanswered.",
            )
            lead_ins = (
                f"The {anchor} tilts.",
                f"Around the {anchor}, a new measure appears.",
                f"The {anchor} offers an unexpected opening.",
                f"Within the {anchor}, the pattern finally shifts.",
            )
            yield (
                f"<NARRATION>{lead_ins[index]}</NARRATION>"
            )
            return
        self._actor_calls += 1
        yield (
            "<ACTOR_TEXT>I make a specific choice number "
            f"{self._actor_calls} and leave room for someone else to answer.</ACTOR_TEXT>"
            f"<MEMORY_NOTE>I remember choice {self._actor_calls} changed the shared situation.</MEMORY_NOTE>"
        )


async def run_one_day_rehearsal(root: str | Path) -> OneDayRehearsalReport:
    """Run morning, afternoon, evening, diaries, closure, and direction offline."""
    data_root = _validate_empty_nonproduction_root(root)
    roots = DataRoots.from_root(data_root)
    roots.prepare()
    database = SQLiteDatabase(roots.state / "improv.sqlite3")
    database.migrate()
    clock = VirtualClock(datetime(2026, 9, 7, 13, tzinfo=timezone.utc))
    _seed_one_day(database, clock)

    client = DeterministicRehearsalClient()
    config = AppConfig(
        backends={"synthetic": BackendConfig(base_url="http://synthetic.invalid/v1", kind="ollama")}
    )
    factory = LiveSceneFactory(
        # Technical rehearsal only; this does not establish orientation or consent.
        require_orientation=False,
        database=database,
        roots=roots,
        config=config,
        clock=clock,
        client_factory=lambda _: client,
        strict_rehearsal_acceptance=True,
    )
    coordinator = SeasonDayCoordinator(
        database=database,
        clock=clock,
        scene_factory=factory,
        strict_rehearsal_acceptance=True,
    )
    worker = DurableWorkflowWorker(
        database=database,
        clock=clock,
        scene_factory=factory,
        post_scene=coordinator.after_scene,
        close_day=coordinator.close_day,
        # Output and narrative boundary failures are evidence for review, not
        # candidates for unattended prompt retries in this rehearsal.
        retry_non_transport_failures=False,
    )
    pacific = ZoneInfo("America/Los_Angeles")
    for hour in (6, 12, 18):
        clock.set(datetime(2026, 9, 7, hour, tzinfo=pacific).astimezone(timezone.utc))
        # Process only the scheduled slot.  On a resumed rehearsal, later
        # blocked slots can also be due at this virtual instant; draining the
        # entire queue would make this per-slot accounting ambiguous.
        processed = await worker.drain_due(limit=1)
        if processed != 1:
            raise OneDayRehearsalError(f"expected one {hour:02d}:00 slot, processed {processed}")

    report = _report(database, roots)
    _validate_complete(report)
    report_path = roots.state / "one-day-rehearsal-report.json"
    report_path.write_text(json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


async def run_live_one_day_rehearsal(
    root: str | Path,
    *,
    config: AppConfig,
    manifest: SceneModelManifest,
    resume: bool = False,
) -> OneDayRehearsalReport:
    """Run one fully isolated Aether day against the selected live models.

    This uses reviewed rehearsal character anchors rather than generating a
    private plan as part of the benchmark. It therefore measures the scene,
    diary, closure, and direction behavior that the creator is deciding about.
    """

    data_root = _validate_live_rehearsal_root(root, resume=resume)
    roots = DataRoots.from_root(data_root)
    roots.prepare()
    database = SQLiteDatabase(roots.state / "improv.sqlite3")
    database.migrate()
    clock = VirtualClock(datetime(2026, 9, 7, 13, tzinfo=timezone.utc))
    if resume:
        _validate_live_rehearsal_resume(database, config=config, manifest=manifest)
        _requeue_short_rehearsal_diaries(database)
    else:
        _seed_live_aether_one_day(database, clock, config=config, manifest=manifest)

    factory = LiveSceneFactory(
        # Technical rehearsal only; this does not establish orientation or consent.
        require_orientation=False,
        database=database,
        roots=roots,
        config=config,
        clock=clock,
        strict_rehearsal_acceptance=True,
    )
    coordinator = SeasonDayCoordinator(
        database=database,
        clock=clock,
        scene_factory=factory,
        strict_rehearsal_acceptance=True,
    )
    worker = DurableWorkflowWorker(
        database=database,
        clock=clock,
        scene_factory=factory,
        post_scene=coordinator.after_scene,
        close_day=coordinator.close_day,
        # Preserve rejected live output for review without asking the selected
        # model for a new, unapproved substitute response.
        retry_non_transport_failures=False,
    )
    await _drain_rehearsal_slots(worker=worker, database=database, clock=clock, resume=resume)
    if resume:
        await _resume_completed_day_diaries(
            database=database,
            factory=factory,
            coordinator=coordinator,
            clock=clock,
        )

    report = _report(database, roots)
    report = replace(
        report,
        model_mode="live selected models; isolated nonproduction rehearsal",
        provenance={
            **report.provenance,
            "client": "LiveSceneFactory",
            "model_endpoint_contacted": True,
        },
    )
    _validate_complete(report)
    (roots.state / "one-day-rehearsal-report.json").write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def _validate_empty_nonproduction_root(root: str | Path) -> Path:
    candidate = Path(root).expanduser().resolve(strict=False)
    if candidate == Path(candidate.anchor) or candidate in {Path.home(), Path("/tmp").resolve()}:
        raise OneDayRehearsalError("rehearsal root must be a dedicated child directory")
    if (
        candidate == PRODUCTION_DATA_ROOT
        or PRODUCTION_DATA_ROOT in candidate.parents
        or candidate in PRODUCTION_DATA_ROOT.parents
    ):
        raise OneDayRehearsalError("one-day rehearsal cannot use or contain the production data root")
    if candidate.exists() and any(candidate.iterdir()):
        raise OneDayRehearsalError("one-day rehearsal root must be new or empty")
    return candidate


def _validate_live_rehearsal_root(root: str | Path, *, resume: bool) -> Path:
    """Validate either a fresh root or an explicit durable-resume target."""

    if not resume:
        return _validate_empty_nonproduction_root(root)
    candidate = Path(root).expanduser().resolve(strict=False)
    if candidate == Path(candidate.anchor) or candidate in {Path.home(), Path("/tmp").resolve()}:
        raise OneDayRehearsalError("rehearsal root must be a dedicated child directory")
    if (
        candidate == PRODUCTION_DATA_ROOT
        or PRODUCTION_DATA_ROOT in candidate.parents
        or candidate in PRODUCTION_DATA_ROOT.parents
    ):
        raise OneDayRehearsalError("one-day rehearsal cannot use or contain the production data root")
    if not (candidate / "state" / "improv.sqlite3").is_file():
        raise OneDayRehearsalError("resume requires an existing isolated rehearsal database")
    return candidate


def _validate_live_rehearsal_resume(
    database: SQLiteDatabase,
    *,
    config: AppConfig,
    manifest: SceneModelManifest,
) -> None:
    """Fail closed if a resume request does not match its original rehearsal."""

    season = SeasonRepository(database).get(REHEARSAL_SEASON_ID)
    persisted = SceneModelManifest.model_validate(season.model_manifest)
    if persisted.model_dump(mode="json") != manifest.model_dump(mode="json"):
        raise OneDayRehearsalError("resume manifest does not match the existing rehearsal")
    validate_model_manifest(
        manifest,
        actor_ids=[member.character_id for member in season.cast],
        config=config,
    )


async def _drain_rehearsal_slots(
    *,
    worker: DurableWorkflowWorker,
    database: SQLiteDatabase,
    clock: VirtualClock,
    resume: bool,
) -> None:
    """Advance the virtual day without replaying already-completed live slots."""

    pacific = ZoneInfo("America/Los_Angeles")
    records = RecordRepository(database)
    for number, hour in enumerate((6, 12, 18), start=1):
        target = datetime(2026, 9, 7, hour, tzinfo=pacific).astimezone(timezone.utc)
        run_id = f"{REHEARSAL_SEASON_ID}-run-{number:02d}"
        run_status = str(records.get_run(run_id)["status"])
        already_completed = run_status == "COMPLETED"
        if already_completed and resume:
            continue
        if resume:
            if run_status == "INTERRUPTED":
                WorkQueue(database).requeue_completed_for_manual_resume(
                    work_id=f"work:{run_id}",
                    available_at=target.isoformat(),
                )
            elif run_status == "RUNNING":
                WorkQueue(database).reclaim_leased_for_manual_resume(
                    work_id=f"work:{run_id}",
                    available_at=target.isoformat(),
                )
        if resume and hasattr(database, "connection"):
            row = database.connection.execute(
                "SELECT available_at FROM work_items WHERE work_id = ? AND status = 'QUEUED'",
                (f"work:{run_id}",),
            ).fetchone()
            if row is not None:
                available = datetime.fromisoformat(str(row["available_at"])).astimezone(timezone.utc)
                target = max(target, available)
        clock.set(target)
        # Earlier failed work may have released this slot at a retry instant.
        # Keep draining one queue item at a time until the *intended* scene is
        # terminal; a diary/closure item must never be counted as that scene.
        resumed_interruption = resume and run_status == "INTERRUPTED"
        processed_after_resume = False
        for _ in range(32):
            current_status = str(records.get_run(run_id)["status"])
            if current_status in {"COMPLETED", "SKIPPED"} or (
                current_status == "INTERRUPTED"
                and (not resumed_interruption or processed_after_resume)
            ):
                break
            processed = await worker.drain_due(limit=1)
            if processed == 1:
                processed_after_resume = True
                # A later slot cannot make progress while an earlier scene is
                # interrupted.  Stop advancing virtual time here: repeatedly
                # claiming and releasing the same blocked item only inflates
                # its retry count and obscures the real repair target.
                results = getattr(worker, "results", ())
                if results and getattr(results[-1], "status", None) == "BLOCKED_BY_EARLIER_RUN":
                    return
                continue
            row = database.connection.execute(
                "SELECT available_at FROM work_items WHERE work_id = ? AND status = 'QUEUED'",
                (f"work:{run_id}",),
            ).fetchone()
            if row is None:
                raise OneDayRehearsalError(f"no queued work remains for the {hour:02d}:00 slot")
            clock.set(datetime.fromisoformat(str(row["available_at"])).astimezone(timezone.utc))
        else:
            raise OneDayRehearsalError(f"slot {run_id} did not reach a terminal state")


async def _resume_completed_day_diaries(
    *,
    database: SQLiteDatabase,
    factory: LiveSceneFactory,
    coordinator: SeasonDayCoordinator,
    clock: VirtualClock,
) -> None:
    """Repair unresolved private diary work without replaying completed scenes."""

    records = RecordRepository(database)
    runs = [records.get_run(f"{REHEARSAL_SEASON_ID}-run-{number:02d}") for number in (1, 2, 3)]
    if any(row is None or str(row["status"]) != "COMPLETED" for row in runs):
        return
    unresolved = [
        row
        for row in records.list_diaries(season_id=REHEARSAL_SEASON_ID, day_number=1)
        if str(row["status"]) not in {"WRITTEN", "LATE"}
    ]
    if not unresolved:
        return
    pacific = ZoneInfo("America/Los_Angeles")
    clock.set(datetime(2026, 9, 7, 18, tzinfo=pacific).astimezone(timezone.utc))
    run_id = f"{REHEARSAL_SEASON_ID}-run-03"
    scene = factory({"season_id": REHEARSAL_SEASON_ID, "run_id": run_id})
    result = await scene.execute()
    await coordinator.after_scene(
        {"season_id": REHEARSAL_SEASON_ID, "run_id": run_id},
        scene,
        result,
        allow_diary_repair=True,
    )


def _requeue_short_rehearsal_diaries(database: SQLiteDatabase) -> None:
    """Reopen out-of-target rehearsal diaries for a fresh private attempt.

    The prior artifact remains in the audit archive and the event captures its
    original slot/count; no diary text is edited or discarded.
    """

    records = RecordRepository(database)
    events = EventRepository(database)
    for row in records.list_diaries(season_id=REHEARSAL_SEASON_ID, day_number=1):
        words = row["word_count"]
        if str(row["status"]) not in {"WRITTEN", "LATE"} or words is None or 300 <= int(words) <= 800:
            continue
        diary_id = str(row["diary_id"])
        records.update_diary(
            diary_id=diary_id,
            chosen_slot_number=None,
            status="EXPECTED",
            word_count=None,
            late=False,
            content_path=None,
        )
        events.append(
            event_id=f"{diary_id}:target-repair:{int(words)}",
            natural_key=f"{diary_id}:target-repair:{int(words)}",
            aggregate_type="diary",
            aggregate_id=diary_id,
            event_type="DiaryTargetRepairQueued",
            payload={
                "prior_word_count": int(words),
                "prior_chosen_slot_number": row["chosen_slot_number"],
                "target": "300-800",
            },
        )


def _seed_one_day(database: SQLiteDatabase, clock: VirtualClock) -> None:
    pacific = ZoneInfo("America/Los_Angeles")
    opening = OpeningSnapshot(
        set="The weather returns desk",
        setting="A municipal library below a sealed observatory.",
        cast=["Mara", "Tavi", "Oren", "Sable"],
        world_rules=["Borrowed weather must be returned before midnight."],
    )
    cast = tuple(
        CastMember(character_id=character_id, name=name)
        for character_id, name in (("mara", "Mara"), ("tavi", "Tavi"), ("oren", "Oren"), ("sable", "Sable"))
    )
    plan = HiddenSeasonPlan(
        premise="The library has lent a storm to the wrong patron.",
        hidden_mysteries=["Where did the absent weather go?"],
        role_sheets=[
            RoleSheet(
                character_id=member.character_id,
                objectives=["Learn one thing without claiming certainty."],
                boundaries=["Keep the play TV-14 and nonviolent."],
                knowledge=["The library keeps imperfect weather records."],
                relationships=["Leave room for another character's choice."],
                secrets=["Something about the weather feels personally familiar."],
                play_style="Specific, responsive, and curious.",
                voice_guidance="Use concrete sensory detail without technical jargon.",
            )
            for member in cast
        ],
    )
    SeasonRepository(database).create(
        Season(
            season_id=REHEARSAL_SEASON_ID,
            season_number=2,
            title="One-day operator rehearsal",
            status=SeasonStatus.ARMED,
            opening=opening,
            private_plan=plan,
            cast=list(cast),
            model_manifest={
                "orchestrator": {"backend": "synthetic", "model": "synthetic-director"},
                "actor_default": {"backend": "synthetic", "model": "synthetic-actor"},
            },
        )
    )
    records, schedule, queue = RecordRepository(database), ScheduleRepository(database), WorkQueue(database)
    for number, hour in enumerate((6, 12, 18), start=1):
        local = datetime(2026, 9, 7, hour, tzinfo=pacific)
        slot = ScheduleSlot(
            slot_id=f"{REHEARSAL_SEASON_ID}-run-{number:02d}",
            season_id=REHEARSAL_SEASON_ID,
            day_number=1,
            slot_number=number,
            run_number=number,
            scheduled_local=local,
            scheduled_utc=local.astimezone(timezone.utc),
            utc_offset="-07:00",
        )
        schedule.add(slot)
        records.insert_run(run_id=slot.slot_id, season_id=REHEARSAL_SEASON_ID, slot_id=slot.slot_id, status="QUEUED")
        queue.enqueue(
            work_id=f"work:{slot.slot_id}",
            natural_key=f"run:{slot.slot_id}",
            kind="RUN_SCENE",
            payload={"season_id": REHEARSAL_SEASON_ID, "run_id": slot.slot_id, "day_number": 1, "slot_number": number},
            available_at=slot.scheduled_utc.isoformat(),
            priority=number,
        )


def _seed_live_aether_one_day(
    database: SQLiteDatabase,
    clock: VirtualClock,
    *,
    config: AppConfig,
    manifest: SceneModelManifest,
) -> None:
    _seed_live_aether_rehearsal(
        database,
        clock,
        config=config,
        manifest=manifest,
        season_id=REHEARSAL_SEASON_ID,
        days=1,
        title="Live Aether one-day rehearsal",
    )


def _seed_live_aether_rehearsal(
    database: SQLiteDatabase,
    clock: VirtualClock,
    *,
    config: AppConfig,
    manifest: SceneModelManifest,
    season_id: str,
    days: int,
    title: str,
) -> None:
    """Seed the reviewed Aether anchors for an isolated multi-day rehearsal."""

    if not 1 <= days <= 7:
        raise ValueError("rehearsal days must be between 1 and 7")
    opening = OpeningSnapshot(
        set='Submarine "Aether"',
        setting=(
            "Inside Yellowstone's molten caldera, the Aether moves through magma and ash "
            "under advanced but fallible thermal shielding."
        ),
        cast=["Luna Planck", "Mason Curie", "Higgs Sierra", "Ivy Fermion"],
        world_rules=[
            "Fusion output can be modulated but is never guaranteed to survive extreme heat.",
            "Crew choices influence danger but never determine a required outcome.",
            "Each actor retains full agency over dialogue and actions.",
            "The environment is dangerous; speculative science stays TV-14.",
        ],
    )
    cast = (
        CastMember(character_id="luna-planck", name="Luna Planck", role_sheet_version=1),
        CastMember(character_id="mason-curie", name="Mason Curie", role_sheet_version=1),
        CastMember(character_id="higgs-sierra", name="Higgs Sierra", role_sheet_version=1),
        CastMember(character_id="ivy-fermion", name="Ivy Fermion", role_sheet_version=1),
    )
    validate_model_manifest(manifest, actor_ids=[member.character_id for member in cast], config=config)
    plan = HiddenSeasonPlan(
        premise="The Aether must cross an unstable caldera without treating uncertainty as proof.",
        planned_tensions=[
            "A physical hazard creates a choice between safety, progress, and incomplete data.",
            "The crew must notice when a proposed fix changes another risk.",
        ],
        hidden_mysteries=["The caldera's reactions may be pattern, coincidence, or misread signal."],
        role_sheets=[
            RoleSheet(
                character_id="luna-planck",
                objectives=["Read the strange environment without claiming certainty."],
                boundaries=["Do not turn a hypothesis into proof or command another actor."],
                knowledge=["Botany gives Luna a patient eye for systems under stress."],
                relationships=["Invite others to test an observation rather than solve it alone."],
                secrets=["A familiar growth pattern in the caldera unsettles her."],
                play_style="Quietly observant and experimentally curious.",
                voice_guidance="Concrete, patient, and open about uncertainty.",
            ),
            RoleSheet(
                character_id="mason-curie",
                objectives=["Keep the vessel survivable while weighing incomplete diagnostics."],
                boundaries=["Do not decide other characters' actions or invent certainty."],
                knowledge=["Marine fieldwork makes Mason alert to pressure, currents, and containment."],
                relationships=["Disagree plainly without forcing a consensus."],
                secrets=["He trusts physical margins more than a reassuring display."],
                play_style="Measured, practical, and slow to overpromise.",
                voice_guidance="Calm language with material comparisons rather than lectures.",
            ),
            RoleSheet(
                character_id="higgs-sierra",
                objectives=["Identify the immediate escape or safety move everyone is avoiding."],
                boundaries=["Do not operate systems assigned to another character."],
                knowledge=["Stunt work and wildfire training make Higgs attentive to exits and failure routes."],
                relationships=["Challenge unsafe momentum while leaving the next choice open."],
                secrets=["She maps exits before admitting she is afraid."],
                play_style="Embodied, decisive, and attentive to practical exits.",
                voice_guidance="First-person, concrete, and alert to material risk.",
            ),
            RoleSheet(
                character_id="ivy-fermion",
                objectives=["Name the human cost or overlooked detail inside a technical choice."],
                boundaries=["Do not narrate another actor's inner state or surrender every decision."],
                knowledge=["Playwriting and herbs make Ivy sensitive to rhythm, care, and small signs."],
                relationships=["Press for clarity while making room for contradiction."],
                secrets=["A growing thing in a hostile place feels like a personal challenge."],
                play_style="Reflective but willing to make a consequential proposal.",
                voice_guidance="Specific sensory language with an eye for people and texture.",
            ),
        ],
    )
    SeasonRepository(database).create(
        Season(
            season_id=season_id,
            season_number=2,
            title=title,
            status=SeasonStatus.ARMED,
            opening=opening,
            private_plan=plan,
            cast=list(cast),
            model_manifest=manifest.model_dump(mode="json"),
        )
    )
    _persist_live_rehearsal_identity_provenance(
        database,
        season_id=season_id,
        cast=cast,
        role_sheets=plan.role_sheets,
        created_at=clock.now().isoformat(),
    )
    _enqueue_rehearsal_slots(database, season_id=season_id, days=days)


def _persist_live_rehearsal_identity_provenance(
    database: SQLiteDatabase,
    *,
    season_id: str,
    cast: tuple[CastMember, ...],
    role_sheets: list[RoleSheet],
    created_at: str,
) -> None:
    """Persist the exact role inputs used by the disposable model audition.

    These are explicitly rehearsal anchors, not a substitute for the creator's
    production preparation approvals. Their purpose is to make a later model
    comparison inspectable: a result can name the card and role-sheet versions
    it actually received.
    """

    cards = {
        "luna-planck": {
            "pronouns": "she/her",
            "public_brief": "A quiet botanist who brings succulents to rehearsals.",
            "occupation_skills": ["botany", "patient observation"],
            "voice_anchors": ["quietly curious", "concrete sensory comparisons"],
            "habits": ["hums old folk songs while watering plants"],
        },
        "mason-curie": {
            "pronouns": "he/him",
            "public_brief": "A rugged marine biologist who treats pressure as practical fact.",
            "occupation_skills": ["marine biology", "field containment"],
            "voice_anchors": ["calm", "measured material comparisons"],
            "habits": ["uses seaweed as stage props"],
        },
        "higgs-sierra": {
            "pronouns": "she/her",
            "public_brief": "An energetic stunt double with wildfire-safety habits.",
            "occupation_skills": ["stunt safety", "wildfire escape planning"],
            "voice_anchors": ["embodied", "decisive"],
            "habits": ["checks escape routes before rehearsals"],
        },
        "ivy-fermion": {
            "pronouns": "he/him",
            "public_brief": "A playwright who grows herbs in the green room.",
            "occupation_skills": ["playwriting", "herb growing"],
            "voice_anchors": ["observant", "relationship-aware"],
            "habits": ["writes early while dew is on the grass"],
        },
    }
    sheets = {sheet.character_id: sheet for sheet in role_sheets}
    with database.transaction() as connection:
        for member in cast:
            card = cards[member.character_id]
            connection.execute(
                "INSERT INTO character_card_versions(season_id, character_id, version, status, name, "
                "pronouns, public_brief, occupation_skills_json, voice_anchors_json, habits_json, "
                "derived_opening_version, created_at, approved_at) "
                "VALUES (?, ?, 1, 'REHEARSAL_ANCHOR', ?, ?, ?, ?, ?, ?, 1, ?, NULL)",
                (
                    season_id,
                    member.character_id,
                    member.name,
                    card["pronouns"],
                    card["public_brief"],
                    json.dumps(card["occupation_skills"]),
                    json.dumps(card["voice_anchors"]),
                    json.dumps(card["habits"]),
                    created_at,
                ),
            )
            connection.execute(
                "INSERT INTO role_sheet_versions(season_id, character_id, version, content_json, created_at) "
                "VALUES (?, ?, 1, ?, ?)",
                (season_id, member.character_id, sheets[member.character_id].model_dump_json(), created_at),
            )


def _enqueue_one_day_slots(database: SQLiteDatabase, clock: VirtualClock) -> None:
    _enqueue_rehearsal_slots(database, season_id=REHEARSAL_SEASON_ID, days=1)


def _enqueue_rehearsal_slots(
    database: SQLiteDatabase,
    *,
    season_id: str,
    days: int,
) -> None:
    records, schedule, queue = RecordRepository(database), ScheduleRepository(database), WorkQueue(database)
    pacific = ZoneInfo("America/Los_Angeles")
    for day_number in range(1, days + 1):
        for slot_number, hour in enumerate((6, 12, 18), start=1):
            run_number = ((day_number - 1) * 3) + slot_number
            local = datetime(2026, 9, 6 + day_number, hour, tzinfo=pacific)
            slot = ScheduleSlot(
                slot_id=f"{season_id}-run-{run_number:02d}",
                season_id=season_id,
                day_number=day_number,
                slot_number=slot_number,
                run_number=run_number,
                scheduled_local=local,
                scheduled_utc=local.astimezone(timezone.utc),
                utc_offset="-07:00",
            )
            schedule.add(slot)
            records.insert_run(
                run_id=slot.slot_id,
                season_id=season_id,
                slot_id=slot.slot_id,
                status="QUEUED",
            )
            queue.enqueue(
                work_id=f"work:{slot.slot_id}",
                natural_key=f"run:{slot.slot_id}",
                kind="RUN_SCENE",
                payload={
                    "season_id": season_id,
                    "run_id": slot.slot_id,
                    "day_number": day_number,
                    "slot_number": slot_number,
                },
                available_at=slot.scheduled_utc.isoformat(),
                priority=run_number,
            )


def _report(database: SQLiteDatabase, roots: DataRoots) -> OneDayRehearsalReport:
    slots = tuple(
        {
            "run_id": str(row["run_id"]),
            "slot": ("morning", "afternoon", "evening")[int(row["slot_number"]) - 1],
            "status": str(row["status"]),
            "turn_count": int(row["turn_count"]),
            "completion_reason": str(row["completion_reason"] or ""),
        }
        for row in database.connection.execute(
            "SELECT r.run_id, r.status, r.turn_count, r.completion_reason, s.slot_number FROM runs r JOIN schedule_slots s ON s.slot_id = r.slot_id WHERE r.season_id = ? ORDER BY s.slot_number",
            (REHEARSAL_SEASON_ID,),
        )
    )
    diary_counts = {
        str(row["status"]): int(row["count"])
        for row in database.connection.execute(
            "SELECT status, COUNT(*) AS count FROM diaries WHERE season_id = ? GROUP BY status", (REHEARSAL_SEASON_ID,)
        )
    }
    day = database.connection.execute(
        "SELECT closed FROM days WHERE season_id = ? AND day_number = 1", (REHEARSAL_SEASON_ID,)
    ).fetchone()
    event_rows = tuple(
        (str(row["event_id"]), str(row["event_type"]))
        for row in database.connection.execute(
            "SELECT event_id, event_type FROM domain_events WHERE aggregate_id = ? OR aggregate_id = ? "
            "OR aggregate_id IN (SELECT run_id FROM runs WHERE season_id = ?) "
            "OR aggregate_id IN (SELECT diary_id FROM diaries WHERE season_id = ?) "
            "ORDER BY created_at, event_id",
            (REHEARSAL_SEASON_ID, f"{REHEARSAL_SEASON_ID}:day:1", REHEARSAL_SEASON_ID, REHEARSAL_SEASON_ID),
        )
    )
    event_ids = tuple(event_id for event_id, _ in event_rows)
    event_types = tuple(sorted({event_type for _, event_type in event_rows}))
    direction = "NextDayDirectionCreated" in event_types
    unresolved: list[dict[str, str]] = []
    for row in database.connection.execute(
        "SELECT run_id, status FROM runs WHERE season_id = ? AND status NOT IN ('COMPLETED', 'SKIPPED')", (REHEARSAL_SEASON_ID,)
    ):
        unresolved.append({"kind": "run", "id": str(row["run_id"]), "status": str(row["status"])})
    for row in database.connection.execute(
        "SELECT diary_id, status FROM diaries WHERE season_id = ? AND status NOT IN ('WRITTEN', 'LATE', 'MISSING', 'PRIVATE')", (REHEARSAL_SEASON_ID,)
    ):
        unresolved.append({"kind": "diary", "id": str(row["diary_id"]), "status": str(row["status"])})
    calls = int(database.connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0])
    audit_row = database.connection.execute(
        "SELECT "
        "SUM(status = 'COMPLETED') AS completed, "
        "SUM(status = 'COMPLETED' AND parse_status = 'PARSED') AS parsed, "
        "SUM(status = 'COMPLETED' AND validation_status = 'VALID') AS validated, "
        "SUM(status = 'COMPLETED' AND acceptance_status = 'ACCEPTED') AS accepted, "
        "SUM(status = 'COMPLETED' AND render_status = 'RENDERED') AS rendered, "
        "SUM(status = 'COMPLETED' AND (parse_status IS NULL OR validation_status IS NULL "
        "OR acceptance_status IS NULL OR render_status IS NULL OR parse_status = 'PENDING' "
        "OR validation_status = 'PENDING' OR acceptance_status = 'PENDING' OR render_status = 'PENDING')) AS pending "
        "FROM model_calls"
    ).fetchone()
    publication_row = database.connection.execute(
        "SELECT version, status FROM publications WHERE season_id = ? ORDER BY version DESC LIMIT 1",
        (REHEARSAL_SEASON_ID,),
    ).fetchone()
    publication = (
        "not attempted at report generation; no public projection was created"
        if publication_row is None
        else (
            "publication recorded in this root; report reflects the current persisted publication "
            f"version {int(publication_row['version'])} ({str(publication_row['status'])})"
        )
    )
    return OneDayRehearsalReport(
        season_id=REHEARSAL_SEASON_ID,
        model_mode="deterministic synthetic client; no model endpoint contacted",
        slots=slots,
        diary_counts=diary_counts,
        day_closed=bool(day and day["closed"]),
        next_day_direction_recorded=direction,
        receipt_ids=event_ids,
        receipt_event_types=event_types,
        provenance={
            "clock": "VirtualClock at fixed Pacific morning, afternoon, and evening boundaries",
            "client": "DeterministicRehearsalClient",
            "model_endpoint_contacted": False,
            "model_call_statuses": {
                str(row["status"]): int(row["count"])
                for row in database.connection.execute("SELECT status, COUNT(*) AS count FROM model_calls GROUP BY status")
            },
            "recording": "SQLite events, model-call metadata, and private artifacts under the rehearsal root",
        },
        audit_summary={
            key: int(audit_row[key] or 0)
            for key in ("completed", "parsed", "validated", "accepted", "rendered", "pending")
        },
        model_call_count=calls,
        private_archive_sha256=_tree_hash(roots.private),
        public_archive_sha256=_tree_hash(roots.public),
        unresolved=tuple(unresolved),
        publication=publication,
        creator_judgment_prompts=(
            "Did morning, afternoon, and evening feel like three changed states?",
            "Could each blocked or failed step be explained from dashboard evidence?",
            "Did the actors remain distinct in behavior, relationship, and voice?",
            "Does this evidence justify a separately authorized local-model day?",
        ),
    )


def _validate_complete(report: OneDayRehearsalReport) -> None:
    if len(report.slots) != 3 or any(slot["status"] != "COMPLETED" for slot in report.slots):
        raise OneDayRehearsalError("all three rehearsal slots must complete")
    if report.diary_counts != {"WRITTEN": 4}:
        raise OneDayRehearsalError("the rehearsal requires four written diary opportunities")
    if not report.day_closed or not report.next_day_direction_recorded or report.unresolved:
        raise OneDayRehearsalError("day closure, next-day direction, and resolved work are required")
    if report.audit_summary["pending"]:
        raise OneDayRehearsalError("all completed rehearsal model calls require acceptance evidence")
    if "DiaryTargetMissed" in report.receipt_event_types:
        raise OneDayRehearsalError("all four rehearsal diaries must meet the 300-800 word target")
    if report.public_archive_sha256 != hashlib.sha256().hexdigest():
        raise OneDayRehearsalError("synthetic one-day rehearsal must not create public output")


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((candidate for candidate in root.rglob("*") if candidate.is_file()), key=lambda item: str(item.relative_to(root))):
        digest.update(str(path.relative_to(root)).encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


__all__ = [
    "DeterministicRehearsalClient",
    "OneDayRehearsalError",
    "OneDayRehearsalReport",
    "PRODUCTION_DATA_ROOT",
    "REHEARSAL_SEASON_ID",
    "run_live_one_day_rehearsal",
    "run_one_day_rehearsal",
]
