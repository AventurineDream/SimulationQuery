import asyncio
from datetime import datetime, timezone

from improv_troupe.application.episode_resolution import (
    EpisodeResolutionService,
    _outcome_relabel_prompt,
    _review_outcome_relabel_scope,
    _resolution_correction_prompt,
    review_episode_resolution,
)
from improv_troupe.application import ModelCallExecutor
from improv_troupe.clock import VirtualClock
from improv_troupe.domain import HiddenSeasonPlan, OpeningSnapshot, ScheduleSlot, Season
from improv_troupe.infrastructure import RecordRepository, SQLiteDatabase, ScheduleRepository, SeasonRepository
from improv_troupe.llm import EpisodeResolutionEnvelope, ScriptedFakeClient, ScriptedStream


def _resolution(**updates):
    payload = {
        "outcome": "COSTLY_SUCCESS",
        "central_question_answered": "The archive is preserved while the vessel remains stranded.",
        "narration": "The archive settles into protected storage. The engine falls quiet, and ordinary ambient sounds return to the vessel.",
        "irreversible_change": "Propulsion is permanently disabled.",
        "gained": "The living archive remains intact.",
        "lost": "The vessel can no longer leave under its own power.",
        "hook": None,
        "canon_updates": ["The archive is protected.", "Propulsion is permanently disabled."],
        "complete": True,
    }
    payload.update(updates)
    return EpisodeResolutionEnvelope.model_validate(payload)


def test_resolution_rejects_cast_puppeteering():
    issue = review_episode_resolution(
        _resolution(narration="Ivy releases the override and Mason watches the archive settle."),
        actor_names=("Ivy Fermion", "Mason Curie"),
    )
    assert issue is not None
    assert issue.code == "ACTOR_PUPPETEERING"


def test_resolution_rejects_unqualified_success_with_major_loss():
    issue = review_episode_resolution(
        _resolution(outcome="SUCCESS"),
        actor_names=("Ivy", "Mason"),
    )
    assert issue is not None
    assert issue.code == "OUTCOME_COST_MISCLASSIFIED"


def test_resolution_accepts_costly_success_without_cast_actions():
    assert review_episode_resolution(
        _resolution(),
        actor_names=("Ivy", "Mason"),
    ) is None


def test_puppeteering_correction_requires_a_fresh_cast_free_narration():
    prompt = _resolution_correction_prompt("ACTOR_PUPPETEERING")

    assert "discard the rejected NARRATION" in prompt
    assert "contain none of the cast names" in prompt
    assert "Use only environmental and system-state subjects" in prompt
    assert "Keep every non-NARRATION field unchanged" in prompt


def test_rewritten_environmental_resolution_passes_the_autonomy_review():
    assert review_episode_resolution(
        _resolution(
            narration=(
                "The archive signal collapses into an unbroken line, and the observatory seal "
                "remains locked behind cooling haze. Manual bleed steadies the air circuit while "
                "the propulsion display stays dark. Heat fractures recede from the hull gauges, "
                "leaving the submarine intact but unable to recover the lost environmental "
                "record. Amber indicators settle over the console. The archive channel does not "
                "return; only the measured hiss of breathable air remains."
            )
        ),
        actor_names=("Ivy Fermion", "Mason Curie", "Luna Planck"),
    ) is None


def test_resolution_rejects_past_tense_cast_staging_from_v8_finale():
    issue = review_episode_resolution(
        _resolution(
            narration=(
                "The capsule tore free as molten fractures split the hull. Ivy watched the "
                "archive recede through the viewport, her breath steady despite the heat."
            )
        ),
        actor_names=("Ivy Fermion", "Mason Curie", "Luna Planck"),
    )

    assert issue is not None
    assert issue.code == "ACTOR_PUPPETEERING"


def test_outcome_relabel_prompt_allows_only_the_outcome_field():
    prompt = _outcome_relabel_prompt()

    assert "changing only OUTCOME" in prompt
    assert "COSTLY_SUCCESS" in prompt
    assert "Copy every other field exactly" in prompt


def test_outcome_relabel_scope_rejects_story_rewrites():
    original = _resolution(outcome="SUCCESS")

    assert _review_outcome_relabel_scope(
        original,
        _resolution(outcome="COSTLY_SUCCESS"),
    ) is None
    issue = _review_outcome_relabel_scope(
        original,
        _resolution(outcome="COSTLY_SUCCESS", lost="Only a little time is lost."),
    )
    assert issue is not None
    assert issue.code == "OUTCOME_RELABEL_SCOPE_DRIFT"


def test_resolution_gets_one_final_provenance_linked_outcome_relabel(tmp_path):
    database = SQLiteDatabase(tmp_path / "state" / "improv.sqlite3")
    database.migrate()
    season_id = "S01"
    run_id = "S01-run-04"
    SeasonRepository(database).create(Season(season_id=season_id, season_number=1))
    local = datetime.fromisoformat("2026-08-21T12:00:00-07:00")
    slot = ScheduleSlot(
        slot_id=run_id,
        season_id=season_id,
        day_number=2,
        slot_number=2,
        run_number=4,
        scheduled_local=local,
        scheduled_utc=local.astimezone(timezone.utc),
        utc_offset="-07:00",
    )
    ScheduleRepository(database).add(slot)
    RecordRepository(database).insert_run(
        run_id=run_id,
        season_id=season_id,
        slot_id=slot.slot_id,
        status="COMPLETED",
    )
    puppet = _resolution(
        outcome="SUCCESS",
        narration="Ivy releases the override while Mason watches the archive settle into protected storage.",
    )
    environmental = _resolution(outcome="SUCCESS")
    costly = _resolution(outcome="COSTLY_SUCCESS")
    client = ScriptedFakeClient(
        [
            ScriptedStream((puppet.model_dump_json(),)),
            ScriptedStream((environmental.model_dump_json(),)),
            ScriptedStream((costly.model_dump_json(),)),
        ]
    )
    clock = VirtualClock(datetime(2026, 8, 22, 1, tzinfo=timezone.utc))
    executor = ModelCallExecutor(
        database=database,
        client=client,
        clock=clock,
        audit_root=tmp_path / "private",
        backend="scripted-fake",
        model="director-model",
    )
    service = EpisodeResolutionService(
        season_id=season_id,
        final_run_id=run_id,
        opening=OpeningSnapshot(
            set="A sealed observatory",
            setting="A damaged submarine beneath a caldera.",
            cast=["Ivy Fermion", "Mason Curie"],
            world_rules=["Actor autonomy is preserved."],
        ),
        private_plan=HiddenSeasonPlan(
            premise="The archive may be saved at a permanent cost.",
            planned_tensions=["Cooling reserves are nearly exhausted."],
            hidden_mysteries=["The archive regulates the caldera."],
        ),
        orchestrator=executor,
    )

    result = asyncio.run(service.resolve(accepted_canon=(), final_transcript=()))

    assert result.outcome == "COSTLY_SUCCESS"
    calls = database.connection.execute(
        "SELECT call_id,attempt,acceptance_status,validator_code,correction_of_call_id "
        "FROM model_calls WHERE purpose='episode_resolution' ORDER BY attempt"
    ).fetchall()
    assert [row["acceptance_status"] for row in calls] == ["REJECTED", "REJECTED", "ACCEPTED"]
    assert calls[1]["correction_of_call_id"] == calls[0]["call_id"]
    assert calls[2]["correction_of_call_id"] == calls[1]["call_id"]
    assert calls[2]["validator_code"] is None
