#!/usr/bin/env python3
"""Run one isolated MAGIC scene followed by the private diary workflow.

This is a nonproduction follow-up to the accepted no-diary MAGIC rehearsal. It
keeps the scene, models, forced roll, and safety validators the same, then adds
one final daily slot so every active actor receives a real diary opportunity.
Diary text is written to the private audit archive and is intentionally omitted
from the JSON receipt. The rehearsal also enables sentence-level claim audits.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from improv_troupe.application.live_runtime import LiveSceneFactory, validate_model_manifest
from improv_troupe.application.season_days import SeasonDayCoordinator
from improv_troupe.clock import VirtualClock
from improv_troupe.config import AppConfig
from improv_troupe.domain import SeasonStatus
from improv_troupe.infrastructure import DataRoots, SQLiteDatabase

from run_live_magic_dice_rehearsal import (
    ACTOR_IDS,
    LOCKED_OPENING_PLAN,
    MAGIC_FORBIDDEN_ATTEMPT_TERMS,
    MAGIC_FORBIDDEN_RESULT_TERMS,
    MAGIC_TRIAL_CHALLENGE,
    TARGET_TOTALS,
    _contains_forbidden_result_term,
    _derive_runtime_adjudication,
    _force_outcome_tier,
    _manifest,
    _outcome_contract_matches,
    _run_row,
    _runtime_adjudication_matches,
    _seed_variant,
    _terminalize_rehearsal_season,
    _validate_root,
)


PACIFIC = ZoneInfo("America/Los_Angeles")


def _configure_scene(scene) -> None:
    """Apply the exact accepted no-diary MAGIC scene constraints."""

    scene.max_rounds = 2
    scene.max_actor_turns = 8
    scene.require_magic_challenge = True
    scene.required_magic_next_actor = "Mara Bell"
    scene.required_magic_challenge_text = MAGIC_TRIAL_CHALLENGE
    scene.required_magic_modifier = 0
    scene.required_magic_opening_plan = LOCKED_OPENING_PLAN
    scene.forbidden_magic_attempt_terms = MAGIC_FORBIDDEN_ATTEMPT_TERMS
    scene.forbidden_magic_result_terms = MAGIC_FORBIDDEN_RESULT_TERMS


def _event_payloads(database: SQLiteDatabase, *, run_id: str, event_type: str) -> list[dict[str, object]]:
    rows = database.connection.execute(
        "SELECT payload_json FROM domain_events WHERE aggregate_id = ? AND event_type = ? "
        "ORDER BY created_at, event_id",
        (run_id, event_type),
    ).fetchall()
    payloads: list[dict[str, object]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _model_calls(database: SQLiteDatabase) -> list[dict[str, object]]:
    rows = database.connection.execute(
        "SELECT call_id, run_id, purpose, attempt, status, acceptance_status, "
        "validator_code, validator_detail, prompt_path, output_path "
        "FROM model_calls ORDER BY rowid"
    ).fetchall()
    return [dict(row) for row in rows]


def _call_failures(calls: list[dict[str, object]], *, run_id: str) -> dict[str, object]:
    """Separate scene actor, director-render, and diary failures in the receipt."""

    scene_calls = [call for call in calls if call.get("run_id") == run_id]
    diary_calls = [
        call for call in calls
        if str(call.get("purpose", "")).startswith(f"diary:PORCH-LIVE-R1:")
    ]
    fidelity_calls = [
        call for call in calls
        if str(call.get("purpose", "")).startswith("diary-review:PORCH-LIVE-R1:")
    ]

    def rejected(call: dict[str, object]) -> bool:
        return (
            str(call.get("status", "")) != "COMPLETED"
            or str(call.get("acceptance_status", "")) != "ACCEPTED"
        )

    actor_failures = [
        call for call in scene_calls
        if str(call.get("purpose", "")).startswith(("actor_turn:", "actor_correction:"))
        and rejected(call)
    ]
    render_failures = [
        call for call in scene_calls
        if str(call.get("purpose", "")).startswith("orchestrator_round:")
        and rejected(call)
    ]
    director_plan_failures = [
        call for call in scene_calls
        if str(call.get("purpose", "")).startswith("director_plan_round:") and rejected(call)
    ]
    diary_failures = [call for call in diary_calls if rejected(call)]
    fidelity_failures = [call for call in fidelity_calls if rejected(call)]

    def compact(call: dict[str, object]) -> dict[str, object]:
        return {
            "call_id": call.get("call_id"),
            "purpose": call.get("purpose"),
            "attempt": call.get("attempt"),
            "status": call.get("status"),
            "acceptance_status": call.get("acceptance_status"),
            "validator_code": call.get("validator_code"),
            "validator_detail": call.get("validator_detail"),
        }

    return {
        "actor_output_failures": [compact(call) for call in actor_failures],
        "director_plan_failures": [compact(call) for call in director_plan_failures],
        "director_render_failures": [compact(call) for call in render_failures],
        "diary_failures": [compact(call) for call in diary_failures],
        "diary_fidelity_failures": [compact(call) for call in fidelity_failures],
    }


def _diary_records(database: SQLiteDatabase, *, season_id: str) -> list[dict[str, object]]:
    rows = database.connection.execute(
        "SELECT diary_id, character_id, day_number, chosen_slot_number, status, word_count, "
        "late, content_path FROM diaries WHERE season_id = ? ORDER BY character_id",
        (season_id,),
    ).fetchall()
    return [
        {
            "diary_id": str(row["diary_id"]),
            "character_id": str(row["character_id"]),
            "day_number": int(row["day_number"]),
            "chosen_slot_number": (
                int(row["chosen_slot_number"])
                if row["chosen_slot_number"] is not None
                else None
            ),
            "status": str(row["status"]),
            "word_count": int(row["word_count"]) if row["word_count"] is not None else None,
            "late": bool(row["late"]),
            "content_path": str(row["content_path"]) if row["content_path"] else None,
        }
        for row in rows
    ]


def _diary_fidelity_records(
    database: SQLiteDatabase, *, season_id: str
) -> list[dict[str, object]]:
    diary_rows = database.connection.execute(
        "SELECT diary_id, character_id FROM diaries WHERE season_id = ? ORDER BY character_id",
        (season_id,),
    ).fetchall()
    records: list[dict[str, object]] = []
    for diary_row in diary_rows:
        events = database.connection.execute(
            "SELECT event_type, payload_json FROM domain_events WHERE aggregate_id = ? "
            "AND event_type IN ('DiaryFidelityReviewed', 'DiaryFidelityReviewUnavailable') "
            "ORDER BY created_at, event_id",
            (str(diary_row["diary_id"]),),
        ).fetchall()
        if not events:
            continue
        try:
            payload = json.loads(str(events[-1]["payload_json"]))
        except (TypeError, ValueError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        records.append(
            {
                "diary_id": str(diary_row["diary_id"]),
                "character_id": str(diary_row["character_id"]),
                "decision": str(payload.get("review_status", "UNAVAILABLE")),
                "summary": (str(payload["summary"]) if payload.get("summary") else None),
                "findings": payload.get("findings", {}),
                "review_path": (
                    str(payload["review_path"]) if payload.get("review_path") else None
                ),
                "call_id": str(payload["call_id"]) if payload.get("call_id") else None,
            }
        )
    return records


def _magic_summary(
    database: SQLiteDatabase,
    *,
    run_id: str,
    target_outcome: str,
    forced_roll: dict[str, object] | None,
) -> dict[str, object]:
    rolls = _event_payloads(database, run_id=run_id, event_type="MagicRollResolved")
    plan_events = _event_payloads(database, run_id=run_id, event_type="DirectorPlanAccepted")
    plans = [event.get("plan", {}) for event in plan_events]
    adjudications = [event.get("magic_adjudication") for event in plan_events]
    first_plan = plans[0] if plans and isinstance(plans[0], dict) else {}
    second_plan = plans[1] if len(plans) > 1 and isinstance(plans[1], dict) else {}
    success_criteria = str(first_plan.get("magic_success_criteria", "")).strip()
    expected_outcome = rolls[0].get("outcome") if len(rolls) == 1 else None
    persisted_adjudication = adjudications[1] if len(adjudications) > 1 else None
    runtime_adjudication = persisted_adjudication or _derive_runtime_adjudication(
        rolls, success_criteria
    )
    round_two_turn = database.connection.execute(
        "SELECT content_path FROM turns WHERE run_id = ? AND round_number = 2 "
        "AND character_id = '__orchestrator__'",
        (run_id,),
    ).fetchone()
    round_two_path = (
        Path(str(round_two_turn["content_path"]))
        if round_two_turn and round_two_turn["content_path"]
        else None
    )
    round_two_narration = (
        round_two_path.read_text(encoding="utf-8")
        if round_two_path is not None and round_two_path.is_file()
        else None
    )
    effect_detail = str(second_plan.get("magic_effect_detail", "")).strip()
    goal_answer = (
        str(runtime_adjudication.get("goal_answer", "")).strip()
        if isinstance(runtime_adjudication, dict)
        else ""
    )
    unsupported_text = " ".join(
        str(value)
        for value in (
            second_plan.get("scene_objective", ""),
            second_plan.get("adjudication", ""),
            second_plan.get("state_change", ""),
            second_plan.get("pressure", ""),
            second_plan.get("choice_a", ""),
            second_plan.get("choice_b", ""),
            *second_plan.get("canon_updates", []),
            effect_detail,
        )
    ).casefold()
    unsupported_terms_absent = not any(
        _contains_forbidden_result_term(unsupported_text, term)
        for term in MAGIC_FORBIDDEN_RESULT_TERMS
    )
    runtime_adjudication_valid = _runtime_adjudication_matches(
        runtime_adjudication,
        outcome=str(expected_outcome) if expected_outcome is not None else None,
        success_criteria=success_criteria,
    )
    consequence_detail_compiled = bool(
        effect_detail and round_two_narration and effect_detail in round_two_narration
    )
    consequence_visible = bool(
        goal_answer
        and round_two_narration
        and goal_answer in round_two_narration
        and (not effect_detail or effect_detail in round_two_narration)
    )
    acknowledged = (
        isinstance(persisted_adjudication, dict)
        and persisted_adjudication.get("outcome") == expected_outcome
    )
    if len(rolls) == 1:
        forced_roll = dict(forced_roll or {})
        forced_roll.setdefault("attribute", rolls[0].get("attribute"))
        forced_roll.setdefault("attribute_score", rolls[0].get("attribute_score"))
        forced_roll.setdefault("situational_modifier", rolls[0].get("situational_modifier"))
        forced_roll.setdefault("die_faces", rolls[0].get("die_faces"))
        forced_roll.setdefault("expected_total", TARGET_TOTALS[target_outcome])
    forced_roll_matches = bool(
        len(rolls) == 1
        and forced_roll is not None
        and rolls[0].get("outcome") == target_outcome
        and rolls[0].get("total") == forced_roll.get("expected_total")
        and rolls[0].get("die_faces") == forced_roll.get("die_faces")
    )
    return {
        "rolls": rolls,
        "forced_roll": forced_roll,
        "expected_outcome": expected_outcome,
        "magic_success_criteria": success_criteria,
        "runtime_magic_adjudication": runtime_adjudication,
        "runtime_adjudication_persisted_for_next_plan": acknowledged,
        "runtime_adjudication_matches_roll": runtime_adjudication_valid,
        "outcome_contract_valid": _outcome_contract_matches(
            second_plan, runtime_adjudication, expected_outcome, success_criteria
        ),
        "unsupported_result_terms_absent_from_plan": unsupported_terms_absent,
        "consequence_detail_compiled_in_next_beat": consequence_detail_compiled,
        "outcome_detail_visible_in_next_beat": consequence_visible,
        "whole_plan_coherent": (
            _outcome_contract_matches(
                second_plan, runtime_adjudication, expected_outcome, success_criteria
            )
            and runtime_adjudication_valid
            and unsupported_terms_absent
            and consequence_detail_compiled
            and consequence_visible
        ),
        "round_two_plan": second_plan,
        "round_two_narration": round_two_narration,
        "forced_roll_matches_target": forced_roll_matches,
        "opening_plan_locked": first_plan == LOCKED_OPENING_PLAN.model_dump(mode="json"),
    }


def _diary_text_leaked_into_scene_prompts(
    calls: list[dict[str, object]], diary_rows: list[dict[str, object]], *, run_id: str
) -> bool:
    """Verify that accepted private diary bodies never entered scene prompts."""

    scene_prompts: list[str] = []
    for call in calls:
        if call.get("run_id") != run_id or not call.get("prompt_path"):
            continue
        path = Path(str(call["prompt_path"]))
        if path.is_file():
            scene_prompts.append(path.read_text(encoding="utf-8"))
    for row in diary_rows:
        path_value = row.get("content_path")
        if not path_value:
            continue
        path = Path(str(path_value))
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").strip()
        if text and any(text in prompt for prompt in scene_prompts):
            return True
    return False


async def _run(args: argparse.Namespace) -> dict[str, object]:
    root = _validate_root(args.data_root, allow_existing=args.resume)
    config = AppConfig.load(args.config)
    manifest = _manifest(args.manifest)
    validate_model_manifest(manifest, actor_ids=list(ACTOR_IDS), config=config)
    roots = DataRoots.from_root(root)
    roots.prepare()
    database = SQLiteDatabase(roots.state / "improv.sqlite3")
    database.migrate()
    clock = VirtualClock(datetime(2026, 9, 16, 13, tzinfo=timezone.utc))
    factory = LiveSceneFactory(
        database=database,
        roots=roots,
        config=config,
        clock=clock,
        strict_rehearsal_acceptance=True,
        sessions_per_day=1,
    )
    season_id = "PORCH-LIVE-R1"
    run_id = f"{season_id}-run-01"
    existing = database.connection.execute(
        "SELECT status FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if existing is None:
        _seed_variant(
            database,
            manifest=manifest,
            variant_id="R1",
            strategy="magic_dice_diary_smoke",
            strategy_description=(
                "A matched follow-up: run the accepted safe-distance MAGIC check, then give "
                "each actor one private diary opportunity."
            ),
            clock=clock,
            dice_trial=True,
            diary_trial=True,
            scheduled_local=datetime(2026, 9, 16, 6, tzinfo=PACIFIC),
        )
    elif not args.resume:
        raise ValueError("existing rehearsal data requires --resume")
    factory.validate_season(season_id)

    scene = factory({"season_id": season_id, "run_id": run_id})
    _configure_scene(scene)
    forced_roll: dict[str, object] | None = None
    scene_result: dict[str, object] | None = None
    scene_error: dict[str, str] | None = None
    result = None
    existing_status = str(existing["status"]) if existing is not None else ""
    if existing_status == "COMPLETED":
        try:
            result = await scene.execute()
            scene_result = {"reason": result.reason, "turns": result.turns}
        except Exception as exc:
            scene_error = {"type": type(exc).__name__, "message": str(exc)}
    else:
        forced_roll = _force_outcome_tier(scene, args.target_outcome)
        try:
            result = await scene.execute()
            scene_result = {"reason": result.reason, "turns": result.turns}
        except Exception as exc:
            scene_error = {"type": type(exc).__name__, "message": str(exc)}

    diary_error: dict[str, str] | None = None
    run_row = database.connection.execute(
        "SELECT status FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if scene_result is not None and run_row is not None and str(run_row["status"]) == "COMPLETED":
        try:
            coordinator = SeasonDayCoordinator(
                database=database,
                clock=clock,
                scene_factory=factory,
                strict_rehearsal_acceptance=True,
                strict_diary_word_count=True,
                review_diary_fidelity=True,
                validate_diary_claims=True,
                sessions_per_day=1,
                final_day_number=1,
            )
            await coordinator.after_scene(
                {
                    "season_id": season_id,
                    "run_id": run_id,
                    "day_number": 1,
                    "slot_number": 1,
                },
                scene,
                result,
            )
        except Exception as exc:
            diary_error = {"type": type(exc).__name__, "message": str(exc)}

    rolls = _event_payloads(database, run_id=run_id, event_type="MagicRollResolved")
    if len(rolls) == 1:
        forced_roll = dict(forced_roll or {})
        forced_roll.setdefault("attribute", rolls[0].get("attribute"))
        forced_roll.setdefault("attribute_score", rolls[0].get("attribute_score"))
        forced_roll.setdefault("situational_modifier", rolls[0].get("situational_modifier"))
        forced_roll.setdefault("die_faces", rolls[0].get("die_faces"))
        forced_roll.setdefault("expected_total", TARGET_TOTALS[args.target_outcome])
    diary_rows = _diary_records(database, season_id=season_id)
    fidelity_reviews = _diary_fidelity_records(database, season_id=season_id)
    calls = _model_calls(database)
    magic = _magic_summary(
        database,
        run_id=run_id,
        target_outcome=args.target_outcome,
        forced_roll=forced_roll,
    )
    day_row = database.connection.execute(
        "SELECT closed FROM days WHERE season_id = ? AND day_number = 1", (season_id,)
    ).fetchone()
    cheetah_turn_count = int(
        database.connection.execute(
            "SELECT COUNT(*) FROM turns WHERE run_id = ? AND lower(character_id) LIKE '%cheetah%'",
            (run_id,),
        ).fetchone()[0]
    )
    private_paths_are_private = all(
        not row["content_path"]
        or roots.private in Path(str(row["content_path"])).resolve().parents
        for row in diary_rows
    )
    diary_statuses = [str(row["status"]) for row in diary_rows]
    diaries_accepted = len(diary_rows) == len(ACTOR_IDS) and all(
        status in {"WRITTEN", "LATE"} for status in diary_statuses
    )
    content_diary_ids = {
        str(row["diary_id"]) for row in diary_rows if row.get("content_path")
    }
    fidelity_by_diary = {
        str(row["diary_id"]): str(row["decision"]) for row in fidelity_reviews
    }
    diary_fidelity_coverage = content_diary_ids.issubset(fidelity_by_diary) and bool(
        content_diary_ids
    )
    diary_fidelity_safe_for_direction = diary_fidelity_coverage and all(
        fidelity_by_diary[diary_id] == "ACCEPTED" for diary_id in content_diary_ids
    )
    diary_quality_status = (
        "PASS"
        if diary_fidelity_safe_for_direction
        else "HUMAN_REVIEW_REQUIRED"
        if diary_fidelity_coverage
        else "FAIL"
    )
    scene_ok = (
        scene_error is None
        and scene_result == {"reason": "turn_limit", "turns": 8}
        and magic["forced_roll_matches_target"]
        and magic["opening_plan_locked"]
        and magic["runtime_adjudication_persisted_for_next_plan"]
        and magic["whole_plan_coherent"]
        and cheetah_turn_count == 0
    )
    passed = bool(
        scene_ok
        and diary_error is None
        and diaries_accepted
        and diary_fidelity_coverage
        and day_row is not None
        and bool(day_row["closed"])
        and private_paths_are_private
        and not _diary_text_leaked_into_scene_prompts(calls, diary_rows, run_id=run_id)
    )
    report = {
        "rehearsal": root.name,
        "execution_type": "isolated_live_model_rehearsal_with_private_diaries",
        "status": "PASS" if passed else "FAIL",
        "quality_status": diary_quality_status,
        "quality_review": {
            "automated_scope": [
                "word count and diary envelope acceptance",
                "private artifact placement",
                "diary-body absence from scene prompts",
                "scene and MAGIC contract checks",
                "structured diary-fidelity review and context withholding",
            ],
            "not_automated": [
                "human confirmation that the fidelity review caught every unsupported claim",
                "voice quality and continuity suitability for future direction",
            ],
            "reason": (
                "A structured model review is a fail-closed filter, not proof that the entry "
                "preserves the accepted event order or first-person limited knowledge."
            ),
        },
        "model_manifest": manifest.model_dump(mode="json"),
        "baseline_comparison": {
            "scene_constraints": "same as accepted two-round no-diary MAGIC rehearsal",
            "new_variable": (
                "one-session private diary workflow after the scene, with deterministic "
                "sentence-level claim audits"
            ),
            "target_outcome": args.target_outcome,
        },
        "scene_result": scene_result,
        "scene_error": scene_error,
        "magic": magic,
        "diary_count": len(diary_rows),
        "diaries": diary_rows,
        "diaries_accepted": diaries_accepted,
        "diary_fidelity": fidelity_reviews,
        "diary_fidelity_coverage": diary_fidelity_coverage,
        "diary_fidelity_safe_for_direction": diary_fidelity_safe_for_direction,
        "day_closed": bool(day_row and day_row["closed"]),
        "cheetah_turn_count": cheetah_turn_count,
        "private_diary_paths_are_private": private_paths_are_private,
        "diary_text_leaked_into_scene_prompts": _diary_text_leaked_into_scene_prompts(
            calls, diary_rows, run_id=run_id
        ),
        "failure_classes": _call_failures(calls, run_id=run_id),
        "diary_error": diary_error,
        "durable_run": _run_row(database, run_id),
        "diary_text_policy": "content omitted from receipt; inspect only in private audit files",
    }
    if passed and _current_season_status(database, season_id) is not SeasonStatus.PRIVATE_COMPLETE:
        _terminalize_rehearsal_season(database, season_id=season_id, clock=clock)
    (roots.state / "magic-diary-rehearsal-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


def _current_season_status(database: SQLiteDatabase, season_id: str) -> SeasonStatus:
    row = database.connection.execute(
        "SELECT status FROM seasons WHERE season_id = ?", (season_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown rehearsal season: {season_id}")
    return SeasonStatus(str(row["status"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--target-outcome",
        choices=tuple(TARGET_TOTALS),
        default="costly_success",
        help="force one outcome tier for the matched MAGIC scene",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse the same isolated root and complete unresolved diary work",
    )
    report = asyncio.run(_run(parser.parse_args()))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
