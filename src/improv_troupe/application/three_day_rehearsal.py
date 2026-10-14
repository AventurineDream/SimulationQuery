"""Isolated three-day live-model rehearsal and continuity receipt."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..clock import VirtualClock
from ..config import AppConfig
from ..infrastructure import DataRoots, RecordRepository, SQLiteDatabase, SeasonRepository, WorkQueue
from ..llm.client import ChatClient
from .live_runtime import LiveSceneFactory, SceneModelManifest, validate_model_manifest
from .one_day_rehearsal import PRODUCTION_DATA_ROOT, _seed_live_aether_rehearsal, _tree_hash
from .season_days import SeasonDayCoordinator
from .worker import DurableWorkflowWorker


THREE_DAY_REHEARSAL_SEASON_ID = "S02-THREE-DAY"
THREE_DAY_REHEARSAL_DAYS = 3


class ThreeDayRehearsalError(RuntimeError):
    """Raised when the isolated continuity rehearsal is unsafe or incomplete."""


@dataclass(frozen=True)
class ThreeDayRehearsalReport:
    season_id: str
    model_mode: str
    days: tuple[dict[str, object], ...]
    continuity_evidence: tuple[dict[str, object], ...]
    model_calls: dict[str, int]
    audit: dict[str, int]
    event_counts: dict[str, int]
    unresolved: tuple[dict[str, str], ...]
    public_archive_sha256: str
    publication: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


async def run_live_three_day_rehearsal(
    root: str | Path,
    *,
    config: AppConfig,
    manifest: SceneModelManifest,
    resume: bool = False,
    client_factory: Callable[[str], ChatClient] | None = None,
) -> ThreeDayRehearsalReport:
    """Run nine isolated Aether scenes and verify cross-day continuity."""

    data_root = _validate_root(root, resume=resume)
    roots = DataRoots.from_root(data_root)
    roots.prepare()
    database = SQLiteDatabase(roots.state / "improv.sqlite3")
    database.migrate()
    clock = VirtualClock(datetime(2026, 9, 7, 13, tzinfo=timezone.utc))
    if resume:
        _validate_resume(database, config=config, manifest=manifest)
    else:
        _seed_live_aether_rehearsal(
            database,
            clock,
            config=config,
            manifest=manifest,
            season_id=THREE_DAY_REHEARSAL_SEASON_ID,
            days=THREE_DAY_REHEARSAL_DAYS,
            title="Live Aether three-day continuity rehearsal",
        )

    factory = LiveSceneFactory(
        # Technical rehearsal only; this does not establish orientation or consent.
        require_orientation=False,
        database=database,
        roots=roots,
        config=config,
        clock=clock,
        client_factory=client_factory,
        strict_rehearsal_acceptance=True,
    )
    coordinator = SeasonDayCoordinator(
        database=database,
        clock=clock,
        scene_factory=factory,
        strict_rehearsal_acceptance=True,
        strict_diary_word_count=True,
    )
    worker = DurableWorkflowWorker(
        database=database,
        clock=clock,
        scene_factory=factory,
        post_scene=coordinator.after_scene,
        close_day=coordinator.close_day,
        retry_non_transport_failures=False,
    )
    if resume:
        await _repair_missing_directions(
            database=database,
            factory=factory,
            coordinator=coordinator,
        )
    await _drain_three_days(
        worker=worker,
        database=database,
        clock=clock,
        resume=resume,
    )

    report = _report(database, roots)
    _validate_complete(report)
    (roots.state / "three-day-rehearsal-report.json").write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


async def _repair_missing_directions(
    *,
    database: SQLiteDatabase,
    factory: LiveSceneFactory,
    coordinator: SeasonDayCoordinator,
) -> None:
    """Retry only failed closed-day directions, never the completed scenes."""

    for day_number in range(1, THREE_DAY_REHEARSAL_DAYS + 1):
        day = database.connection.execute(
            "SELECT closed FROM days WHERE season_id = ? AND day_number = ?",
            (THREE_DAY_REHEARSAL_SEASON_ID, day_number),
        ).fetchone()
        if day is None or not bool(day["closed"]):
            continue
        target_day = day_number + 1
        existing = database.connection.execute(
            "SELECT 1 FROM domain_events WHERE aggregate_type = 'season' "
            "AND aggregate_id = ? AND event_type = 'NextDayDirectionCreated' "
            "AND CAST(json_extract(payload_json, '$.target_day_number') AS INTEGER) = ? LIMIT 1",
            (THREE_DAY_REHEARSAL_SEASON_ID, target_day),
        ).fetchone()
        if existing is not None:
            continue
        run_id = f"{THREE_DAY_REHEARSAL_SEASON_ID}-run-{(day_number * 3):02d}"
        await coordinator._write_direction_if_needed(
            season_id=THREE_DAY_REHEARSAL_SEASON_ID,
            day_number=day_number,
            run_id=run_id,
        )


def _validate_root(root: str | Path, *, resume: bool) -> Path:
    candidate = Path(root).expanduser().resolve(strict=False)
    if candidate == Path(candidate.anchor) or candidate in {Path.home(), Path("/tmp").resolve()}:
        raise ThreeDayRehearsalError("rehearsal root must be a dedicated child directory")
    if (
        candidate == PRODUCTION_DATA_ROOT
        or PRODUCTION_DATA_ROOT in candidate.parents
        or candidate in PRODUCTION_DATA_ROOT.parents
    ):
        raise ThreeDayRehearsalError("three-day rehearsal cannot use or contain production data")
    if resume:
        if not (candidate / "state" / "improv.sqlite3").is_file():
            raise ThreeDayRehearsalError("resume requires an existing isolated rehearsal database")
    elif candidate.exists() and any(candidate.iterdir()):
        raise ThreeDayRehearsalError("three-day rehearsal root must be new or empty")
    return candidate


def _validate_resume(
    database: SQLiteDatabase,
    *,
    config: AppConfig,
    manifest: SceneModelManifest,
) -> None:
    season = SeasonRepository(database).get(THREE_DAY_REHEARSAL_SEASON_ID)
    persisted = SceneModelManifest.model_validate(season.model_manifest)
    if persisted.model_dump(mode="json") != manifest.model_dump(mode="json"):
        raise ThreeDayRehearsalError("resume manifest does not match the existing rehearsal")
    validate_model_manifest(
        manifest,
        actor_ids=[member.character_id for member in season.cast],
        config=config,
    )


async def _drain_three_days(
    *,
    worker: DurableWorkflowWorker,
    database: SQLiteDatabase,
    clock: VirtualClock,
    resume: bool,
) -> None:
    records = RecordRepository(database)
    schedule = database.connection.execute(
        "SELECT r.run_id, r.status, s.scheduled_utc FROM runs r "
        "JOIN schedule_slots s ON s.slot_id = r.slot_id "
        "WHERE r.season_id = ? ORDER BY s.run_number",
        (THREE_DAY_REHEARSAL_SEASON_ID,),
    ).fetchall()
    for scheduled_row in schedule:
        run_id = str(scheduled_row["run_id"])
        original_status = str(records.get_run(run_id)["status"])
        if original_status == "COMPLETED" and resume:
            continue
        target = datetime.fromisoformat(str(scheduled_row["scheduled_utc"])).astimezone(timezone.utc)
        if resume:
            if original_status == "INTERRUPTED":
                WorkQueue(database).requeue_completed_for_manual_resume(
                    work_id=f"work:{run_id}",
                    available_at=target.isoformat(),
                )
            elif original_status == "RUNNING":
                WorkQueue(database).reclaim_leased_for_manual_resume(
                    work_id=f"work:{run_id}",
                    available_at=target.isoformat(),
                )
            queued = database.connection.execute(
                "SELECT available_at FROM work_items WHERE work_id = ? AND status = 'QUEUED'",
                (f"work:{run_id}",),
            ).fetchone()
            if queued is not None:
                target = max(
                    target,
                    datetime.fromisoformat(str(queued["available_at"])).astimezone(timezone.utc),
                )
        clock.set(target)
        resumed_interruption = resume and original_status == "INTERRUPTED"
        processed_after_resume = False
        for _ in range(64):
            current_status = str(records.get_run(run_id)["status"])
            if current_status in {"COMPLETED", "SKIPPED"} or (
                current_status == "INTERRUPTED"
                and (not resumed_interruption or processed_after_resume)
            ):
                break
            processed = await worker.drain_due(limit=1)
            if processed == 1:
                processed_after_resume = True
                if worker.results and worker.results[-1].status == "BLOCKED_BY_EARLIER_RUN":
                    return
                continue
            queued = database.connection.execute(
                "SELECT available_at FROM work_items WHERE status = 'QUEUED' "
                "ORDER BY available_at, priority, work_id LIMIT 1"
            ).fetchone()
            if queued is None:
                raise ThreeDayRehearsalError(f"no queued work remains for {run_id}")
            clock.set(datetime.fromisoformat(str(queued["available_at"])).astimezone(timezone.utc))
        else:
            raise ThreeDayRehearsalError(f"{run_id} did not reach a terminal state")


def _report(database: SQLiteDatabase, roots: DataRoots) -> ThreeDayRehearsalReport:
    days: list[dict[str, object]] = []
    for day_number in range(1, THREE_DAY_REHEARSAL_DAYS + 1):
        runs = [
            {
                "run_id": str(row["run_id"]),
                "slot_number": int(row["slot_number"]),
                "status": str(row["status"]),
                "turn_count": int(row["turn_count"]),
                "completion_reason": str(row["completion_reason"] or ""),
            }
            for row in database.connection.execute(
                "SELECT r.run_id, r.status, r.turn_count, r.completion_reason, s.slot_number "
                "FROM runs r JOIN schedule_slots s ON s.slot_id = r.slot_id "
                "WHERE r.season_id = ? AND s.day_number = ? ORDER BY s.slot_number",
                (THREE_DAY_REHEARSAL_SEASON_ID, day_number),
            )
        ]
        diaries = [
            {
                "character_id": str(row["character_id"]),
                "status": str(row["status"]),
                "word_count": int(row["word_count"]) if row["word_count"] is not None else None,
            }
            for row in database.connection.execute(
                "SELECT character_id, status, word_count FROM diaries "
                "WHERE season_id = ? AND day_number = ? ORDER BY character_id",
                (THREE_DAY_REHEARSAL_SEASON_ID, day_number),
            )
        ]
        day = database.connection.execute(
            "SELECT closed FROM days WHERE season_id = ? AND day_number = ?",
            (THREE_DAY_REHEARSAL_SEASON_ID, day_number),
        ).fetchone()
        direction = database.connection.execute(
            "SELECT COUNT(*) FROM domain_events WHERE aggregate_type = 'season' "
            "AND aggregate_id = ? AND event_type = 'NextDayDirectionCreated' "
            "AND CAST(json_extract(payload_json, '$.target_day_number') AS INTEGER) = ?",
            (THREE_DAY_REHEARSAL_SEASON_ID, day_number + 1),
        ).fetchone()[0]
        days.append(
            {
                "day_number": day_number,
                "runs": runs,
                "diaries": diaries,
                "closed": bool(day and day["closed"]),
                "next_day_direction_recorded": bool(direction),
            }
        )

    status_counts = {
        str(row["status"]): int(row["count"])
        for row in database.connection.execute(
            "SELECT status, COUNT(*) AS count FROM model_calls GROUP BY status"
        )
    }
    audit_row = database.connection.execute(
        "SELECT "
        "SUM(acceptance_status = 'ACCEPTED') AS accepted, "
        "SUM(acceptance_status = 'REJECTED') AS rejected, "
        "SUM(status = 'COMPLETED' AND (parse_status IS NULL OR validation_status IS NULL "
        "OR acceptance_status IS NULL OR render_status IS NULL OR parse_status = 'PENDING' "
        "OR validation_status = 'PENDING' OR acceptance_status = 'PENDING' "
        "OR render_status = 'PENDING')) AS pending FROM model_calls"
    ).fetchone()
    event_counts = {
        str(row["event_type"]): int(row["count"])
        for row in database.connection.execute(
            "SELECT event_type, COUNT(*) AS count FROM domain_events GROUP BY event_type"
        )
    }
    unresolved: list[dict[str, str]] = []
    for row in database.connection.execute(
        "SELECT run_id, status FROM runs WHERE season_id = ? AND status != 'COMPLETED'",
        (THREE_DAY_REHEARSAL_SEASON_ID,),
    ):
        unresolved.append({"kind": "run", "id": str(row["run_id"]), "status": str(row["status"])})
    for row in database.connection.execute(
        "SELECT diary_id, status FROM diaries WHERE season_id = ? "
        "AND status NOT IN ('WRITTEN', 'LATE')",
        (THREE_DAY_REHEARSAL_SEASON_ID,),
    ):
        unresolved.append({"kind": "diary", "id": str(row["diary_id"]), "status": str(row["status"])})
    for row in database.connection.execute(
        "SELECT work_id, status FROM work_items WHERE status NOT IN ('COMPLETED', 'CANCELLED')"
    ):
        unresolved.append({"kind": "work", "id": str(row["work_id"]), "status": str(row["status"])})

    return ThreeDayRehearsalReport(
        season_id=THREE_DAY_REHEARSAL_SEASON_ID,
        model_mode="live selected models; isolated nonproduction three-day continuity rehearsal",
        days=tuple(days),
        continuity_evidence=_continuity_evidence(database),
        model_calls=status_counts,
        audit={key: int(audit_row[key] or 0) for key in ("accepted", "rejected", "pending")},
        event_counts=event_counts,
        unresolved=tuple(unresolved),
        public_archive_sha256=_tree_hash(roots.public),
        publication="not attempted; no public projection was created",
    )


def _continuity_evidence(database: SQLiteDatabase) -> tuple[dict[str, object], ...]:
    evidence: list[dict[str, object]] = []
    for day_number in (2, 3):
        run_number = ((day_number - 1) * 3) + 1
        run_id = f"{THREE_DAY_REHEARSAL_SEASON_ID}-run-{run_number:02d}"
        director_path = database.connection.execute(
            "SELECT prompt_path FROM model_calls WHERE run_id = ? "
            "AND purpose = 'director_plan_round:1' AND acceptance_status = 'ACCEPTED' "
            "ORDER BY attempt DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        actor_path = database.connection.execute(
            "SELECT prompt_path FROM model_calls WHERE run_id = ? "
            "AND purpose LIKE 'actor_turn:%:round:1' AND acceptance_status = 'ACCEPTED' "
            "ORDER BY started_at, call_id LIMIT 1",
            (run_id,),
        ).fetchone()
        director = _json_user_payload(str(director_path["prompt_path"])) if director_path else {}
        actor = _actor_private_payload(str(actor_path["prompt_path"])) if actor_path else {}
        evidence.append(
            {
                "day_number": day_number,
                "mission_clock": str(director.get("mission_clock", "")),
                "prior_canon_items": len(director.get("accepted_canon", [])),
                "previous_shared_outcome_present": bool(director.get("previous_shared_outcome")),
                "private_day_direction_present": bool(director.get("private_day_direction")),
                "actor_memory_items": len(actor.get("known_memory", [])),
                "actor_prior_canon_items": len(actor.get("accepted_canon", [])),
                "actor_previous_outcome_present": bool(actor.get("previous_shared_outcome")),
            }
        )
    return tuple(evidence)


def _json_user_payload(prompt_path: str) -> dict[str, object]:
    messages = json.loads(Path(prompt_path).read_text(encoding="utf-8"))
    for message in reversed(messages):
        if message.get("role") == "user":
            value = json.loads(str(message.get("content", "{}")))
            return value if isinstance(value, dict) else {}
    return {}


def _actor_private_payload(prompt_path: str) -> dict[str, object]:
    messages = json.loads(Path(prompt_path).read_text(encoding="utf-8"))
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = str(message.get("content", ""))
        prefix = "PRIVATE ACTOR CONTEXT\n"
        marker = "\nCURRENT SCENE\n"
        if content.startswith(prefix) and marker in content:
            value = json.loads(content[len(prefix) : content.index(marker)])
            return value if isinstance(value, dict) else {}
    return {}


def _validate_complete(report: ThreeDayRehearsalReport) -> None:
    if len(report.days) != THREE_DAY_REHEARSAL_DAYS:
        raise ThreeDayRehearsalError("the rehearsal requires exactly three days")
    for day in report.days:
        runs = day["runs"]
        diaries = day["diaries"]
        if len(runs) != 3 or any(
            run["status"] != "COMPLETED" or run["turn_count"] != 16 for run in runs
        ):
            raise ThreeDayRehearsalError(f"day {day['day_number']} did not complete three 16-turn runs")
        if len(diaries) != 4 or any(
            diary["status"] not in {"WRITTEN", "LATE"}
            or diary["word_count"] is None
            or not 300 <= diary["word_count"] <= 800
            for diary in diaries
        ):
            raise ThreeDayRehearsalError(f"day {day['day_number']} diaries are incomplete or out of target")
        if not day["closed"] or not day["next_day_direction_recorded"]:
            raise ThreeDayRehearsalError(f"day {day['day_number']} closure or direction is missing")
    if len(report.continuity_evidence) != 2 or any(
        not row["previous_shared_outcome_present"]
        or not row["private_day_direction_present"]
        or row["prior_canon_items"] < 1
        or row["actor_memory_items"] < 1
        or row["actor_prior_canon_items"] < 1
        or not row["actor_previous_outcome_present"]
        for row in report.continuity_evidence
    ):
        raise ThreeDayRehearsalError("day-two/day-three continuity context was not fully propagated")
    if report.audit["pending"] or report.unresolved:
        raise ThreeDayRehearsalError("the rehearsal has pending audit or unresolved durable work")
    if report.public_archive_sha256 != hashlib.sha256().hexdigest():
        raise ThreeDayRehearsalError("the private rehearsal created unexpected public output")


__all__ = [
    "THREE_DAY_REHEARSAL_DAYS",
    "THREE_DAY_REHEARSAL_SEASON_ID",
    "ThreeDayRehearsalError",
    "ThreeDayRehearsalReport",
    "run_live_three_day_rehearsal",
]
