#!/usr/bin/env python3
"""Run five isolated 16-turn Porch rehearsals against the selected live models.

This is a private model-quality rehearsal. It creates no production season,
diaries, or public projection. Each strategy is seeded as an independent
one-run season so canon and actor memories cannot leak between variants.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from improv_troupe.application.live_runtime import LiveSceneFactory, SceneModelManifest, validate_model_manifest
from improv_troupe.clock import VirtualClock
from improv_troupe.config import AppConfig
from improv_troupe.domain import (
    CastMember,
    HiddenSeasonPlan,
    OpeningSnapshot,
    RoleSheet,
    ScheduleSlot,
    Season,
    SeasonStatus,
    WorldBook,
    WorldBookEntry,
    transition_season,
)
from improv_troupe.domain.magic import MagicScores
from improv_troupe.infrastructure import DataRoots, RecordRepository, ScheduleRepository, SQLiteDatabase, SeasonRepository


PACIFIC = ZoneInfo("America/Los_Angeles")
ROOT_MARKER = "season-1-porch-live-"
MAGIC_TRIAL_CHALLENGE = (
    "Can Mara identify what the cheetah's posture reveals about its leg injury, "
    "without approaching or touching it?"
)
MAGIC_DICE_SCORE_PROFILES = {
    "mara-bell": MagicScores(might=3, authority=3, gusto=5, intellect=4, cool=4),
    "eli-bell": MagicScores(might=3, authority=4, gusto=3, intellect=4, cool=5),
    "sage-bell": MagicScores(might=3, authority=4, gusto=4, intellect=3, cool=5),
    "rory-bell": MagicScores(might=3, authority=4, gusto=4, intellect=5, cool=3),
}
STRATEGIES = (
    ("R1", "cautious_disclosure", "Adults prioritize safe observation and professional help early."),
    ("R2", "secretive_kids", "The family tries to conceal the animal long enough to understand and keep it."),
    ("R3", "twin_alliance", "The twins work together to investigate while adults manage safety."),
    ("R4", "mara_adventure", "Mara follows her field instincts and tests proximity before professional help arrives."),
    ("R5", "eli_care", "Eli establishes calm, distance, and care while the others investigate within boundaries."),
)


def _validate_root(root: Path, *, allow_existing: bool = False) -> Path:
    candidate = root.expanduser().resolve()
    if candidate == Path(candidate.anchor) or candidate == Path.home() or candidate == Path("/tmp"):
        raise ValueError("refusing broad rehearsal root")
    if allow_existing:
        if not candidate.is_dir():
            raise ValueError(f"resume root must be an existing directory: {candidate}")
        return candidate
    if candidate.exists() and any(candidate.iterdir()):
        raise ValueError(f"rehearsal root must be new or empty: {candidate}")
    return candidate


def _manifest(path: Path) -> SceneModelManifest:
    return SceneModelManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _role_sheets(*, dice_trial: bool = False) -> list[RoleSheet]:
    return [
        RoleSheet(
            character_id="mara-bell",
            magic=MAGIC_DICE_SCORE_PROFILES["mara-bell"] if dice_trial else MagicScores(),
            objectives=["Protect the family while treating the unknown as a field problem worth understanding."],
            boundaries=["Do not decide another family member's action or treat the cheetah as a tame pet."],
            knowledge=["Safari guiding, animal body language, route planning, and emergency camp logistics."],
            relationships=["Trust Eli's care expertise even when it slows an adventure."],
            secrets=["The off-season has left Mara missing the wild more than she admits."],
            play_style="Adventurous, capable, cheerful under pressure, occasionally reckless.",
            voice_guidance="Warm field-guide clarity with affectionate understatement.",
        ),
        RoleSheet(
            character_id="eli-bell",
            magic=MAGIC_DICE_SCORE_PROFILES["eli-bell"] if dice_trial else MagicScores(),
            objectives=["Keep frightened living things from feeling abandoned while preserving safety."],
            boundaries=["Do not approach or handle the cheetah without professional guidance."],
            knowledge=["CNA care routines, patient advocacy, steady hands, and crisis de-escalation."],
            relationships=["Respect Mara's competence while naming when an adventure is becoming unsafe."],
            secrets=["He will overcommit to one more day of care if nobody sets a boundary."],
            play_style="Tender, observant, competent, and quietly firm about care.",
            voice_guidance="Calm, ordinary language that makes emergencies feel manageable.",
        ),
        RoleSheet(
            character_id="sage-bell",
            magic=MAGIC_DICE_SCORE_PROFILES["sage-bell"] if dice_trial else MagicScores(),
            objectives=["Keep the twins together and turn the event into a shared adventure."],
            boundaries=["Do not physically approach the cheetah or override an adult safety boundary."],
            knowledge=["Animal facts, noticing distress, labels, maps, twin rules, and coordination."],
            relationships=["Invite Rory into plans, but notice when invitation becomes pressure."],
            secrets=["Rory's independence can feel like abandonment even when it is not."],
            play_style="Earnest, collaborative, imaginative, sometimes over-attached.",
            voice_guidance="Specific observations, shared language, and strong feelings stated plainly.",
        ),
        RoleSheet(
            character_id="rory-bell",
            magic=MAGIC_DICE_SCORE_PROFILES["rory-bell"] if dice_trial else MagicScores(),
            objectives=["Make one important discovery that belongs to Rory alone."],
            boundaries=["Do not narrate another character's thoughts or treat curiosity as permission to endanger anyone."],
            knowledge=["Hidden routes, junk-built inventions, overlooked spaces, and private collections."],
            relationships=["Want Sage close, but resist being absorbed into a single twin identity."],
            secrets=["She may hide a mistake if sharing it feels like losing ownership of the discovery."],
            play_style="Inventive, private, daring, and sensitive to being defined as half of a pair.",
            voice_guidance="Short concrete observations, quick ideas, and defensively specific claims.",
        ),
    ]


def _world_book(*, dice_trial: bool = False) -> list[WorldBook]:
    dice_directive = (
        " In each isolated outcome rehearsal, use this exact round-one challenge for Mara: "
        f"{MAGIC_TRIAL_CHALLENGE!r} Set Mara Bell as next_actor and set MAGIC_MODIFIER to 0. "
        "Mara chooses how to attempt it and which attribute fits her approach. Her observations "
        "are not a veterinary diagnosis and never justify approaching or touching the cheetah. "
        "After the roll, the runtime owns the outcome, goal status, and goal answer. The director "
        "supplies only a short observable consequence detail, plus one tangible cost type for a "
        "costly success, and makes the fiction meaningfully obey it. A setback must still move "
        "the situation forward."
        if dice_trial
        else ""
    )
    return [
        WorldBook(
            world_book_id="porch-shared",
            name="Porch shared facts",
            description="Research-informed shared guardrails for the rehearsal.",
            token_budget=700,
            entries=[
                WorldBookEntry(
                    entry_id="porch-cheetah-facts",
                    name="Cheetah behavior",
                    constant=True,
                    content=(
                        "The cheetah is an injured wild animal, not a pet. It is cautious, "
                        "visual, most active in cooler morning or evening hours, rests in shade, "
                        "and may chirp, growl, or withdraw. It does not roar or speak human language."
                    ),
                    visibility="SHARED",
                ),
                WorldBookEntry(
                    entry_id="porch-house",
                    name="Bell house",
                    constant=True,
                    content=(
                        "It is a modest semi-rural three-bedroom, two-bath house in sunny, "
                        "temperate Banff in 3036. The handmade treehouse overlooks the yard "
                        "and nearby wildlife corridor."
                    ),
                    visibility="SHARED",
                ),
            ],
        ),
        WorldBook(
            world_book_id="porch-director",
            name="Porch director rules",
            description="Private adjudication rules for the live director.",
            token_budget=900,
            entries=[
                WorldBookEntry(
                    entry_id="porch-rules",
                    name="MAGIC resolution",
                    constant=True,
                    content=(
                        "For meaningful uncertainty, use 2d6 + (MAGIC score - 3) + situational modifier. "
                        "Might is strength, endurance, and hands-on physical effort; Authority is "
                        "advocacy, coordination, and earning trust, never control over another "
                        "character; Gusto is initiative, daring, and enthusiasm; Intellect is "
                        "observation, knowledge, inference, and planning; Cool is composure, patience, "
                        "and timing under pressure. A clean success achieves the stated goal without "
                        "an added complication; a costly success achieves it with a meaningful cost; "
                        "a setback means the approach falls short but the situation changes through "
                        "new information, a complication, or another opening. Never make a setback a "
                        "dead end. Do not roll trivial actions. "
                        "The app rolls and records all dice; never invent, narrate, or alter die faces. "
                        "After a roll, the next director plan must acknowledge the exact tier and "
                        "honor it: clean success succeeds, costly success succeeds with cost, and a "
                        "setback's intended approach falls short while the situation advances."
                        + dice_directive
                        + " The cheetah never receives an independent turn: narrate its observable response "
                        "only after family actions or environmental changes. Never write a family member's "
                        "private thoughts, dialogue, or decision for them."
                    ),
                    visibility="DIRECTOR_ONLY",
                ),
            ],
        ),
    ]


def _seed_variant(
    database: SQLiteDatabase,
    *,
    manifest: SceneModelManifest,
    variant_id: str,
    strategy: str,
    strategy_description: str,
    clock: VirtualClock,
    dice_trial: bool = False,
    diary_trial: bool = False,
    scheduled_local: datetime | None = None,
) -> tuple[str, str]:
    season_id = f"PORCH-LIVE-{variant_id}"
    run_id = f"{season_id}-run-01"
    cast = [
        CastMember(character_id="mara-bell", name="Mara Bell", role_sheet_version=1),
        CastMember(character_id="eli-bell", name="Eli Bell", role_sheet_version=1),
        CastMember(character_id="sage-bell", name="Sage Bell", role_sheet_version=1),
        CastMember(character_id="rory-bell", name="Rory Bell", role_sheet_version=1),
    ]
    opening = OpeningSnapshot(
        set="The Bell family porch",
        setting="A sunny morning at the family's modest semi-rural home in temperate Banff, Canada, in 3036.",
        cast=["Mara Bell", "Eli Bell", "Sage Bell", "Rory Bell"],
        world_rules=[
            "AI advancements resemble magic, but daily life remains recognizably modern and materially unequal.",
            "The family finds an injured, docile cheetah on the porch and does not initially name it.",
            "The treehouse is a recurring location and a meaningful refuge for the twins.",
            "The four family members receive turns; the cheetah is always narrated by the Orchestrator and never receives a turn.",
            "Meaningful risks use the MAGIC resolution formula from the private director rules.",
            (
                "A private diary workflow follows this scene; diary text is not shared with the "
                "scene director or other actors before deliberate review."
                if diary_trial
                else "No diaries are written in this rehearsal."
            ),
        ],
    )
    plan = HiddenSeasonPlan(
        premise="A family must decide how to shelter an injured cheetah without turning care into possession.",
        planned_tensions=[
            "The cheetah's condition and trust must change in response to family choices.",
            "Safety, secrecy, professional help, and the twins' rivalry should create consequential forks.",
            f"Rehearsal variant: {strategy}. {strategy_description}",
        ],
        hidden_mysteries=[
            "The cheetah's arrival and transport history are unknown.",
            "A later clue may connect it to a managed wildlife system or an invalid registry.",
        ],
        role_sheets=_role_sheets(dice_trial=dice_trial),
    )
    slot_time = scheduled_local or datetime(2026, 9, 12, 6, tzinfo=PACIFIC)
    slot = ScheduleSlot(
        slot_id=run_id,
        season_id=season_id,
        day_number=1,
        slot_number=1,
        run_number=1,
        scheduled_local=slot_time,
        scheduled_utc=slot_time.astimezone(timezone.utc),
        utc_offset=slot_time.strftime("%z")[:3] + ":" + slot_time.strftime("%z")[3:],
    )
    season_number = int(variant_id.removeprefix("R"))
    SeasonRepository(database).create(
        Season(
            season_id=season_id,
            # The repository keeps season numbers unique even for private
            # rehearsal records sharing one audit database.
            season_number=season_number,
            title=f"Season {season_number} Porch live rehearsal — {strategy}",
            status=SeasonStatus.ARMED,
            opening=opening,
            private_plan=plan,
            model_manifest=manifest.model_dump(mode="json"),
            cast=cast,
            schedule=[slot],
            world_books=_world_book(dice_trial=dice_trial),
        )
    )
    RecordRepository(database).insert_run(run_id=run_id, season_id=season_id, slot_id=run_id, status="QUEUED")
    return season_id, run_id


def _run_row(database: SQLiteDatabase, run_id: str) -> dict[str, object]:
    row = database.connection.execute(
        "SELECT run_id,status,turn_count,completion_reason FROM runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    calls = database.connection.execute(
        "SELECT purpose,status,acceptance_status,COUNT(*) AS count FROM model_calls "
        "WHERE run_id = ? GROUP BY purpose,status,acceptance_status ORDER BY purpose,status",
        (run_id,),
    ).fetchall()
    return {
        "run_id": run_id,
        "status": str(row["status"]),
        "turn_count": int(row["turn_count"]),
        "completion_reason": str(row["completion_reason"] or ""),
        "model_calls": [dict(call) for call in calls],
    }


def _terminalize_rehearsal_season(
    database: SQLiteDatabase,
    *,
    season_id: str,
    clock: VirtualClock,
) -> None:
    """Close one isolated rehearsal so the next variant can be seeded.

    Production seasons are intentionally single-active-season. These five
    variants are independent experiments sharing one audit database, so each
    completed scene must move through the normal terminal state transition
    before the next variant is created.
    """
    seasons = SeasonRepository(database)
    current = seasons.get(season_id)
    closing = transition_season(current, SeasonStatus.CLOSING)
    seasons.update(closing, expected_version=current.version, now=clock.now())
    completed = transition_season(closing, SeasonStatus.PRIVATE_COMPLETE)
    seasons.update(completed, expected_version=closing.version, now=clock.now())


async def _run(args: argparse.Namespace) -> dict[str, object]:
    root = _validate_root(args.data_root, allow_existing=args.resume)
    config = AppConfig.load(args.config)
    manifest = _manifest(args.manifest)
    validate_model_manifest(
        manifest,
        actor_ids=["mara-bell", "eli-bell", "sage-bell", "rory-bell"],
        config=config,
    )
    roots = DataRoots.from_root(root)
    roots.prepare()
    database = SQLiteDatabase(roots.state / "improv.sqlite3")
    database.migrate()
    clock = VirtualClock(datetime(2026, 9, 12, 13, tzinfo=timezone.utc))
    factory = LiveSceneFactory(
        database=database,
        roots=roots,
        config=config,
        clock=clock,
        strict_rehearsal_acceptance=True,
        sessions_per_day=1,
    )
    results = []
    for variant_id, strategy, description in STRATEGIES:
        season_id = f"PORCH-LIVE-{variant_id}"
        run_id = f"{season_id}-run-01"
        existing_run = database.connection.execute(
            "SELECT status FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        resumed = existing_run is not None
        if existing_run is None:
            season_id, run_id = _seed_variant(
                database,
                manifest=manifest,
                variant_id=variant_id,
                strategy=strategy,
                strategy_description=description,
                clock=clock,
            )
        factory.validate_season(season_id)
        if existing_run is not None and str(existing_run["status"]) == "COMPLETED":
            durable = _run_row(database, run_id)
            scene_result = {
                "reason": durable["completion_reason"],
                "turns": durable["turn_count"],
            }
        else:
            scene = factory({"season_id": season_id, "run_id": run_id})
            try:
                result = await scene.execute()
                scene_result = {
                    "reason": result.reason,
                    "turns": result.turns,
                }
            except Exception as exc:
                # Preserve a model/runtime failure as a batch datum, then
                # close this isolated variant so later variants can run.
                _terminalize_rehearsal_season(database, season_id=season_id, clock=clock)
                results.append({
                    "variant_id": variant_id,
                    "strategy": strategy,
                    "resumed": resumed,
                    "scene_result": None,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                    "durable": _run_row(database, run_id),
                })
                continue
            _terminalize_rehearsal_season(database, season_id=season_id, clock=clock)
            durable = _run_row(database, run_id)
        results.append({
            "variant_id": variant_id,
            "strategy": strategy,
            "resumed": resumed,
            "scene_result": scene_result,
            "durable": durable,
        })
    report = {
        "batch": "season-1-porch-live-20260912",
        "execution_type": "isolated_live_model_rehearsal",
        "model_manifest": manifest.model_dump(mode="json"),
        "turns_per_run": 16,
        "diaries": "none",
        "cheetah_turns": 0,
        "results": results,
    }
    (roots.state / "porch-live-rehearsal-report.json").write_text(
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
        "--resume",
        action="store_true",
        help="resume completed or interrupted variants in an existing rehearsal root",
    )
    asyncio.run(_run(parser.parse_args()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
