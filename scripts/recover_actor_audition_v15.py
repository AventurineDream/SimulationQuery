"""Recover only v15's Day 2 post-scene work; never rerun scene generation."""

import asyncio
import fcntl
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from improv_troupe.application.actor_audition_rehearsal import (
    ACTOR_AUDITION_SEASON_ID, _all_canon, _episode_transcript, _report,
)
from improv_troupe.application.episode_resolution import EpisodeResolutionService
from improv_troupe.application.live_runtime import LiveSceneFactory, SceneModelManifest
from improv_troupe.application.season_days import SeasonDayCoordinator
from improv_troupe.clock import VirtualClock
from improv_troupe.config import AppConfig
from improv_troupe.infrastructure import DataRoots, SQLiteDatabase, SeasonRepository


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".rehearsal-data/actor-audition-v15-rotated-20260903"


def preserved_scene_snapshot(database):
    rows = database.connection.execute(
        "SELECT * FROM turns WHERE round_number <= 4 ORDER BY turn_id"
    ).fetchall()
    return [
        (dict(row), hashlib.sha256(Path(row["content_path"]).read_bytes()).hexdigest()
         if row["content_path"] else None)
        for row in rows
    ]


async def recover():
    roots = DataRoots.from_root(DATA)
    database = SQLiteDatabase(roots.state / "improv.sqlite3")
    runs = database.connection.execute("SELECT * FROM runs ORDER BY run_id").fetchall()
    if len(runs) != 4 or any(row["status"] != "COMPLETED" for row in runs):
        raise RuntimeError("Recovery requires all four scenes already completed")
    if database.connection.execute(
        "SELECT 1 FROM model_calls WHERE status='STREAMING' LIMIT 1"
    ).fetchone():
        raise RuntimeError("An active or unresolved streaming call prevents recovery")
    backup = roots.state / "before-postscene-recovery.sqlite3"
    if not backup.exists():
        with sqlite3.connect(backup) as destination:
            database.connection.backup(destination)
    original_scenes = preserved_scene_snapshot(database)
    config = AppConfig.load(ROOT / "rehearsals/actor-audition-v15-config.yaml")
    season = SeasonRepository(database).get(ACTOR_AUDITION_SEASON_ID)
    manifest = SceneModelManifest.model_validate(season.model_manifest)
    final_run = runs[-1]
    clock = VirtualClock(datetime.fromisoformat(final_run["actual_completed_at"]))
    factory = LiveSceneFactory(
        # Technical rehearsal only; this does not establish orientation or consent.
        require_orientation=False,
        database=database, roots=roots, config=config, clock=clock,
        strict_rehearsal_acceptance=True, sessions_per_day=2,
    )
    payload = {
        "season_id": ACTOR_AUDITION_SEASON_ID,
        "run_id": final_run["run_id"], "day_number": 2, "slot_number": 2,
    }
    scene = factory(payload)
    # execute() on a COMPLETED run only hydrates its persisted transcript.
    scene_result = await scene.execute()
    coordinator = SeasonDayCoordinator(
        database=database, clock=clock, scene_factory=factory,
        strict_rehearsal_acceptance=True, strict_diary_word_count=True,
        sessions_per_day=2, final_day_number=2,
    )
    print("Recovering missing Day 2 diaries; existing accepted diaries are skipped.", flush=True)
    await coordinator.after_scene(payload, scene, scene_result)
    print("Day 2 diary pass finished. Recovering missing terminal resolution.", flush=True)
    existing_resolution = database.connection.execute(
        "SELECT 1 FROM domain_events WHERE event_type='EpisodeResolutionCreated' AND aggregate_id=?",
        (ACTOR_AUDITION_SEASON_ID,),
    ).fetchone()
    if not existing_resolution:
        await EpisodeResolutionService(
            season_id=ACTOR_AUDITION_SEASON_ID, final_run_id=final_run["run_id"],
            opening=season.opening, private_plan=season.private_plan,
            orchestrator=scene.orchestrator,
        ).resolve(accepted_canon=_all_canon(database), final_transcript=_episode_transcript(database))
    if preserved_scene_snapshot(database) != original_scenes:
        raise RuntimeError("Scene preservation check failed")
    report = _report(database, roots, manifest).as_dict()
    report["recovery_scope"] = "Day 2 diaries and terminal resolution only; Day 1 rejections preserved"
    report["scene_preservation_verified"] = True
    report_path = roots.state / "actor-audition-recovery-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    with (DATA / "state/postscene-recovery.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(recover())
