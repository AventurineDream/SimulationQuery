#!/usr/bin/env python3
"""Run one isolated, two-round MAGIC dice rehearsal against the selected models."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from improv_troupe.application.live_runtime import LiveSceneFactory, validate_model_manifest
from improv_troupe.clock import VirtualClock
from improv_troupe.config import AppConfig
from improv_troupe.domain.magic import MagicAdjudication, MagicOutcome
from improv_troupe.infrastructure import DataRoots, SQLiteDatabase
from improv_troupe.llm.structured import DirectorPlanEnvelope

from run_live_porch_rehearsal import (
    MAGIC_DICE_SCORE_PROFILES,
    MAGIC_TRIAL_CHALLENGE,
    _manifest,
    _run_row,
    _seed_variant,
    _terminalize_rehearsal_season,
    _validate_root,
)


PACIFIC = ZoneInfo("America/Los_Angeles")
ACTOR_IDS = ("mara-bell", "eli-bell", "sage-bell", "rory-bell")
TARGET_TOTALS = {"clean_success": 10, "costly_success": 8, "setback": 6}
MAGIC_FORBIDDEN_ATTEMPT_TERMS = (
    "sprain",
    "fracture",
    "strain",
    "tear",
    "dislocation",
    "acute",
    "nerve involvement",
)
MAGIC_FORBIDDEN_RESULT_TERMS = (
    *MAGIC_FORBIDDEN_ATTEMPT_TERMS,
    "sprained",
    "fractured",
    "strained",
    "torn",
    "dislocated",
    "tendon",
    "ligament",
    "trauma",
    "broken",
    "rupture",
    "ruptured",
)


def _contains_forbidden_result_term(text: str, term: str) -> bool:
    pattern = rf"\b{re.escape(term.casefold())}(?:s|ed|ing)?\b"
    return re.search(pattern, text.casefold()) is not None
LOCKED_OPENING_PLAN = DirectorPlanEnvelope(
    scene_objective="What does the cheetah's posture reveal about its raised right hind leg?",
    adjudication="Its right hind paw stays raised; cause and severity remain unknown.",
    state_change="The docile cheetah rests in porch shade, favoring its raised right hind paw.",
    pressure="The family must keep the porch quiet until wildlife support can assess it.",
    choice_a="Study its weight shifts from the kitchen doorway.",
    choice_b="Review the porch camera's arrival clip for its first steps.",
    next_actor="Mara Bell",
    complete=False,
    clock_changes=[{"clock": "mystery", "change": 1}],
    canon_updates=[
        "The cheetah remains docile; no one has approached or touched it.",
        "A porch camera captured its arrival and first steps.",
    ],
    magic_challenge=MAGIC_TRIAL_CHALLENGE,
    magic_success_criteria=(
        "Mara confirms the cheetah keeps weight off its raised right hind paw while stepping."
    ),
    magic_modifier=0,
)


def _dice_for_sum(total: int) -> tuple[int, int]:
    candidates = [
        (first, second)
        for first in range(1, 7)
        for second in range(first, 7)
        if first + second == total
    ]
    if not candidates:
        raise ValueError(f"target total requires an impossible 2d6 sum: {total}")
    return min(candidates, key=lambda pair: (abs(pair[0] - pair[1]), pair))


def _runtime_adjudication_matches(
    adjudication: dict[str, object] | None,
    *,
    outcome: str | None,
    success_criteria: str | None,
) -> bool:
    if adjudication is None or outcome is None or not success_criteria:
        return False
    try:
        expected = MagicAdjudication.from_outcome(
            outcome=MagicOutcome(outcome),
            success_criteria=success_criteria,
        ).model_dump(mode="json")
        actual = MagicAdjudication.model_validate(adjudication).model_dump(mode="json")
    except (TypeError, ValueError):
        return False
    return actual == expected


def _derive_runtime_adjudication(
    rolls: list[dict[str, object]], success_criteria: str
) -> dict[str, object] | None:
    if len(rolls) != 1 or not success_criteria:
        return None
    try:
        return MagicAdjudication.from_outcome(
            outcome=MagicOutcome(str(rolls[0]["outcome"])),
            success_criteria=success_criteria,
        ).model_dump(mode="json")
    except (KeyError, TypeError, ValueError):
        return None


def _outcome_contract_matches(
    plan: dict[str, object],
    adjudication: dict[str, object] | None,
    outcome: str | None,
    success_criteria: str | None,
) -> bool:
    if not _runtime_adjudication_matches(
        adjudication,
        outcome=outcome,
        success_criteria=success_criteria,
    ):
        return False
    detail = str(plan.get("magic_effect_detail", "")).strip()
    cost_type = plan.get("magic_cost_type")
    legacy_fields = {
        "magic_result_ack",
        "magic_goal_status",
        "magic_goal_answer",
    }
    if legacy_fields.intersection(plan):
        return False
    if outcome == "clean_success":
        return cost_type is None and bool(detail)
    if outcome == "costly_success":
        return bool(detail) and cost_type in {
            "time",
            "position",
            "trust",
            "access",
            "resources",
        }
    if outcome == "setback":
        return bool(detail) and cost_type is None
    return False


def _force_outcome_tier(scene, outcome: str) -> dict[str, object]:
    """Inject one deterministic die pair after the live actor chooses a stat."""

    if outcome not in TARGET_TOTALS:
        raise ValueError(f"unknown MAGIC outcome tier: {outcome}")
    control: dict[str, object] = {
        "target_outcome": outcome,
        "target_total": TARGET_TOTALS[outcome],
    }
    original_persist = scene._persist_actor_turn

    def persist_actor_turn(
        actor,
        round_number,
        text,
        envelope,
        attempt,
        call_id,
        *,
        disposition="ACCEPT",
    ):
        challenge = scene._game_state.challenge_for(
            character_id=actor.character_id,
            name=actor.name,
        )
        if round_number == 1 and challenge is not None and envelope.magic_stat is not None:
            score = actor.role_sheet.magic.score_for(envelope.magic_stat)
            modifier = scene._game_state.pending_magic_modifier
            dice_sum = TARGET_TOTALS[outcome] - (score - 3) - modifier
            faces = _dice_for_sum(dice_sum)
            control.update(
                {
                    "attribute": envelope.magic_stat.value,
                    "attribute_score": score,
                    "situational_modifier": modifier,
                    "die_faces": list(faces),
                    "expected_total": TARGET_TOTALS[outcome],
                }
            )

            def roll_once() -> tuple[int, int]:
                scene.die_roller = None
                return faces

            scene.die_roller = roll_once
        return original_persist(
            actor,
            round_number,
            text,
            envelope,
            attempt,
            call_id,
            disposition=disposition,
        )

    scene._persist_actor_turn = persist_actor_turn
    return control


async def _run(args: argparse.Namespace) -> dict[str, object]:
    root = _validate_root(args.data_root, allow_existing=args.resume)
    config = AppConfig.load(args.config)
    manifest = _manifest(args.manifest)
    validate_model_manifest(manifest, actor_ids=list(ACTOR_IDS), config=config)
    roots = DataRoots.from_root(root)
    roots.prepare()
    database = SQLiteDatabase(roots.state / "improv.sqlite3")
    database.migrate()
    clock = VirtualClock(datetime(2026, 9, 15, 13, tzinfo=timezone.utc))
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
        season_id, run_id = _seed_variant(
            database,
            manifest=manifest,
            variant_id="R1",
            strategy="magic_dice_smoke",
            strategy_description=(
                "A bounded live check: exercise one safe-distance MAGIC roll and require the "
                "following director beat to honor its recorded tier."
            ),
            clock=clock,
            dice_trial=True,
            scheduled_local=datetime(2026, 9, 15, 6, tzinfo=PACIFIC),
        )
    elif not args.resume:
        raise ValueError("existing rehearsal data requires --resume")
    factory.validate_season(season_id)

    result_payload: dict[str, object] | None = None
    forced_roll: dict[str, object] | None = None
    error: dict[str, str] | None = None
    existing_status = str(existing["status"]) if existing is not None else ""
    if existing_status == "COMPLETED":
        durable = _run_row(database, run_id)
        result_payload = {
            "reason": durable["completion_reason"],
            "turns": durable["turn_count"],
        }
    else:
        scene = factory({"season_id": season_id, "run_id": run_id})
        scene.max_rounds = 2
        scene.max_actor_turns = 8
        scene.require_magic_challenge = True
        scene.required_magic_next_actor = "Mara Bell"
        scene.required_magic_challenge_text = MAGIC_TRIAL_CHALLENGE
        scene.required_magic_modifier = 0
        scene.required_magic_opening_plan = LOCKED_OPENING_PLAN
        scene.forbidden_magic_attempt_terms = MAGIC_FORBIDDEN_ATTEMPT_TERMS
        scene.forbidden_magic_result_terms = MAGIC_FORBIDDEN_RESULT_TERMS
        if args.target_outcome is not None:
            forced_roll = _force_outcome_tier(scene, args.target_outcome)
        try:
            scene_result = await scene.execute()
            result_payload = {"reason": scene_result.reason, "turns": scene_result.turns}
            _terminalize_rehearsal_season(database, season_id=season_id, clock=clock)
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}

    rolls = [
        json.loads(row["payload_json"])
        for row in database.connection.execute(
            "SELECT payload_json FROM domain_events WHERE aggregate_id = ? "
            "AND event_type = 'MagicRollResolved' ORDER BY created_at, event_id",
            (run_id,),
        ).fetchall()
    ]
    plan_events = [
        json.loads(row["payload_json"])
        for row in database.connection.execute(
            "SELECT payload_json FROM domain_events WHERE aggregate_id = ? "
            "AND event_type = 'DirectorPlanAccepted' ORDER BY created_at, event_id",
            (run_id,),
        ).fetchall()
    ]
    plans = [event.get("plan", {}) for event in plan_events]
    adjudications = [event.get("magic_adjudication") for event in plan_events]
    diary_count = int(
        database.connection.execute(
            "SELECT COUNT(*) FROM diaries WHERE season_id = ?", (season_id,)
        ).fetchone()[0]
    )
    cheetah_turn_count = int(
        database.connection.execute(
            "SELECT COUNT(*) FROM turns WHERE run_id = ? AND lower(character_id) LIKE '%cheetah%'",
            (run_id,),
        ).fetchone()[0]
    )
    first_plan = plans[0] if plans else {}
    second_plan = plans[1] if len(plans) > 1 else {}
    success_criteria = str(first_plan.get("magic_success_criteria", "")).strip()
    expected_outcome = rolls[0]["outcome"] if len(rolls) == 1 else None
    persisted_adjudication = adjudications[1] if len(adjudications) > 1 else None
    runtime_adjudication = persisted_adjudication or _derive_runtime_adjudication(
        rolls, success_criteria
    )
    runtime_adjudication_source = (
        "accepted_plan_event"
        if persisted_adjudication is not None
        else "pending_roll"
        if runtime_adjudication is not None
        else None
    )
    acknowledged = (
        persisted_adjudication is not None
        and persisted_adjudication.get("outcome") == expected_outcome
    )
    exact_challenge = first_plan.get("magic_challenge") == MAGIC_TRIAL_CHALLENGE
    locked_opening_plan = first_plan == LOCKED_OPENING_PLAN.model_dump(mode="json")
    zero_modifier = first_plan.get("magic_modifier") == 0
    mara_is_next_actor = str(first_plan.get("next_actor", "")).casefold() in {
        "mara bell",
        "mara-bell",
    }
    forced_roll_matches = (
        args.target_outcome is None
        or (
            len(rolls) == 1
            and forced_roll is not None
            and rolls[0].get("outcome") == args.target_outcome
            and rolls[0].get("total") == forced_roll.get("expected_total")
            and rolls[0].get("die_faces") == forced_roll.get("die_faces")
        )
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
    outcome_contract_valid = _outcome_contract_matches(
        second_plan, runtime_adjudication, expected_outcome, success_criteria
    )
    goal_answer = (
        str(runtime_adjudication.get("goal_answer", "")).strip()
        if runtime_adjudication
        else ""
    )
    effect_detail = str(second_plan.get("magic_effect_detail", "")).strip()
    accepted_magic_action = str(rolls[0].get("action", "")) if len(rolls) == 1 else ""
    pre_roll_diagnostic_terms_absent = bool(accepted_magic_action) and not any(
        _contains_forbidden_result_term(accepted_magic_action, term)
        for term in MAGIC_FORBIDDEN_ATTEMPT_TERMS
    )
    consequence_visible = bool(
        goal_answer
        and round_two_narration
        and goal_answer in round_two_narration
        and (not effect_detail or effect_detail in round_two_narration)
    )
    runtime_adjudication_valid = _runtime_adjudication_matches(
        runtime_adjudication,
        outcome=expected_outcome,
        success_criteria=success_criteria,
    )
    accepted_magic_actor_text = str(rolls[0].get("actor_text", "")) if len(rolls) == 1 else ""
    action_recorded_separately = bool(
        len(rolls) == 1
        and accepted_magic_action
        and accepted_magic_actor_text
        and rolls[0].get("attempt_contract") == "attempted_method_only"
    )
    second_plan_text = " ".join(
        str(value)
        for value in (
            second_plan.get("scene_objective", ""),
            second_plan.get("adjudication", ""),
            second_plan.get("state_change", ""),
            second_plan.get("pressure", ""),
            second_plan.get("choice_a", ""),
            second_plan.get("choice_b", ""),
            *second_plan.get("canon_updates", []),
            second_plan.get("magic_effect_detail", ""),
        )
    ).casefold()
    unsupported_terms_absent = not any(
        _contains_forbidden_result_term(second_plan_text, term)
        for term in MAGIC_FORBIDDEN_RESULT_TERMS
    )
    consequence_detail_compiled = bool(
        effect_detail
        and round_two_narration
        and effect_detail in round_two_narration
    )
    whole_plan_coherent = (
        outcome_contract_valid
        and runtime_adjudication_valid
        and unsupported_terms_absent
        and consequence_detail_compiled
        and consequence_visible
    )
    passed = (
        error is None
        and result_payload == {"reason": "turn_limit", "turns": 8}
        and len(rolls) == 1
        and rolls[0].get("round_number") == 1
        and acknowledged
        and diary_count == 0
        and cheetah_turn_count == 0
        and (
            args.target_outcome is None
            or (
                exact_challenge
                and locked_opening_plan
                and zero_modifier
                and mara_is_next_actor
                and forced_roll_matches
                and pre_roll_diagnostic_terms_absent
                and action_recorded_separately
                and whole_plan_coherent
            )
        )
    )
    report = {
        "rehearsal": root.name,
        "execution_type": "isolated_live_model_rehearsal",
        "status": "PASS" if passed else "FAIL",
        "model_manifest": manifest.model_dump(mode="json"),
        "accepted_design_draft": {
            "approval_status": "user_accepted_for_rehearsal",
            "magic_score_scale": "1-5, centered at 3",
            "character_scores": {
                character_id: scores.model_dump(mode="json")
                for character_id, scores in MAGIC_DICE_SCORE_PROFILES.items()
            },
            "situational_modifier_bounds": [-2, 2],
            "run_shape": "2 rounds, 8 family turns; no diaries; cheetah has no turn",
        },
        "target_outcome": args.target_outcome,
        "forced_roll": forced_roll,
        "challenge_exact": exact_challenge,
        "opening_plan_locked_and_unresolved": locked_opening_plan,
        "locked_opening_plan": LOCKED_OPENING_PLAN.model_dump(mode="json"),
        "declared_situational_modifier": first_plan.get("magic_modifier"),
        "mara_was_next_actor": mara_is_next_actor,
        "magic_success_criteria": success_criteria,
        "scene_result": result_payload,
        "rolls": rolls,
        "runtime_adjudication_persisted_for_next_plan": acknowledged,
        "runtime_magic_adjudication": runtime_adjudication,
        "runtime_adjudication_source": runtime_adjudication_source,
        "pre_roll_diagnostic_terms_absent": pre_roll_diagnostic_terms_absent,
        "accepted_magic_action": accepted_magic_action,
        "accepted_magic_actor_text": accepted_magic_actor_text,
        "action_recorded_separately": action_recorded_separately,
        "outcome_contract_valid": outcome_contract_valid,
        "runtime_adjudication_matches_roll": runtime_adjudication_valid,
        "runtime_goal_answer_matches_criteria": (
            bool(runtime_adjudication_valid)
            and bool(goal_answer)
            and (
                goal_answer == success_criteria
                if expected_outcome in {"clean_success", "costly_success"}
                else goal_answer != success_criteria
            )
        ),
        "unsupported_result_terms_absent_from_plan": unsupported_terms_absent,
        "consequence_detail_compiled_in_next_beat": consequence_detail_compiled,
        "outcome_detail_visible_in_next_beat": consequence_visible,
        "whole_plan_coherent": whole_plan_coherent,
        "round_two_plan": second_plan,
        "round_two_narration": round_two_narration,
        "narrative_consequence_review": (
            "runtime adjudication, whole-plan consistency, unsupported-claim scan, and compiled "
            "result line checked; broader prose coherence still merits human review"
        ),
        "diary_count": diary_count,
        "cheetah_turn_count": cheetah_turn_count,
        "durable_run": _run_row(database, run_id),
        "error": error,
    }
    (roots.state / "magic-dice-rehearsal-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--target-outcome",
        choices=tuple(TARGET_TOTALS),
        help="force one outcome tier for the first MAGIC check; intended for isolated rehearsal only",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse or resume the run stored at --data-root without replacing its durable events",
    )
    report = asyncio.run(_run(parser.parse_args()))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
