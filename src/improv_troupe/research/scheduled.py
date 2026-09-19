"""Single-world scheduled collection: real-clock, serialized, stop on faults."""
from __future__ import annotations

import asyncio
import fcntl
import json
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ..application.actor_audition_rehearsal import _seed, _audition_scene_factory
from ..application.season_days import SeasonDayCoordinator
from ..application.worker import DurableWorkflowWorker
from ..clock import SystemClock
from ..infrastructure import DataRoots, SQLiteDatabase, WorkQueue
from ..llm.audit import AuditWriter
from .pilot import prepare, load_frozen, snapshot, run_probes
from .transport import ResearchOllamaClient, ResearchTransportError, dumps

SEASON_ID = "SQ-PILOT2-RETRY-20260906"
PACIFIC = ZoneInfo("America/Los_Angeles")
STANDARD_TIMES = ("06:00", "12:00", "18:00")


def _relocate_continuation_artifacts(connection, *, old_data_root: Path, new_data_root: Path) -> dict[str, int]:
    """Relink copied absolute artifact paths to an isolated continuation root."""

    old_prefix = str(old_data_root.resolve())
    new_prefix = str(new_data_root.resolve())
    if old_prefix == new_prefix:
        return {}
    targets = {
        "model_calls": ("prompt_path", "output_path", "parsed_path", "validated_path", "accepted_path", "rendered_path"),
        "turns": ("content_path",),
        "diaries": ("content_path",),
        "domain_events": ("payload_json",),
    }
    changed: dict[str, int] = {}
    for table, columns in targets.items():
        available = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
        for column in columns:
            if column not in available:
                continue
            cursor = connection.execute(
                f"UPDATE {table} SET {column}=replace({column}, ?, ?) "
                f"WHERE instr(COALESCE({column}, ''), ?) > 0",
                (old_prefix, new_prefix, old_prefix),
            )
            if cursor.rowcount:
                changed[f"{table}.{column}"] = int(cursor.rowcount)
    return changed


def _phase_spine(total_runs: int) -> tuple[str, ...]:
    """Stretch the four-phase story spine across the selected run count."""
    if total_runs < 4:
        raise ValueError("scheduled collection requires at least four runs")
    names = ("inciting_commitment", "complication_cost", "reversal_crisis", "climax_choice")
    base, remainder = divmod(total_runs, len(names))
    lengths = [base] * len(names)
    for index in range(len(names) - remainder, len(names)):
        lengths[index] += 1
    return tuple(name for name, length in zip(names, lengths) for _ in range(length))


def prepare_scheduled(
    root, *, repo, config_path, manifest_path, requested_at=None,
    season_id=SEASON_ID, start_date=None, days=7, sessions_per_day=3,
    immediate_run_numbers=(1, 2),
):
    now = requested_at or datetime.now(timezone.utc)
    days = int(days)
    sessions_per_day = int(sessions_per_day)
    if days < 1 or days > 7:
        raise ValueError("days must be between 1 and 7")
    if sessions_per_day < 1 or sessions_per_day > len(STANDARD_TIMES):
        raise ValueError(f"sessions_per_day must be between 1 and {len(STANDARD_TIMES)}")
    start_date = start_date or now.astimezone(PACIFIC).date()
    if not isinstance(start_date, date):
        raise TypeError("start_date must be a date")
    if days == 6 and start_date.weekday() != 6:
        raise ValueError("the six-day schedule must start on Sunday and end on Friday")
    if days == 6 and (start_date + timedelta(days=days - 1)).weekday() != 4:
        raise ValueError("the six-day schedule must end on Friday")
    total_runs = days * sessions_per_day
    immediate_run_numbers = tuple(sorted({int(number) for number in immediate_run_numbers}))
    if any(number < 1 or number > total_runs for number in immediate_run_numbers):
        raise ValueError("immediate run numbers must be within the scheduled run range")
    schedule = {
        "start_date": start_date.isoformat(), "days": days,
        "sessions_per_day": sessions_per_day, "total_runs": total_runs,
        "timezone": "America/Los_Angeles", "standard_times": list(STANDARD_TIMES[:sessions_per_day]),
        "calendar": "sun-friday" if days == 6 else "custom",
        "immediate_run_numbers": list(immediate_run_numbers),
        "immediate_at_utc": now.isoformat() if immediate_run_numbers else None,
        "season_id": season_id, "director_context_policy": "daily-director-excerpts-v1",
        "scene_wall_time_limit": False, "diary_thinking": "low",
    }
    spec = prepare(root, repo=repo, config_path=config_path, manifest_path=manifest_path, schedule=schedule)
    spec, config, manifest = load_frozen(root, repo, config_path)
    world_root = root / "worlds" / spec["worlds"][0]["id"]
    roots = DataRoots.from_root(world_root)
    roots.prepare()
    db = SQLiteDatabase(roots.state / "improv.sqlite3")
    db.migrate()
    try:
        _seed(db, SystemClock(), config=config, manifest=manifest, season_id=season_id,
              start_date=date.fromisoformat(schedule["start_date"]), days=days,
              sessions_per_day=sessions_per_day)
        # Preserve original immutable slot positions. Explicit dispatch overrides
        # belong to the work queue and frozen amendment, never fabricated clocks.
        with db.transaction() as connection:
            for n in immediate_run_numbers:
                connection.execute("UPDATE work_items SET available_at=? WHERE work_id=?",
                                   (now.isoformat(), f"work:{season_id}-run-{n:02d}"))
        AuditWriter(root).write_text("schedule.json", dumps([dict(r) for r in db.connection.execute(
            "SELECT s.run_number,s.day_number,s.slot_number,s.scheduled_local,w.available_at "
            "FROM schedule_slots s JOIN work_items w ON w.work_id='work:'||s.slot_id ORDER BY s.run_number")]))
    finally:
        db.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.connection.close()
    return spec


def authorize_scheduled_resume(
    root: Path,
    *,
    repo: Path,
    config_path: Path,
    run_id: str,
    reason: str,
    authorized_at: datetime | None = None,
):
    """Authorize one explicit continuation after a stopped scheduled run.

    The original stopped root is expected to remain untouched by the caller.
    This operation is intended for an explicitly cloned continuation root. It
    preserves the failed attempt, creates a SQLite backup, reopens only the
    named completed queue receipt, and records an immutable authorization file.
    """

    root = root.resolve()
    if not reason.strip():
        raise ValueError("resume reason must not be empty")
    authorization_time = authorized_at or datetime.now(timezone.utc)
    if authorization_time.tzinfo is None:
        raise ValueError("authorized_at must be timezone-aware")
    with (root / "scheduler.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        spec, config, manifest = load_frozen(root, repo, config_path)
        if "schedule" not in spec:
            raise ValueError("not a scheduled experiment")
        if (root / "resume-pending.json").exists():
            raise ValueError("a scheduled resume is already pending")
        existing_authorization_path = root / "resume-authorized.json"
        existing_consumed_path = root / "resume-consumed.json"
        prior_resume = None
        if existing_authorization_path.exists():
            if not existing_consumed_path.exists():
                raise ValueError("a scheduled resume is already authorized")
            prior_resume = json.loads(existing_authorization_path.read_text())
            if str(prior_resume.get("run_id")) != run_id:
                raise ValueError("a second scheduled resume must target the prior resume run")
        stopped_path = root / "STOPPED.json"
        if not stopped_path.exists():
            raise ValueError("scheduled resume requires STOPPED.json")
        world = spec["worlds"][0]
        world_root = root / "worlds" / world["id"]
        roots = DataRoots.from_root(world_root)
        db_path = roots.state / "improv.sqlite3"
        db = SQLiteDatabase(db_path)
        db.migrate()
        try:
            continuation = spec.get("continuation", {})
            parent_root = continuation.get("parent_root") if isinstance(continuation, dict) else None
            path_relocations = {}
            if parent_root:
                with db.transaction() as connection:
                    path_relocations = _relocate_continuation_artifacts(
                        connection,
                        old_data_root=Path(str(parent_root)) / "data",
                        new_data_root=root,
                    )
            row = db.connection.execute(
                "SELECT r.run_id,r.status,r.turn_count,w.status AS work_status,w.completed_at "
                "FROM runs r JOIN work_items w ON w.work_id='work:'||r.run_id "
                "WHERE r.run_id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown scheduled run: {run_id}")
            if str(row["status"]) != "INTERRUPTED":
                raise ValueError(f"resume requires an INTERRUPTED run, found {row['status']}")
            if str(row["work_status"]) != "COMPLETED":
                raise ValueError(f"resume requires a completed queue receipt, found {row['work_status']}")
            first_open = db.connection.execute(
                "SELECT r.run_id FROM runs r JOIN schedule_slots s ON s.slot_id=r.slot_id "
                "WHERE r.season_id=? AND r.status NOT IN ('COMPLETED','SKIPPED') "
                "ORDER BY s.run_number LIMIT 1",
                (world.get("season_id") or spec["schedule"]["season_id"],),
            ).fetchone()
            if first_open is not None and str(first_open["run_id"]) != run_id:
                raise ValueError(f"earlier unresolved run must be resumed first: {first_open['run_id']}")
            active = db.connection.execute(
                "SELECT call_id,status FROM model_calls WHERE status IN "
                "('STREAMING','WAITING_FOR_MODEL','VALIDATING') LIMIT 1"
            ).fetchone()
            if active is not None:
                raise ValueError(f"active model call prevents resume: {active['call_id']}")
            recovery = db.connection.execute(
                "SELECT recovery_id,status FROM recovery_requests WHERE status IN "
                "('WAITING_FOR_MODEL','RECOVERY_REQUIRED') LIMIT 1"
            ).fetchone()
            if recovery is not None:
                raise ValueError(f"active recovery prevents scheduled resume: {recovery['recovery_id']}")
            attempt_marker = root / "attempts" / f"{run_id}.json"
            completed_marker = root / "completed" / f"{run_id}.json"
            if not attempt_marker.exists() or completed_marker.exists():
                raise ValueError("resume requires the preserved incomplete attempt marker")
            db.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            stamp = authorization_time.strftime("%Y%m%dT%H%M%SZ")
            resume_number = int(prior_resume.get("resume_number", 1)) + 1 if prior_resume else 1
            backup_path = roots.state / f"improv.before-resume-{stamp}.sqlite3"
            preserved_stop_path = root / (
                "STOPPED.before-resume.json"
                if prior_resume is None
                else f"STOPPED.before-resume-{stamp}.json"
            )
            preserved_result_path = world_root / (
                "result.before-resume.json"
                if prior_resume is None
                else f"result.before-resume-{stamp}.json"
            )
            shutil.copy2(db_path, backup_path)
            before = {
                "run_id": run_id,
                "run_status": str(row["status"]),
                "turn_count": int(row["turn_count"]),
                "work_status": str(row["work_status"]),
                "stopped": json.loads(stopped_path.read_text()),
                "resume_number": resume_number,
                "authorized_at_utc": authorization_time.isoformat(),
            }
            authorization = {
                "status": "AUTHORIZED",
                "run_id": run_id,
                "resume_number": resume_number,
                "reason": reason,
                "authorized_at_utc": authorization_time.isoformat(),
                "sqlite_backup": str(backup_path),
                "preserved_stop_marker": str(preserved_stop_path),
                "preserved_result": str(preserved_result_path),
                "prior_attempt": str(attempt_marker),
                "source_experiment_id": spec["experiment_id"],
                "path_relocations": path_relocations,
            }
            pending_path = root / "resume-pending.json"
            AuditWriter(root).write_text(
                pending_path.name,
                dumps({**authorization, "before": before}),
            )
            if prior_resume is not None:
                existing_authorization_path.rename(
                    root / f"resume-authorized.before-resume-{stamp}.json"
                )
                existing_consumed_path.rename(
                    root / f"resume-consumed.before-resume-{stamp}.json"
                )
            stopped_path.rename(preserved_stop_path)
            result_path = world_root / "result.json"
            if result_path.exists():
                result_path.rename(preserved_result_path)
            reopened = WorkQueue(db).requeue_completed_for_manual_resume(
                work_id=f"work:{run_id}", available_at=authorization_time.isoformat()
            )
            if not reopened:
                raise ValueError("the stopped run queue receipt could not be reopened")
            pending_path.rename(root / "resume-authorized.json")
            return {"status": "AUTHORIZED", "run_id": run_id, "sqlite_backup": str(backup_path)}
        finally:
            db.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.connection.close()


async def tick(root, *, repo, config_path, client_type=ResearchOllamaClient, clock=None):
    """Called periodically by the host. Lock spans all model calls and post-work."""
    root = root.resolve()
    with (root / "scheduler.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status": "BUSY"}
        spec, config, manifest = load_frozen(root, repo, config_path)
        if "schedule" not in spec:
            raise ValueError("not a scheduled experiment")
        if (root / "resume-pending.json").exists():
            return {"status": "RESUME_PENDING"}
        resume_record = None
        resume_path = root / "resume-authorized.json"
        if resume_path.exists():
            resume_record = json.loads(resume_path.read_text())
        resume_target = str(resume_record["run_id"]) if resume_record else None
        resume_consumed = (root / "resume-consumed.json").exists()
        if (root / "STOPPED.json").exists() and (resume_record is None or resume_consumed):
            return {"status": "STOPPED"}
        if (root / "parents-complete.json").exists():
            return {"status": "COMPLETED"}
        identity = json.loads((root / "identity.json").read_text())
        world = spec["worlds"][0]
        world_root = root / "worlds" / world["id"]
        audit = AuditWriter(root)
        roots = DataRoots.from_root(world_root)
        db = SQLiteDatabase(roots.state / "improv.sqlite3")
        clock = clock or SystemClock()
        client = client_type(config.backend("local"), roots.private / "provider",
                             world_id=world["id"], seed=world["seed"])
        client.bounded_daily_context = True
        client.diary_thinking = spec["schedule"].get("diary_thinking")
        base = _audition_scene_factory(db, roots, config, clock, lambda _: client)
        schedule = spec["schedule"]
        days = int(schedule.get("days", 7))
        sessions_per_day = int(schedule.get("sessions_per_day", 3))
        total_runs = days * sessions_per_day
        base.sessions_per_day = sessions_per_day
        # Stretch the existing four-phase spine across the selected schedule,
        # avoiding an artificial climax on an early day. Freeze this before the
        # first request.
        base.episode_phases = _phase_spine(total_runs)
        def factory(payload):
            scene = base(payload)
            scene.enforce_wall_time_limit = False
            scene.round_observer = lambda s, n: snapshot(s, n, world_root=world_root, world_id=world["id"], spec=spec)
            return scene
        coordinator = SeasonDayCoordinator(database=db, clock=clock, scene_factory=factory,
                                           strict_rehearsal_acceptance=True, strict_diary_word_count=True,
                                           sessions_per_day=sessions_per_day, final_day_number=days)
        async def after_scene(payload, scene, result):
            if int(payload["slot_number"]) == sessions_per_day:
                await coordinator.after_scene(payload, scene, result)
            if client.failed:
                raise ResearchTransportError("post-scene transport failed")
        worker = DurableWorkflowWorker(database=db, clock=clock, scene_factory=factory,
                                       post_scene=after_scene, close_day=coordinator.close_day,
                                       auto_retry_timeouts=False, retry_non_transport_failures=False)
        completed = []
        try:
            incomplete_attempts = [
                p for p in (root / "attempts").glob("*.json")
                if not (root / "completed" / p.name).exists()
            ]
            if incomplete_attempts and not (
                resume_target
                and not resume_consumed
                and [p.name for p in incomplete_attempts] == [f"{resume_target}.json"]
            ):
                raise ResearchTransportError("unfinished prior scene or post-scene attempt; no automatic resume")
            while True:
                row = db.connection.execute(
                    "SELECT r.run_id,r.status,w.status AS work_status,w.available_at FROM runs r JOIN schedule_slots s ON s.slot_id=r.slot_id "
                    "JOIN work_items w ON w.work_id='work:'||r.run_id WHERE r.status!='COMPLETED' ORDER BY s.run_number LIMIT 1"
                ).fetchone()
                if row is None:
                    result = {"world_id": world["id"], "status": "COMPLETED"}
                    AuditWriter(world_root).write_text("result.json", dumps(result))
                    audit.write_text("parents-complete.json", dumps([result]))
                    return {"status": "COMPLETED", "runs": completed}
                marker = root / "attempts" / f"{row['run_id']}.json"
                resuming_target = (
                    resume_target
                    and not resume_consumed
                    and str(row["run_id"]) == resume_target
                    and str(row["status"]) == "INTERRUPTED"
                    and str(row["work_status"]) == "QUEUED"
                )
                if (marker.exists() and not resuming_target) or (
                    row["status"] != "QUEUED" and not resuming_target
                ) or str(row["work_status"]) != "QUEUED":
                    raise ResearchTransportError("incomplete prior attempt; no automatic resume")
                if datetime.fromisoformat(row["available_at"]) > clock.now():
                    return {"status": "SCHEDULED", "next_run": row["run_id"], "due_at": row["available_at"], "runs": completed}
                if resuming_target:
                    audit.write_text(
                        "resume-consumed.json",
                        dumps({"run_id": row["run_id"], "started_at_utc": clock.now().isoformat()}),
                    )
                if await client.identity(list(identity["models"])) != identity:
                    raise ResearchTransportError("model/server identity drift")
                if not marker.exists():
                    audit.write_text(marker.relative_to(root), dumps({"started_at_utc": clock.now().isoformat(), "run_id": row["run_id"]}))
                elif resuming_target:
                    resume_number = int(resume_record.get("resume_number", 1)) if resume_record else 1
                    audit.write_text(
                        Path("resumes") / f"{row['run_id']}-resume-{resume_number}.json",
                        dumps({
                            "started_at_utc": clock.now().isoformat(),
                            "run_id": row["run_id"],
                            "resume_number": resume_number,
                            "prior_attempt": str(marker),
                        }),
                    )
                # A due CLOSE_DAY may precede RUN_SCENE; do not mistake it for
                # the requested scene or advance to the next scene prematurely.
                for _ in range(10):
                    if await worker.drain_due(limit=1) != 1 or client.failed:
                        raise ResearchTransportError("due work failed or disappeared")
                    if worker.results[-1].kind == "RUN_SCENE":
                        break
                else:
                    raise ResearchTransportError("scene was not reached")
                state = db.connection.execute("SELECT status FROM runs WHERE run_id=?", (row["run_id"],)).fetchone()[0]
                if state != "COMPLETED" or worker.results[-1].status != "COMPLETED":
                    raise ResearchTransportError(f"scene ended {state}; no retry or later scene")
                completed.append(row["run_id"])
                audit.write_text(f"completed/{row['run_id']}.json", dumps({"at": clock.now().isoformat()}))
        except Exception as exc:
            result = {"world_id": world["id"], "status": "INCOMPLETE", "error": type(exc).__name__,
                      "detail": str(exc) if isinstance(exc, ResearchTransportError) else None,
                      "at": clock.now().isoformat()}
            audit.write_text("STOPPED.json", dumps(result))
            AuditWriter(world_root).write_text("result.json", dumps(result))
            return {"status": "STOPPED", "error": result}
        finally:
            db.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.connection.close()


async def finish_probes(root, *, repo, config_path):
    if not (root / "probes-started.json").exists():
        return await run_probes(root, repo=repo, config_path=config_path)
    return {"status": "ALREADY_ATTEMPTED"}
