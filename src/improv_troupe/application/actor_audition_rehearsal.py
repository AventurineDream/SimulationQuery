"""Two-day, four-performer live-model acting audition."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from ..clock import VirtualClock
from ..config import AppConfig
from ..domain import (
    ActorSheet, CastMember, CastingAssignment, CharacterCard, HiddenSeasonPlan,
    OpeningSnapshot, RoleSheet, ScheduleSlot, Season, SeasonStatus, WorldBook,
    WorldBookEntry,
)
from ..infrastructure import (
    DataRoots, RecordRepository, ScheduleRepository, SeasonRepository,
    SQLiteDatabase, WorkQueue,
)
from ..llm.client import ChatClient
from .episode_resolution import EpisodeResolutionService
from .live_runtime import EpisodeSpineBeat, LiveSceneFactory, SceneModelManifest, validate_model_manifest
from .one_day_rehearsal import PRODUCTION_DATA_ROOT, _tree_hash
from .season_days import SeasonDayCoordinator
from .worker import DurableWorkflowWorker


ACTOR_AUDITION_SEASON_ID = "S02-ACTOR-AUDITION"


class ActorAuditionRehearsalError(RuntimeError):
    pass


@dataclass(frozen=True)
class ActorAuditionRehearsalReport:
    season_id: str
    casting: tuple[dict[str, str], ...]
    runs: tuple[dict[str, object], ...]
    diaries: tuple[dict[str, object], ...]
    resolution: dict[str, object]
    actor_evidence: tuple[dict[str, object], ...]
    director_evidence: dict[str, object]
    audit: dict[str, int]
    unresolved: tuple[dict[str, str], ...]
    publication: str
    public_archive_sha256: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


async def run_live_actor_audition_rehearsal(
    root: str | Path,
    *,
    config: AppConfig,
    manifest: SceneModelManifest,
    client_factory: Callable[[str], ChatClient] | None = None,
) -> ActorAuditionRehearsalReport:
    audition_bindings = list(manifest.actors.values())
    if manifest.actor_default is not None:
        audition_bindings.append(manifest.actor_default)
    if any("peach" in binding.model.casefold() for binding in audition_bindings):
        raise ActorAuditionRehearsalError(
            "Peach is excluded from AI Improv Troupe rehearsal casting"
        )
    data_root = _validate_root(root)
    roots = DataRoots.from_root(data_root)
    roots.prepare()
    database = SQLiteDatabase(roots.state / "improv.sqlite3")
    database.migrate()
    clock = VirtualClock(datetime(2026, 9, 14, 13, tzinfo=timezone.utc))
    _seed(database, clock, config=config, manifest=manifest)

    factory = _audition_scene_factory(database, roots, config, clock, client_factory)
    coordinator = SeasonDayCoordinator(
        database=database, clock=clock, scene_factory=factory,
        strict_rehearsal_acceptance=True, strict_diary_word_count=True,
        sessions_per_day=2, final_day_number=2,
    )

    async def after_scene(payload, scene, scene_result) -> None:
        if int(payload["slot_number"]) != 2:
            return
        await coordinator.after_scene(payload, scene, scene_result)
        if int(payload["day_number"]) == 2:
            season = SeasonRepository(database).get(ACTOR_AUDITION_SEASON_ID)
            resolution = await EpisodeResolutionService(
                season_id=ACTOR_AUDITION_SEASON_ID,
                final_run_id=str(payload["run_id"]),
                opening=season.opening,
                private_plan=season.private_plan,
                orchestrator=scene.orchestrator,
            ).resolve(
                accepted_canon=_all_canon(database),
                final_transcript=_episode_transcript(database),
            )
            scene_result.transcript.add_direction(
                "EPISODE RESOLUTION — " + resolution.narration
            )

    worker = DurableWorkflowWorker(
        database=database, clock=clock, scene_factory=factory,
        post_scene=after_scene, close_day=coordinator.close_day,
        retry_non_transport_failures=False,
    )
    await _drain(worker, database, clock)
    report = _report(database, roots, manifest)
    _validate_complete(report)
    (roots.state / "actor-audition-rehearsal-report.json").write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report




def _audition_scene_factory(database, roots, config, clock, client_factory=None):
    return LiveSceneFactory(
        database=database, roots=roots, config=config, clock=clock,
        client_factory=client_factory, strict_rehearsal_acceptance=True,
        sessions_per_day=2,
        episode_phases=(
            "inciting_commitment", "complication_cost", "reversal_crisis", "climax_choice",
        ),
        episode_spine={
            "inciting_commitment": EpisodeSpineBeat(
                dramatic_job="Reveal the basalt archive and require a commitment to pursue, abandon, or redefine its recovery.",
                required_lore_entry_ids=("basalt-archive",),
                required_story_terms=("archive", "observatory"),
            ),
            "complication_cost": EpisodeSpineBeat(
                dramatic_job="Make the archive commitment consume or forfeit a named resource; do not replay hull-crack containment.",
                required_lore_entry_ids=("thermal-shield",),
                required_story_terms=("cooling", "propulsion", "habitat"),
                forbidden_story_terms=("blister", "junction", "crack"),
            ),
            "reversal_crisis": EpisodeSpineBeat(
                dramatic_job="Reveal that the archive is a living environmental record, changing what recovery means.",
                required_lore_entry_ids=("director-truth",),
                required_story_terms=("living record", "environmental record", "archive"),
                forbidden_story_terms=("blister", "junction", "countdown"),
            ),
            "climax_choice": EpisodeSpineBeat(
                dramatic_job="Force the final value choice about preserving, carrying, or abandoning the living archive and adjudicate its cost.",
                required_lore_entry_ids=("director-truth",),
                required_story_terms=("archive", "record"),
                forbidden_story_terms=("test", "diagnostic", "calibration", "junction", "blister"),
            ),
        },
    )

def _validate_root(root: str | Path) -> Path:
    candidate = Path(root).expanduser().resolve(strict=False)
    if candidate == Path(candidate.anchor) or candidate in {Path.home(), Path("/tmp").resolve()}:
        raise ActorAuditionRehearsalError("rehearsal root must be a dedicated child directory")
    if candidate == PRODUCTION_DATA_ROOT or PRODUCTION_DATA_ROOT in candidate.parents:
        raise ActorAuditionRehearsalError("rehearsal cannot use production data")
    if candidate.exists() and any(candidate.iterdir()):
        raise ActorAuditionRehearsalError("rehearsal root must be new or empty")
    return candidate


def _seed(database, clock, *, config: AppConfig, manifest: SceneModelManifest,
          season_id=ACTOR_AUDITION_SEASON_ID, start_date=date(2026, 9, 15),
          days=2, sessions_per_day=2) -> None:
    include_williams = manifest.actor_default is not None or "williams-lophophora-ii" in manifest.actors
    cast = [
        CastMember(character_id="luna-planck", name="Luna Planck", role_sheet_version=1),
        CastMember(character_id="mason-curie", name="Mason Curie", role_sheet_version=1),
        CastMember(character_id="higgs-sierra", name="Higgs Sierra", role_sheet_version=1),
        CastMember(character_id="ivy-fermion", name="Ivy Fermion", role_sheet_version=1),
    ]
    actors = [
        ActorSheet(actor_id="boson-reefer", name="Boson Reefer", pronouns="he/him",
                   performance_contract=["Make committed choices while preserving character agency."],
                   ensemble_approach="Build on accepted moves without flattening disagreement.",
                   diary_approach="Reflect privately through the character's limited experience."),
        ActorSheet(actor_id="chrysanthemum-ballad", name="Chrysanthemum Ballad", pronouns="she/her",
                   performance_contract=["Make committed choices while preserving character agency."],
                   ensemble_approach="Build on accepted moves without flattening disagreement.",
                   diary_approach="Reflect privately through the character's limited experience."),
        ActorSheet(actor_id="click-tourmaline", name="Click Tourmaline", pronouns="they/them",
                   performance_contract=["Make committed choices while preserving character agency."],
                   ensemble_approach="Build on accepted moves without flattening disagreement.",
                   diary_approach="Reflect privately through the character's limited experience."),
        ActorSheet(actor_id="williams-lophophora-ii", name="Williams Lophophora II", pronouns="he/they",
                   performance_contract=["Make committed choices while preserving character agency."],
                   ensemble_approach="Build on accepted moves without flattening disagreement.",
                   diary_approach="Reflect privately through the character's limited experience."),
    ]
    casting = [
        CastingAssignment(actor_id="boson-reefer", character_id="ivy-fermion"),
        CastingAssignment(actor_id="chrysanthemum-ballad", character_id="luna-planck"),
        CastingAssignment(actor_id="click-tourmaline", character_id="mason-curie"),
        CastingAssignment(actor_id="williams-lophophora-ii", character_id="higgs-sierra"),
    ]
    if not include_williams:
        cast = [member for member in cast if member.character_id != "higgs-sierra"]
        actors = [actor for actor in actors if actor.actor_id != "williams-lophophora-ii"]
        casting = [assignment for assignment in casting if assignment.actor_id != "williams-lophophora-ii"]
    validate_model_manifest(manifest, actor_ids=[a.actor_id for a in actors], config=config)
    plan = HiddenSeasonPlan(
        premise="The Aether discovers a sealed basalt archive in an unstable caldera and must decide what preserving it is worth.",
        planned_tensions=[
            "Safety, progress, and incomplete knowledge cannot all be preserved.",
            "Recovering or abandoning the archive must demand an irreversible material or relational cost.",
        ],
        hidden_mysteries=["The archive is a living environmental record rather than inert data or a rescue device."],
        role_sheets=[
            RoleSheet(character_id="luna-planck", objectives=["Read the environment without claiming certainty."], boundaries=["Do not turn hypothesis into proof."], knowledge=["Botany and patient systems observation."], relationships=["Invite tests without forcing agreement."], secrets=["A familiar growth pattern unsettles her."], play_style="Quietly observant and experimentally curious.", voice_guidance="Concrete, patient, candid about uncertainty."),
            RoleSheet(character_id="mason-curie", objectives=["Keep the vessel survivable under incomplete diagnostics."], boundaries=["Do not decide another character's actions."], knowledge=["Marine pressure and field containment."], relationships=["Disagree plainly without forcing consensus."], secrets=["He trusts physical margins over reassuring displays."], play_style="Measured, practical, slow to overpromise.", voice_guidance="Calm material comparisons, not lectures."),
            RoleSheet(character_id="ivy-fermion", objectives=["Name the human cost inside the technical choice."], boundaries=["Do not narrate another character's inner state."], knowledge=["Playwriting, herbs, and attention to rhythm."], relationships=["Press for clarity while making room for contradiction."], secrets=["Growth in a hostile place feels personally significant."], play_style="Reflective but willing to commit.", voice_guidance="Specific sensory language attentive to people."),
            RoleSheet(character_id="higgs-sierra", objectives=["Identify the immediate safety move everyone is avoiding."], boundaries=["Do not operate another character's systems or move another character."], knowledge=["Stunt safety and wildfire escape planning."], relationships=["Challenge unsafe momentum while leaving others' choices open."], secrets=["She maps exits before admitting fear."], play_style="Embodied, decisive, alert to practical exits.", voice_guidance="Concrete physical choices without bravado."),
        ],
    )
    if not include_williams:
        plan = plan.model_copy(update={
            "role_sheets": [sheet for sheet in plan.role_sheets if sheet.character_id != "higgs-sierra"]
        })
    opening = OpeningSnapshot(
        set='Submarine "Aether"',
        setting="Inside Yellowstone's molten caldera, under advanced but fallible thermal shielding.",
        cast=[member.name for member in cast],
        world_rules=[
            "Fusion output can be modulated but is not guaranteed to survive extreme heat.",
            "Crew choices influence danger without guaranteeing success.",
            "Each actor retains full agency over character dialogue and actions.",
        ],
    )
    character_cards = [
        CharacterCard(character_id="luna-planck", name="Luna Planck", pronouns="she/her", description="A botanist with a patient eye for stressed systems.", personality="Quietly curious, exact about uncertainty.", scenario=opening.setting, tags=["botanist", "observer"]),
        CharacterCard(character_id="mason-curie", name="Mason Curie", pronouns="he/him", description="A rugged marine biologist who treats pressure as practical fact.", personality="Measured, skeptical, materially minded.", scenario=opening.setting, tags=["marine-biologist", "containment"]),
        CharacterCard(character_id="higgs-sierra", name="Higgs Sierra", pronouns="she/her", description="An energetic stunt double with wildfire-safety habits.", personality="Embodied, decisive, always mapping exits.", scenario=opening.setting, tags=["stunt-double", "safety"]),
        CharacterCard(character_id="ivy-fermion", name="Ivy Fermion", pronouns="he/him", description="A playwright who grows herbs in the green room.", personality="Observant, relationship-aware, willing to name a cost.", scenario=opening.setting, tags=["playwright", "herbalist"]),
    ]
    if not include_williams:
        character_cards = [card for card in character_cards if card.character_id != "higgs-sierra"]
    world_books = [WorldBook(
        world_book_id="aether-caldera", name="Aether Caldera Field Guide",
        description="Shared playable facts and private director material.", token_budget=500,
        recursive_scanning=True,
        entries=[
            WorldBookEntry(entry_id="aether-layout", name="Aether layout", keys=["Aether"], constant=True, content="The Aether has a bridge, cooling orchard, observation blister, machine bay, and two pressure-rated transfer locks."),
            WorldBookEntry(entry_id="thermal-shield", name="Thermal shielding", keys=["shield", "heat", "caldera"], content="Thermal shielding buys minutes, not immunity. Cooling reserves can be redirected only by giving up propulsion, sensor clarity, or habitat stability."),
            WorldBookEntry(entry_id="basalt-archive", name="Basalt archive", keys=["signal", "pattern", "archive"], content="A repeating acoustic pattern points toward a sealed basalt observatory whose archive may outlast the crossing."),
            WorldBookEntry(entry_id="director-truth", name="Director truth", keys=["archive"], visibility="DIRECTOR_ONLY", content="The archive is a living environmental record, not a weapon or rescue device. Retrieving it should demand a material or relational cost, never a life."),
            WorldBookEntry(entry_id="luna-private", name="Luna recognition", keys=["growth", "orchard"], visibility="CHARACTER_PRIVATE", character_ids=["luna-planck"], content="The orchard's stress pattern resembles plants Luna once failed by intervening too quickly."),
        ],
    )]
    SeasonRepository(database).create(Season(
        season_id=season_id, season_number=2,
        title=f"{len(actors)}-model actor audition", status=SeasonStatus.ARMED,
        opening=opening, private_plan=plan, actors=actors, casting=casting, cast=cast,
        character_cards=character_cards, world_books=world_books,
        model_manifest=manifest.model_dump(mode="json"),
    ))
    records, schedules, queue = RecordRepository(database), ScheduleRepository(database), WorkQueue(database)
    pacific = ZoneInfo("America/Los_Angeles")
    for day in range(1, days + 1):
        for slot, hour in ((1, 6), (2, 12), (3, 18))[:sessions_per_day]:
            run_number = (day - 1) * sessions_per_day + slot
            local = datetime.combine(start_date + timedelta(days=day - 1), datetime.min.time(), tzinfo=pacific).replace(hour=hour)
            run_id = f"{season_id}-run-{run_number:02d}"
            schedule = ScheduleSlot(
                slot_id=run_id, season_id=season_id,
                day_number=day, slot_number=slot, run_number=run_number,
                scheduled_local=local, scheduled_utc=local.astimezone(timezone.utc), utc_offset="-07:00",
            )
            schedules.add(schedule)
            records.insert_run(run_id=run_id, season_id=season_id, slot_id=run_id, status="QUEUED")
            queue.enqueue(
                work_id=f"work:{run_id}", natural_key=f"run:{run_id}", kind="RUN_SCENE",
                payload={"season_id": season_id, "run_id": run_id, "day_number": day, "slot_number": slot},
                available_at=schedule.scheduled_utc.isoformat(), priority=run_number,
            )


async def _drain(worker, database, clock) -> None:
    rows = database.connection.execute(
        "SELECT r.run_id, s.scheduled_utc FROM runs r JOIN schedule_slots s ON s.slot_id=r.slot_id "
        "WHERE r.season_id=? ORDER BY s.run_number", (ACTOR_AUDITION_SEASON_ID,),
    ).fetchall()
    for row in rows:
        clock.set(datetime.fromisoformat(str(row["scheduled_utc"])).astimezone(timezone.utc))
        for _ in range(32):
            status = str(RecordRepository(database).get_run(str(row["run_id"]))["status"])
            if status in {"COMPLETED", "INTERRUPTED", "SKIPPED"}:
                break
            if await worker.drain_due(limit=1) == 0:
                queued_retry = database.connection.execute(
                    "SELECT available_at FROM work_items WHERE work_id=? AND status='QUEUED'",
                    (f"work:{row['run_id']}",),
                ).fetchone()
                if queued_retry is not None:
                    available_at = datetime.fromisoformat(str(queued_retry["available_at"]))
                    if available_at > clock.now().astimezone(timezone.utc):
                        clock.set(available_at.astimezone(timezone.utc))
                        continue
                raise ActorAuditionRehearsalError(f"no due work for {row['run_id']}")
        else:
            raise ActorAuditionRehearsalError(f"{row['run_id']} did not terminate")


def _all_canon(database) -> tuple[str, ...]:
    values = []
    for row in database.connection.execute(
        "SELECT payload_json FROM domain_events WHERE event_type='OrchestratorRoundAccepted' ORDER BY rowid"
    ):
        values.extend(json.loads(str(row[0])).get("canon_updates", []))
    return tuple(dict.fromkeys(str(value) for value in values))


def _episode_transcript(database) -> tuple[str, ...]:
    lines = []
    for row in database.connection.execute(
        "SELECT t.character_id,t.content_path,s.run_number FROM turns t JOIN runs r ON r.run_id=t.run_id "
        "JOIN schedule_slots s ON s.slot_id=r.slot_id WHERE r.season_id=? ORDER BY s.run_number,t.accepted_sequence",
        (ACTOR_AUDITION_SEASON_ID,),
    ):
        if row["content_path"]:
            lines.append(f"run {row['run_number']} {row['character_id']}: " + Path(str(row["content_path"])).read_text(encoding="utf-8"))
    return tuple(lines)


def _report(database, roots, manifest) -> ActorAuditionRehearsalReport:
    season = SeasonRepository(database).get(ACTOR_AUDITION_SEASON_ID)
    casting_by_character = {c.character_id: c.actor_id for c in season.casting}
    actors = {a.actor_id: a for a in season.actors}
    casting = tuple({
        "actor_id": c.actor_id, "actor_name": actors[c.actor_id].name,
        "character_id": c.character_id,
        "model": manifest.actor_binding(c.actor_id).model,
    } for c in season.casting)
    runs = tuple(dict(row) for row in database.connection.execute(
        "SELECT r.run_id,s.day_number,s.slot_number,r.status,r.turn_count,r.completion_reason, "
        "(SELECT COUNT(*) FROM turns t WHERE t.run_id=r.run_id AND t.disposition='NEUTRAL_INTERRUPTION') "
        "AS neutral_interruptions "
        "FROM runs r JOIN schedule_slots s ON s.slot_id=r.slot_id WHERE r.season_id=? ORDER BY s.run_number",
        (ACTOR_AUDITION_SEASON_ID,),
    ))
    diaries = tuple(dict(row) for row in database.connection.execute(
        "SELECT character_id,day_number,status,word_count,content_path FROM diaries WHERE season_id=? ORDER BY day_number,character_id",
        (ACTOR_AUDITION_SEASON_ID,),
    ))
    event = database.connection.execute(
        "SELECT payload_json FROM domain_events WHERE aggregate_id=? AND event_type='EpisodeResolutionCreated'",
        (ACTOR_AUDITION_SEASON_ID,),
    ).fetchone()
    resolution = json.loads(str(event[0])) if event else {}
    actor_evidence = []
    for character_id, actor_id in casting_by_character.items():
        calls = database.connection.execute(
            "SELECT COUNT(*) total,SUM(acceptance_status='ACCEPTED') accepted,SUM(acceptance_status='REJECTED') rejected "
            "FROM model_calls WHERE character_id=?", (character_id,),
        ).fetchone()
        actor_evidence.append({
            "actor_id": actor_id, "character_id": character_id,
            "accepted_calls": int(calls["accepted"] or 0), "rejected_calls": int(calls["rejected"] or 0),
            "total_calls": int(calls["total"] or 0),
            "diary_word_counts": [d["word_count"] for d in diaries if d["character_id"] == character_id],
            "review_questions": ["Did choices alter the fiction?", "Was the character voice distinct?", "Did the actor build on partners without forced consensus?"],
        })
    audit_row = database.connection.execute(
        "SELECT SUM(acceptance_status='ACCEPTED') accepted,SUM(acceptance_status='REJECTED') rejected,"
        "SUM(acceptance_status IS NULL OR acceptance_status='PENDING') pending FROM model_calls"
    ).fetchone()
    director_calls = int(database.connection.execute(
        "SELECT COUNT(*) FROM model_calls WHERE character_id='__orchestrator__'"
    ).fetchone()[0])
    return ActorAuditionRehearsalReport(
        season_id=ACTOR_AUDITION_SEASON_ID, casting=casting, runs=runs, diaries=diaries,
        resolution=resolution, actor_evidence=tuple(actor_evidence),
        director_evidence={
            "model": manifest.orchestrator.model, "director_model_calls": director_calls,
            "episode_phases": ["inciting_commitment", "complication_cost", "reversal_crisis", "climax_choice"],
            "resolution_recorded": bool(resolution),
            "review_questions": ["Is commitment visible by scene one?", "Does scene three reverse an assumption?", "Does the climax arise from actor choices?", "Does the aftermath clearly resolve the central question?"],
        },
        audit={key: int(audit_row[key] or 0) for key in ("accepted", "rejected", "pending")},
        unresolved=tuple(
            {"kind": "run", "id": str(row["run_id"]), "status": str(row["status"])}
            for row in database.connection.execute(
                "SELECT run_id,status FROM runs WHERE season_id=? AND status!='COMPLETED'", (ACTOR_AUDITION_SEASON_ID,)
            )
        ),
        publication="not attempted; all output remains private",
        public_archive_sha256=_tree_hash(roots.public),
    )


def _validate_complete(report: ActorAuditionRehearsalReport) -> None:
    actor_count = len(report.casting)
    expected_slots = actor_count * 4
    expected_diaries = actor_count * 2
    if len(report.runs) != 4 or any(
        r["status"] != "COMPLETED"
        or int(r["turn_count"]) + int(r.get("neutral_interruptions", 0)) != expected_slots
        for r in report.runs
    ):
        raise ActorAuditionRehearsalError(f"four complete {expected_slots}-slot scenes are required")
    if len(report.diaries) != expected_diaries or any(d["status"] not in {"WRITTEN", "LATE"} or not 300 <= int(d["word_count"] or 0) <= 800 for d in report.diaries):
        raise ActorAuditionRehearsalError(f"{expected_diaries} accepted 300-800 word diaries are required")
    if not report.resolution.get("complete") or report.resolution.get("outcome") not in {"SUCCESS", "COSTLY_SUCCESS", "COSTLY_FAILURE", "FAILURE"}:
        raise ActorAuditionRehearsalError("a complete terminal outcome is required")
    if report.audit["pending"] or report.unresolved:
        raise ActorAuditionRehearsalError("rehearsal has pending audit or unresolved runs")
    if report.public_archive_sha256 != hashlib.sha256().hexdigest():
        raise ActorAuditionRehearsalError("private rehearsal created public output")


__all__ = ["ACTOR_AUDITION_SEASON_ID", "ActorAuditionRehearsalError", "ActorAuditionRehearsalReport", "run_live_actor_audition_rehearsal"]
