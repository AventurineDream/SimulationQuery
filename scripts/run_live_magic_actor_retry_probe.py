#!/usr/bin/env python3
"""Probe one live actor correction after an explicitly scripted rejection.

Uses the scene service, validator, retry limit and roll persistence. Only the
correction calls the configured server; setup and the rejected original are
marked scripted-fixture in the audit. This is not a full-scene rehearsal.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from improv_troupe.application.live_runtime import LiveSceneFactory, validate_model_manifest
from improv_troupe.clock import VirtualClock
from improv_troupe.config import AppConfig
from improv_troupe.infrastructure import DataRoots, SQLiteDatabase
from improv_troupe.llm import ScriptedFakeClient, ScriptedStream

from run_live_magic_dice_rehearsal import (
    ACTOR_IDS, LOCKED_OPENING_PLAN, MAGIC_FORBIDDEN_ATTEMPT_TERMS, _force_outcome_tier,
)
from run_live_porch_rehearsal import (
    _manifest, _run_row, _seed_variant, _terminalize_rehearsal_season, _validate_root,
)


async def _run(args: argparse.Namespace) -> dict[str, object]:
    root = _validate_root(args.data_root)
    config = AppConfig.load(args.config)
    manifest = _manifest(args.manifest)
    validate_model_manifest(manifest, actor_ids=list(ACTOR_IDS), config=config)
    roots = DataRoots.from_root(root)
    roots.prepare()
    database = SQLiteDatabase(roots.state / "improv.sqlite3")
    database.migrate()
    clock = VirtualClock(datetime(2026, 9, 20, 13, tzinfo=timezone.utc))
    season_id, run_id = _seed_variant(
        database, manifest=manifest, variant_id="R1",
        strategy="actor_retry_probe", strategy_description=f"Synthetic {args.case} rejection.",
        clock=clock, dice_trial=True,
    )
    factory = LiveSceneFactory(
        # Technical rehearsal only; this does not establish orientation or consent.
        require_orientation=False,
        database=database, roots=roots, config=config, clock=clock,
        strict_rehearsal_acceptance=True, sessions_per_day=1,
    )
    scene = factory({"season_id": season_id, "run_id": run_id})
    scene.max_rounds = 1
    scene.max_actor_turns = 1
    scene.forbidden_magic_attempt_terms = MAGIC_FORBIDDEN_ATTEMPT_TERMS
    plan = LOCKED_OPENING_PLAN
    if args.case == "no_challenge":
        plan = plan.model_copy(update={"magic_challenge": None, "magic_success_criteria": None})
    scene.orchestrator.client = ScriptedFakeClient([
        ScriptedStream((plan.model_dump_json(),)),
        ScriptedStream((json.dumps({"narration": "A breeze rustles the porch awning."}),)),
    ])
    scene.orchestrator.backend = "scripted-fixture"
    scene.orchestrator.model = "locked-opening-fixture"
    actor = scene.actors[0]
    # Preserve all four cast members in context/safety checks, but execute only
    # Mara's slot even when her correction is rejected. Never fall through to
    # an unplanned live call for one of the other actors.
    scene._ordered_actors = lambda **kwargs: [actor]
    live_client, live_backend, live_model = actor.executor.client, actor.executor.backend, actor.executor.model
    original_text = (
        "I watch the cheetah from the kitchen doorway, concluding that its raised paw means a sprain."
        if args.case == "premature_result"
        else "I compare the time stamps on my porch-camera notes."
    )
    actor.executor.client = ScriptedFakeClient([
        ScriptedStream((json.dumps({
            "text": original_text,
            "magic_stat": "Intellect",
            "magic_method": "I compare the visible movement without deciding what it means.",
        }),))
    ])
    actor.executor.backend = "scripted-fixture"
    actor.executor.model = "rejected-actor-fixture"
    original_call_actor = scene._call_actor

    async def call_actor(current_actor, round_number, **kwargs):
        if kwargs.get("correction_reason"):
            current_actor.executor.client = live_client
            current_actor.executor.backend = live_backend
            current_actor.executor.model = live_model
        return await original_call_actor(current_actor, round_number, **kwargs)

    scene._call_actor = call_actor
    control = _force_outcome_tier(scene, "setback") if args.case == "premature_result" else None
    error = None
    try:
        await scene.execute()
        _terminalize_rehearsal_season(database, season_id=season_id, clock=clock)
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    durable = _run_row(database, run_id)
    calls = [dict(row) for row in database.connection.execute(
        "SELECT call_id,backend,model,purpose,acceptance_status,validator_code,correction_of_call_id "
        "FROM model_calls ORDER BY rowid"
    )]
    live_calls = [call for call in calls if call["backend"] != "scripted-fixture"]
    expected_rolls = 1 if args.case == "premature_result" else 0
    passed = (
        error is None and durable["status"] == "COMPLETED"
        and durable["turn_count"] == 1 and durable["completion_reason"] == "turn_limit"
        and len(live_calls) == 1 and live_calls[0]["acceptance_status"] == "ACCEPTED"
        and len(durable["rolls"]) == expected_rolls
        and durable["diary_count"] == 0 and durable["cheetah_turn_count"] == 0
    )
    report = {
        "execution_type": "scripted_rejection_with_one_live_actor_correction",
        "case": args.case, "status": "PASS" if passed else "FAIL",
        "status_scope": "mechanical_contract_only",
        "quality_status": "HUMAN_REVIEW_REQUIRED",
        "model_manifest": manifest.model_dump(mode="json"),
        "fixture_original": original_text, "calls": calls, "durable": durable,
        "forced_roll": control, "error": error,
        "limitations": [
            "Opening and rejected original are scripted, not live model output.",
            "One correction case is not a live reliability rate.",
            "Post-roll consequence and diaries are not exercised.",
            "Semantic fidelity of the corrected prose requires review.",
        ],
    }
    (roots.state / "actor-retry-probe-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--case", choices=("premature_result", "no_challenge"), required=True)
    report = asyncio.run(_run(parser.parse_args()))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
