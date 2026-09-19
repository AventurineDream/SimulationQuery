"""Operator-approved checkpoint recovery for the two connection-failed auditions."""
import asyncio
import fcntl
import json
import sqlite3
import traceback
from datetime import datetime, timezone
from pathlib import Path

from improv_troupe.application.actor_audition_rehearsal import (
    ACTOR_AUDITION_SEASON_ID as SID, _audition_scene_factory,
    _all_canon, _episode_transcript, _drain, _report,
)
from improv_troupe.application.episode_resolution import EpisodeResolutionService
from improv_troupe.application.live_runtime import SceneModelManifest
from improv_troupe.application.season_days import SeasonDayCoordinator
from improv_troupe.application.worker import DurableWorkflowWorker
from improv_troupe.clock import VirtualClock
from improv_troupe.config import AppConfig
from improv_troupe.infrastructure import DataRoots, SQLiteDatabase, SeasonRepository, WorkQueue
from recover_actor_audition_v15 import preserved_scene_snapshot

ROOT = Path(__file__).resolve().parents[1]


async def recover(version):
    data = ROOT / f".rehearsal-data/actor-audition-v{version}-director-rotation-20260904"
    roots = DataRoots.from_root(data)
    if not (roots.state / "improv.sqlite3").is_file():
        raise RuntimeError("Existing recovery database required")
    database = SQLiteDatabase(roots.state / "improv.sqlite3")
    if database.connection.execute("SELECT 1 FROM model_calls WHERE status='STREAMING'").fetchone():
        raise RuntimeError("Unresolved streaming call prevents recovery")
    runs = database.connection.execute(
        "SELECT r.*,s.day_number,s.slot_number,s.scheduled_utc FROM runs r "
        "JOIN schedule_slots s ON s.slot_id=r.slot_id ORDER BY s.run_number"
    ).fetchall()
    if len(runs) != 4 or any(row["season_id"] != SID for row in runs):
        raise RuntimeError("Unexpected recovery target")
    for row in runs:
        if row["status"] == "INTERRUPTED":
            last = database.connection.execute(
                "SELECT error_type FROM model_calls WHERE run_id=? ORDER BY rowid DESC LIMIT 1",
                (row["run_id"],),
            ).fetchone()
            if not last or last[0] not in {"ConnectError", "ReadTimeout", "ConnectTimeout", "TimeoutError"}:
                raise RuntimeError("Non-transport interruption requires separate review")
    backup = roots.state / "before-connection-recovery.sqlite3"
    if not backup.exists():
        with sqlite3.connect(backup) as target:
            database.connection.backup(target)
    preserved = preserved_scene_snapshot(database)
    private_ids = {row[0] for row in database.connection.execute(
        "SELECT diary_id FROM diaries WHERE status='PRIVATE'"
    )}

    class RecoveryCoordinator(SeasonDayCoordinator):
        def _diary_repairable(self, diary_id):
            return diary_id not in private_ids and super()._diary_repairable(diary_id)

    config = AppConfig.load(ROOT / f"rehearsals/actor-audition-v{version}-config.yaml")
    season = SeasonRepository(database).get(SID)
    manifest = SceneModelManifest.model_validate(season.model_manifest)
    clock = VirtualClock(datetime.fromisoformat(runs[0]["scheduled_utc"]))
    factory = _audition_scene_factory(database, roots, config, clock)
    coordinator = RecoveryCoordinator(
        database=database, clock=clock, scene_factory=factory,
        strict_rehearsal_acceptance=True, strict_diary_word_count=True,
        sessions_per_day=2, final_day_number=2,
    )

    async def after_scene(payload, scene, result):
        if int(payload["slot_number"]) != 2:
            return
        print(f"v{version}: post-scene recovery for {payload['run_id']}", flush=True)
        await coordinator.after_scene(payload, scene, result)
        if int(payload["day_number"]) == 2 and not database.connection.execute(
            "SELECT 1 FROM domain_events WHERE event_type='EpisodeResolutionCreated'"
        ).fetchone():
            await EpisodeResolutionService(
                season_id=SID, final_run_id=str(payload["run_id"]),
                opening=season.opening, private_plan=season.private_plan,
                orchestrator=scene.orchestrator,
            ).resolve(accepted_canon=_all_canon(database), final_transcript=_episode_transcript(database))

    try:
        # Completed scenes only hydrate their saved transcript. Restore missing
        # post-scene work before any later scene can acquire day-direction context.
        for row in runs:
            if row["status"] == "COMPLETED" and row["slot_number"] == 2:
                clock.set(datetime.fromisoformat(row["scheduled_utc"]))
                payload = {"season_id": SID, "run_id": row["run_id"],
                           "day_number": row["day_number"], "slot_number": row["slot_number"]}
                scene = factory(payload)
                await after_scene(payload, scene, await scene.execute())
        queue = WorkQueue(database)
        # Old worker has exited (operator preflight). Retain queue attempts and
        # receipts while releasing its abandoned leases for this isolated root.
        for item in database.connection.execute("SELECT * FROM work_items WHERE status='LEASED'").fetchall():
            queue.release(work_id=item["work_id"], worker_id=item["lease_owner"],
                          available_at=runs[0]["scheduled_utc"])
        for row in runs:
            if row["status"] == "INTERRUPTED":
                queue.requeue_completed_for_manual_resume(
                    work_id=f"work:{row['run_id']}", available_at=row["scheduled_utc"]
                )
        worker = DurableWorkflowWorker(
            database=database, clock=clock, scene_factory=factory,
            post_scene=after_scene, close_day=coordinator.close_day,
            retry_non_transport_failures=False,
        )
        print(f"v{version}: resuming remaining scenes", flush=True)
        await _drain(worker, database, clock)
    finally:
        current = {row[0]["turn_id"]: row for row in preserved_scene_snapshot(database)}
        unchanged = all(current.get(row[0]["turn_id"]) == row for row in preserved)
        report = _report(database, roots, manifest).as_dict()
        report["prior_scene_preservation_verified"] = unchanged
        report["recovery_scope"] = "Connection recovery; previously rejected private diaries preserved"
        report["recovery_checked_at"] = datetime.now(timezone.utc).isoformat()
        (roots.state / "actor-audition-recovery-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        if not unchanged:
            raise RuntimeError("Prior scene preservation verification failed")
    print(f"v{version}: recovery pass finished; resolution={bool(report['resolution'])}, "
          f"unresolved={report['unresolved']}", flush=True)


async def main():
    failed = False
    for version in (18, 19):
        try:
            print(f"Starting v{version} recovery", flush=True)
            await recover(version)
        except Exception:
            traceback.print_exc()
            failed = True
    return int(failed)


if __name__ == "__main__":
    with (ROOT / ".rehearsal-data/v18-v19-recovery.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        raise SystemExit(asyncio.run(main()))
