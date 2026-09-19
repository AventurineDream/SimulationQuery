import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from improv_troupe.application import (
    ModelCallExecutor,
    SceneActor,
    SceneRunError,
    SceneRunner,
)
from improv_troupe.application.scene_runner import (
    _compile_director_beat,
    _director_plan_correction_instruction,
)
from improv_troupe.application.scene_runner import DirectorGameState
from improv_troupe.clock import VirtualClock
from improv_troupe.domain import HiddenSeasonPlan, OpeningSnapshot, RoleSheet, ScheduleSlot, Season
from improv_troupe.infrastructure import RecordRepository, SQLiteDatabase, ScheduleRepository, SeasonRepository
from improv_troupe.llm import ScriptedFakeClient, ScriptedStream
from improv_troupe.llm.structured import DirectorPlanEnvelope, OrchestratorEnvelope
from improv_troupe.domain.magic import MagicAdjudication, MagicOutcome


_OPENING = OpeningSnapshot(
    set="A lighthouse with no shoreline",
    setting="The first night of a reality show in a world where doors remember names.",
    cast=["Mara", "Nox", "Iris", "Sol"],
    world_rules=["No actor-on-actor violence.", "The cast can leave a scene by consent."],
)
_PLAN = HiddenSeasonPlan(
    premise="Something has invited four strangers to a lighthouse.",
    planned_tensions=["The doors are listening."],
    hidden_mysteries=["The invitation was written tomorrow."],
)
_MAGIC_TEST_CHALLENGE = "Can Mara confirm what happens to the cheetah's raised hind paw while it steps?"
_MAGIC_TEST_CRITERIA = (
    "The cheetah keeps weight off its raised right hind paw while stepping."
)


def _tagged_actor(
    label: str,
    *,
    wellness: str | None = None,
    magic_stat: str | None = None,
) -> ScriptedStream:
    signal = f"<WELLNESS_SIGNAL>{wellness}</WELLNESS_SIGNAL>" if wellness else ""
    stat = f"<MAGIC_STAT>{magic_stat}</MAGIC_STAT>" if magic_stat else ""
    return ScriptedStream((f"<ACTOR_TEXT>{label}</ACTOR_TEXT>{signal}{stat}",))


def _tagged_orchestrator(
    round_number: int,
    *,
    complete: bool = False,
    magic_challenge: str | None = None,
    magic_success_criteria: str | None = None,
) -> ScriptedStream:
    magic_fields = ""
    if magic_challenge is not None:
        magic_fields = (
            f"<MAGIC_CHALLENGE>{magic_challenge}</MAGIC_CHALLENGE>"
            "<MAGIC_MODIFIER>0</MAGIC_MODIFIER>"
        )
        if magic_success_criteria is not None:
            magic_fields += (
                f"<MAGIC_SUCCESS_CRITERIA>{magic_success_criteria}</MAGIC_SUCCESS_CRITERIA>"
            )
    return ScriptedStream(
        (
            f"<NARRATION>The lighthouse changes shape for round {round_number}.</NARRATION>"
            f"<NEXT_ACTOR>Mara</NEXT_ACTOR><COMPLETE>{str(complete).lower()}</COMPLETE>"
            f"<CANON_UPDATE>The round {round_number} threshold is real.</CANON_UPDATE>"
            f"{magic_fields}",
        )
    )


def _executor(database, client, audit_root, clock):
    return ModelCallExecutor(
        database=database,
        client=client,
        clock=clock,
        audit_root=audit_root,
        backend="scripted-fake",
        model="pilot-model",
    )


def _scene(tmp_path, *, orchestrator_responses, actor_clients=None):
    database = SQLiteDatabase(tmp_path / "state" / "improv.sqlite3")
    database.migrate()
    SeasonRepository(database).create(Season(season_id="S01", season_number=1))
    local = datetime.fromisoformat("2026-08-21T06:00:00-07:00")
    slot = ScheduleSlot(
        slot_id="S01-run-01",
        season_id="S01",
        day_number=1,
        slot_number=1,
        run_number=1,
        scheduled_local=local,
        scheduled_utc=local.astimezone(timezone.utc),
        utc_offset="-07:00",
    )
    ScheduleRepository(database).add(slot)
    RecordRepository(database).insert_run(
        run_id="S01-run-01",
        season_id="S01",
        slot_id=slot.slot_id,
        status="QUEUED",
    )
    clock = VirtualClock(datetime(2026, 8, 21, 13, tzinfo=timezone.utc))
    orchestrator = _executor(
        database,
        ScriptedFakeClient(orchestrator_responses),
        tmp_path / "private" / "orchestrator",
        clock,
    )
    actor_clients = actor_clients or [
        ScriptedFakeClient([_tagged_actor(f"{name} turn {n}") for n in range(1, 5)])
        for name in _OPENING.cast
    ]
    actors = tuple(
        SceneActor(
            character_id=f"char-{index}",
            name=name,
            role_sheet=RoleSheet(character_id=f"char-{index}", objectives=[f"Protect {name}"]),
            executor=_executor(
                database,
                actor_clients[index - 1],
                tmp_path / "private" / name.lower(),
                clock,
            ),
        )
        for index, name in enumerate(_OPENING.cast, start=1)
    )
    return database, clock, actors, orchestrator


def _runner(
    tmp_path,
    *,
    orchestrator_responses,
    actor_clients=None,
    two_pass_directing=False,
    forbidden_story_terms=(),
):
    database, clock, actors, orchestrator = _scene(
        tmp_path,
        orchestrator_responses=orchestrator_responses,
        actor_clients=actor_clients,
    )
    return (
        database,
        SceneRunner(
            run_id="S01-run-01",
            opening=_OPENING,
            private_plan=_PLAN,
            actors=actors,
            orchestrator=orchestrator,
            enforce_narrative_acceptance=two_pass_directing,
            two_pass_directing=two_pass_directing,
            forbidden_story_terms=forbidden_story_terms,
        ),
        clock,
    )


def _tagged_director_plan(
    round_number: int,
    *,
    scene_objective: str | None = None,
    adjudication: str | None = None,
    state_change: str | None = None,
    pressure: str | None = None,
    choice_a: str | None = None,
    next_actor: str = "Mara",
    complete: bool = False,
    choice_b: str | None = None,
    canon_updates: list[str] | None = None,
    magic_challenge: str | None = None,
    magic_success_criteria: str | None = None,
    magic_modifier: int = 0,
    magic_cost_type: str | None = None,
    magic_effect_detail: str | None = None,
) -> ScriptedStream:
    state_changes = (
        "A numbered key appears at the east landing.",
        "A silver thread descends from the clock room.",
        "A hanging compass points into the sealed pantry.",
        "An opened ledger names the keeper's route.",
    )
    pressures = (
        "The key fades when the next bell sounds.",
        "The thread burns away if the clock is wound.",
        "The pantry air is thinning before the next tide.",
        "The route closes at dawn unless the signal is answered.",
    )
    choices_a = (
        "Use the numbered key at the east landing.",
        "Climb the silver thread to the clock room.",
        "Carry the compass into the sealed pantry.",
        "Answer the keeper's route through the signal lens.",
    )
    choices_b = (
        "Study the numbered key before the bell.",
        "Wind the clock and test the thread from below.",
        "Hold the pantry door and map the compass bearing.",
        "Archive the route and leave the signal unanswered.",
    )
    index = round_number - 1
    selected_state_change = state_change or state_changes[index]
    selected_pressure = pressure or pressures[index]
    selected_choice_a = choice_a or choices_a[index]
    selected_choice_b = choice_b or choices_b[index]
    selected_canon_updates = canon_updates or [selected_state_change]
    magic_fields = ""
    if magic_challenge is not None:
        magic_fields += (
            f"<MAGIC_CHALLENGE>{magic_challenge}</MAGIC_CHALLENGE>"
            f"<MAGIC_MODIFIER>{magic_modifier}</MAGIC_MODIFIER>"
        )
    if magic_success_criteria is not None:
        magic_fields += (
            f"<MAGIC_SUCCESS_CRITERIA>{magic_success_criteria}</MAGIC_SUCCESS_CRITERIA>"
        )
    if magic_cost_type is not None:
        magic_fields += f"<MAGIC_COST_TYPE>{magic_cost_type}</MAGIC_COST_TYPE>"
    if magic_effect_detail is not None:
        magic_fields += f"<MAGIC_EFFECT_DETAIL>{magic_effect_detail}</MAGIC_EFFECT_DETAIL>"
    return ScriptedStream(
        (
            f"<SCENE_OBJECTIVE>{scene_objective or 'Find why the lighthouse remembers the cast before dawn.'}</SCENE_OBJECTIVE>"
            f"<ADJUDICATION>{adjudication or 'A prior move reveals a usable consequence.'}</ADJUDICATION>"
            f"<STATE_CHANGE>{selected_state_change}</STATE_CHANGE>"
            f"<PRESSURE>{selected_pressure}</PRESSURE>"
            f"<CHOICE_A>{selected_choice_a}</CHOICE_A>"
            f"<CHOICE_B>{selected_choice_b}</CHOICE_B>"
            f"<NEXT_ACTOR>{next_actor}</NEXT_ACTOR><COMPLETE>{str(complete).lower()}</COMPLETE>"
            "<CLOCK_CHANGE>mystery:+1</CLOCK_CHANGE>"
            + "".join(f"<CANON_UPDATE>{update}</CANON_UPDATE>" for update in selected_canon_updates)
            + magic_fields
        )
    )


def _tagged_director_render(round_number: int) -> ScriptedStream:
    state_changes = (
        "A numbered key appears at the east landing.",
        "A silver thread descends from the clock room.",
        "A hanging compass points into the sealed pantry.",
        "An opened ledger names the keeper's route.",
    )
    pressures = (
        "The key fades when the next bell sounds.",
        "The thread burns away if the clock is wound.",
        "The pantry air is thinning before the next tide.",
        "The route closes at dawn unless the signal is answered.",
    )
    choices_a = (
        "Use the numbered key at the east landing.",
        "Climb the silver thread to the clock room.",
        "Carry the compass into the sealed pantry.",
        "Answer the keeper's route through the signal lens.",
    )
    choices_b = (
        "Study the numbered key before the bell.",
        "Wind the clock and test the thread from below.",
        "Hold the pantry door and map the compass bearing.",
        "Archive the route and leave the signal unanswered.",
    )
    lead_ins = (
        "The lighthouse tilts.",
        "Around the lighthouse, a new measure appears.",
        "The lighthouse offers an unexpected opening.",
        "Within the lighthouse, the pattern finally shifts.",
    )
    index = round_number - 1
    state_change = state_changes[index]
    pressure = pressures[index]
    choice_a = choices_a[index]
    choice_b = choices_b[index]
    return ScriptedStream(
        (
            f"<NARRATION>{lead_ins[index]}</NARRATION>",
        )
    )


def test_magic_roll_is_persisted_and_the_next_plan_must_respect_it(tmp_path):
    cost = "wildlife support arrives twenty minutes later"
    responses = [
        _tagged_director_plan(
            1,
            magic_challenge=_MAGIC_TEST_CHALLENGE,
            magic_success_criteria=_MAGIC_TEST_CRITERIA,
        ),
        _tagged_director_render(1),
        _tagged_director_plan(
            2,
            adjudication="The recorded check establishes the paw's movement.",
            state_change="The paw's movement is now established.",
            pressure=cost,
            canon_updates=[cost],
            magic_cost_type="time",
            magic_effect_detail=cost,
        ),
        _tagged_director_render(2),
    ]
    actor_clients = [
        ScriptedFakeClient(
            [
                _tagged_actor(
                    "I read the cheetah's breathing from behind the glass.",
                    magic_stat="Intellect",
                ),
                _tagged_actor("I explain the visible signs without moving closer."),
            ]
        ),
        ScriptedFakeClient(
            [_tagged_actor("I keep the doorway clear."), _tagged_actor("I prepare a quiet room.")]
        ),
        ScriptedFakeClient(
            [_tagged_actor("I draw a map from the treehouse."), _tagged_actor("I stay with my twin.")]
        ),
        ScriptedFakeClient(
            [
                _tagged_actor("I mark the path without leaving the yard."),
                _tagged_actor("I ask what the map should show."),
            ]
        ),
    ]
    database, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=responses,
        actor_clients=actor_clients,
        two_pass_directing=True,
    )
    runner.max_rounds = 2
    runner.max_actor_turns = 8
    runner.die_roller = lambda: (3, 4)

    result = asyncio.run(runner.execute())

    roll_rows = database.connection.execute(
        "SELECT event_type, payload_json FROM domain_events "
        "WHERE event_type = 'MagicRollResolved'"
    ).fetchall()
    assert result.turns == 8
    assert len(roll_rows) == 1
    payload = json.loads(roll_rows[0]["payload_json"])
    assert payload["attribute"] == "Intellect"
    assert payload["die_faces"] == [3, 4]
    assert payload["total"] == 7
    assert payload["outcome"] == "costly_success"
    assert payload["challenge"] == _MAGIC_TEST_CHALLENGE
    assert payload["success_criteria"] == _MAGIC_TEST_CRITERIA
    assert runner._game_state.pending_magic_result is None
    assert runner._game_state.last_magic_roll["total"] == 7

    script = result.transcript.script_view()
    assert "MAGIC ROLL — Mara chose Intellect" in script
    assert script.index("Mara: I read the cheetah") < script.index("MAGIC ROLL")
    assert script.index("MAGIC ROLL") < script.index("Nox: I keep the doorway clear")
    accepted_plans = database.connection.execute(
        "SELECT payload_json FROM domain_events WHERE event_type = 'DirectorPlanAccepted' "
        "ORDER BY created_at, event_id"
    ).fetchall()
    second_plan = json.loads(accepted_plans[1]["payload_json"])["plan"]
    assert second_plan["magic_cost_type"] == "time"
    assert "magic_result_ack" not in second_plan
    assert "magic_goal_answer" not in second_plan
    assert (
        "MAGIC result: costly success; goal achieved: "
        + _MAGIC_TEST_CRITERIA
        + "; time cost: "
        + cost
    ) in script
    adjudication = json.loads(accepted_plans[1]["payload_json"])["magic_adjudication"]
    assert adjudication["outcome"] == "costly_success"
    assert adjudication["goal_status"] == "achieved"
    assert adjudication["goal_answer"] == _MAGIC_TEST_CRITERIA

    runner._hydrate()
    replayed_script = runner.transcript.script_view()
    assert replayed_script.count("MAGIC ROLL —") == 1
    assert runner._game_state.pending_magic_result is None
    assert runner._game_state.last_magic_roll["outcome"] == "costly_success"
    assert runner._game_state.last_magic_roll["success_criteria"] == _MAGIC_TEST_CRITERIA


def test_compiled_magic_beat_has_room_for_exact_runtime_receipt():
    plan = DirectorPlanEnvelope(
        scene_objective="What does the cheetah's posture reveal about its raised right hind leg?",
        adjudication="The recorded check leaves a new opening.",
        state_change=(
            "The raised paw remains unconfirmed while the porch camera preserves a longer view "
            "of its weight shifts and timing."
        ),
        pressure=(
            "Wildlife support must be called before the animal moves, while the family keeps "
            "the porch quiet and the doorway clear."
        ),
        choice_a="Review the porch camera arrival clip and compare each visible step.",
        choice_b="Observe weight shifts from the doorway and mark the timing by hand.",
        next_actor="Mara Bell",
        clock_changes=[{"clock": "mystery", "change": 1}],
        canon_updates=["The camera clip remains available."],
        magic_effect_detail=(
            "A faint tremor marks the paw as it lowers, adding a new observable clue without "
            "settling the cause, severity, or veterinary meaning of the movement."
        ),
    )
    criteria = (
        "Mara confirms the cheetah keeps weight off its raised right hind paw while stepping, "
        "using posture, weight, timing, distance, sound, and camera records without diagnosis."
    )
    compiled = _compile_director_beat(
        "Sunlight slants across the porch steps.",
        plan,
        "the Bell family porch",
        magic_adjudication=MagicAdjudication.from_outcome(
            outcome=MagicOutcome.SETBACK,
            success_criteria=criteria,
        ),
    )

    assert len(compiled) > 720
    assert OrchestratorEnvelope(narration=compiled).narration == compiled
    assert SceneRunner._review_director_render(compiled, plan, max_words=160) is None


def test_single_pass_director_switches_to_structured_adjudication_after_a_magic_roll(tmp_path):
    responses = [
        _tagged_orchestrator(
            1,
            magic_challenge="Can Mara interpret the cheetah's breathing from a safe distance?",
            magic_success_criteria="Mara identifies the breathing rhythm from a safe distance.",
        ),
        _tagged_director_plan(
            2,
            adjudication="The check remains unresolved.",
            state_change="The check remains unresolved.",
            pressure="A fresh track leads toward the creek.",
            canon_updates=["A fresh track leads toward the creek."],
            magic_effect_detail="A fresh track leads toward the creek.",
        ),
        _tagged_director_render(2),
    ]
    actor_clients = [
        ScriptedFakeClient(
            [
                _tagged_actor("I note the uneven rhythm and stay behind the window.", magic_stat="Cool"),
                _tagged_actor("I show the others the timing I recorded."),
            ]
        ),
        ScriptedFakeClient([_tagged_actor("I leave the porch door shut."), _tagged_actor("I prepare a blanket outside.")]),
        ScriptedFakeClient([_tagged_actor("I sketch the pattern from the treehouse."), _tagged_actor("I keep the sketch to myself.")]),
        ScriptedFakeClient([_tagged_actor("I compare the beats with the lawn sensor."), _tagged_actor("I ask to share the data.")]),
    ]
    database, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=responses,
        actor_clients=actor_clients,
    )
    runner.max_rounds = 2
    runner.max_actor_turns = 8
    runner.die_roller = lambda: (1, 2)

    result = asyncio.run(runner.execute())

    roll = database.connection.execute(
        "SELECT payload_json FROM domain_events WHERE event_type = 'MagicRollResolved'"
    ).fetchone()
    assert result.turns == 8
    assert json.loads(roll["payload_json"])["total"] == 3
    assert json.loads(roll["payload_json"])["outcome"] == "setback"
    assert runner._game_state.pending_magic_result is None
    assert runner._game_state.last_magic_roll["outcome"] == "setback"
    assert runner._game_state.last_magic_adjudication.goal_status.value == "not_achieved"
    assert "MAGIC result: setback; goal not achieved:" in result.transcript.script_view()
    state_event = database.connection.execute(
        "SELECT payload_json FROM domain_events WHERE event_type = 'OrchestratorRoundAccepted' "
        "AND json_extract(payload_json, '$.round_number') = 1"
    ).fetchone()
    assert json.loads(state_event["payload_json"])["magic_state"]["next_actor"] == "Mara"


def test_required_magic_rehearsal_corrects_a_director_plan_that_omits_the_challenge(tmp_path):
    responses = [
        _tagged_director_plan(1),
        _tagged_director_plan(
            1,
            magic_challenge="Can Mara identify the injury signs from a safe distance?",
            magic_success_criteria="Mara identifies one visible sign without approaching.",
        ),
        _tagged_director_render(1),
    ]
    actor_clients = [
        ScriptedFakeClient(
            [_tagged_actor("I watch the animal's posture from behind the window.", magic_stat="Cool")]
        ),
        ScriptedFakeClient([_tagged_actor("I keep the porch clear.")]),
        ScriptedFakeClient([_tagged_actor("I look for prints from the treehouse.")]),
        ScriptedFakeClient([_tagged_actor("I record what changed without approaching.")]),
    ]
    database, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=responses,
        actor_clients=actor_clients,
        two_pass_directing=True,
    )
    runner.max_rounds = 1
    runner.max_actor_turns = 4
    runner.require_magic_challenge = True
    runner.die_roller = lambda: (6, 4)

    result = asyncio.run(runner.execute())

    assert result.turns == 4
    assert database.connection.execute(
        "SELECT COUNT(*) FROM domain_events WHERE event_type = 'MagicRollResolved'"
    ).fetchone()[0] == 1
    assert database.connection.execute(
        "SELECT validator_code FROM model_calls "
        "WHERE purpose = 'director_plan_round:1' AND attempt = 1"
    ).fetchone()[0] == "MAGIC_CHALLENGE_REQUIRED"


def test_magic_rehearsal_correction_enforces_the_approved_actor_challenge_and_modifier(tmp_path):
    challenge = "Can Mara assess the cheetah's posture from a safe distance?"
    responses = [
        _tagged_director_plan(
            1,
            next_actor="Nox",
            magic_challenge="Can Nox test the lighthouse door?",
            magic_success_criteria="Nox confirms whether the door opens from the landing.",
            magic_modifier=2,
        ),
        _tagged_director_plan(
            1,
            next_actor="Mara",
            magic_challenge=challenge,
            magic_success_criteria="Mara assesses the cheetah's posture from a safe distance.",
            magic_modifier=0,
        ),
        _tagged_director_render(1),
    ]
    actor_clients = [
        ScriptedFakeClient(
            [_tagged_actor("I watch the cheetah's posture from behind the window.", magic_stat="Cool")]
        ),
        ScriptedFakeClient([_tagged_actor("I keep the porch clear.")]),
        ScriptedFakeClient([_tagged_actor("I look for prints from the treehouse.")]),
        ScriptedFakeClient([_tagged_actor("I record what changed without approaching.")]),
    ]
    database, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=responses,
        actor_clients=actor_clients,
        two_pass_directing=True,
    )
    runner.max_rounds = 1
    runner.max_actor_turns = 4
    runner.require_magic_challenge = True
    runner.required_magic_next_actor = "Mara"
    runner.required_magic_challenge_text = challenge
    runner.required_magic_modifier = 0
    runner.die_roller = lambda: (6, 6)

    result = asyncio.run(runner.execute())

    assert result.turns == 4
    attempts = database.connection.execute(
        "SELECT attempt,validator_code,acceptance_status FROM model_calls "
        "WHERE purpose='director_plan_round:1' ORDER BY attempt"
    ).fetchall()
    assert attempts[0]["validator_code"] == "MAGIC_CHALLENGE_SETUP_REQUIRED"
    assert attempts[1]["acceptance_status"] == "ACCEPTED"
    accepted_plan = json.loads(
        database.connection.execute(
            "SELECT payload_json FROM domain_events WHERE event_type='DirectorPlanAccepted'"
        ).fetchone()[0]
    )["plan"]
    assert accepted_plan["next_actor"] == "Mara"
    assert accepted_plan["magic_challenge"] == challenge
    assert accepted_plan["magic_modifier"] == 0


def test_locked_magic_opening_rejects_a_pre_roll_diagnosis(tmp_path):
    _, runner, _ = _runner(tmp_path, orchestrator_responses=[], two_pass_directing=True)
    locked = DirectorPlanEnvelope(
        scene_objective="What does the cheetah's posture reveal about its raised hind leg?",
        adjudication="The raised paw is visible; cause and severity remain unknown.",
        state_change="The cheetah rests in porch shade with one hind paw raised.",
        pressure="The family must keep the porch quiet until help arrives.",
        choice_a="Study its weight shifts from the doorway.",
        choice_b="Review the porch camera's first steps.",
        next_actor="Mara",
        clock_changes=[{"clock": "mystery", "change": 1}],
        canon_updates=["No one has approached or touched the cheetah."],
        magic_challenge="Can Mara read its posture from a safe distance?",
        magic_success_criteria="Mara confirms whether its raised hind paw touches the porch.",
    )
    runner.required_magic_opening_plan = locked

    assert runner._review_director_plan(locked, 1) is None
    pre_solved = locked.model_copy(
        update={"adjudication": "Mara identifies a sprain from the cheetah's posture."}
    )

    issue = runner._review_director_plan(pre_solved, 1)

    assert issue is not None
    assert issue.code == "MAGIC_REHEARSAL_OPENING_LOCKED"


def test_magic_attempt_correction_removes_a_pre_roll_diagnosis(tmp_path):
    challenge = "Can Mara assess the cheetah's leg from the porch?"
    responses = [
        _tagged_director_plan(
            1,
            magic_challenge=challenge,
            magic_success_criteria="Mara records the cheetah's weight shifts without approaching.",
        ),
        _tagged_director_render(1),
    ]
    actor_clients = [
        ScriptedFakeClient(
            [
                _tagged_actor("I can tell the leg has a sprain.", magic_stat="Intellect"),
                _tagged_actor(
                    "I watch how the raised paw meets the porch boards and record each shift.",
                    magic_stat="Intellect",
                ),
            ]
        ),
        ScriptedFakeClient([_tagged_actor("I keep the doorway quiet.")]),
        ScriptedFakeClient([_tagged_actor("I watch from the treehouse.")]),
        ScriptedFakeClient([_tagged_actor("I mark the time without approaching.")]),
    ]
    database, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=responses,
        actor_clients=actor_clients,
        two_pass_directing=True,
    )
    runner.max_rounds = 1
    runner.max_actor_turns = 4
    runner.forbidden_magic_attempt_terms = ("sprain",)
    runner.die_roller = lambda: (2, 2)

    result = asyncio.run(runner.execute())

    assert result.turns == 4
    attempts = database.connection.execute(
        "SELECT attempt,validator_code,acceptance_status FROM model_calls "
        "WHERE purpose IN ('actor_turn:char-1:round:1', 'actor_correction:char-1:round:1') "
        "ORDER BY rowid"
    ).fetchall()
    assert attempts[0]["validator_code"] == "MAGIC_ATTEMPT_PREMATURE_RESULT"
    assert attempts[1]["acceptance_status"] == "ACCEPTED"
    accepted_turn = database.connection.execute(
        "SELECT disposition,content_path FROM turns "
        "WHERE run_id='S01-run-01' AND character_id='char-1'"
    ).fetchone()
    assert accepted_turn["disposition"] == "ACCEPT_AFTER_CORRECTION"
    accepted_text = Path(accepted_turn["content_path"]).read_text(encoding="utf-8")
    assert "sprain" not in accepted_text.casefold()
    correction_call = database.connection.execute(
        "SELECT prompt_path FROM model_calls "
        "WHERE purpose='actor_correction:char-1:round:1'"
    ).fetchone()
    correction_prompt = Path(tmp_path / "private" / "mara" / correction_call[0]).read_text()
    assert "FORBIDDEN MAGIC ATTEMPT TERMS FOUND IN REJECTED TURN: sprain" in correction_prompt
    assert "close medical synonym" in correction_prompt
    assert "observation-only language" in correction_prompt
    roll = database.connection.execute(
        "SELECT payload_json FROM domain_events WHERE event_type='MagicRollResolved'"
    ).fetchone()
    assert json.loads(roll["payload_json"])["attribute"] == "Intellect"


@pytest.mark.parametrize(
    ("outcome", "cost_type", "effect_detail", "expected_issue"),
    [
        ("clean_success", None, "The paw lands softly on the porch.", None),
        (
            "costly_success",
            "time",
            "Wildlife support arrives twenty minutes later.",
            None,
        ),
        ("setback", None, "A fresh track leads toward the creek.", None),
        (
            "costly_success",
            None,
            "Wildlife support arrives twenty minutes later.",
            "MAGIC_OUTCOME_CONSEQUENCE_REQUIRED",
        ),
        (
            "setback",
            "time",
            "A fresh track leads toward the creek.",
            "MAGIC_OUTCOME_CONSEQUENCE_REQUIRED",
        ),
        (
            "clean_success",
            "time",
            "The paw lands softly on the porch.",
            "MAGIC_OUTCOME_CONSEQUENCE_REQUIRED",
        ),
        ("clean_success", None, None, "MAGIC_OUTCOME_CONSEQUENCE_REQUIRED"),
    ],
)
def test_magic_outcome_contract_validates_only_director_consequence_inputs(
    tmp_path, outcome, cost_type, effect_detail, expected_issue
):
    _, runner, _ = _runner(tmp_path, orchestrator_responses=[], two_pass_directing=True)
    runner._game_state.record_magic_roll(
        {
            "attribute": "Intellect",
            "attribute_score": 3,
            "die_faces": [
                {"clean_success": 5, "costly_success": 3, "setback": 2}[outcome],
                {"clean_success": 5, "costly_success": 4, "setback": 3}[outcome],
            ],
            "situational_modifier": 0,
            "total": {"clean_success": 10, "costly_success": 7, "setback": 5}[outcome],
            "outcome": outcome,
            "challenge": _MAGIC_TEST_CHALLENGE,
            "success_criteria": _MAGIC_TEST_CRITERIA,
        }
    )
    pressure = effect_detail or "The family keeps the porch calm while support is on its way."
    plan = DirectorPlanEnvelope(
        scene_objective="Find what the cheetah's posture means for its raised hind leg.",
        adjudication="The runtime records the result of the accepted check.",
        state_change="The runtime records the changed situation.",
        pressure=pressure,
        choice_a="Keep observing from the doorway.",
        choice_b="Use the porch camera to review its steps.",
        next_actor="Mara",
        clock_changes=[{"clock": "mystery", "change": 1}],
        canon_updates=[effect_detail or "The result remains pending."],
        magic_cost_type=cost_type,
        magic_effect_detail=effect_detail,
    )

    issue = runner._review_director_plan(plan, 2)

    if expected_issue is None:
        assert issue is None
    else:
        assert issue is not None
        assert issue.code == expected_issue


def _valid_costly_magic_plan() -> DirectorPlanEnvelope:
    cost = "Wildlife support arrives twenty minutes later."
    return DirectorPlanEnvelope(
        scene_objective="Find what the cheetah's posture means for its raised hind leg.",
        adjudication="The runtime records the achieved goal.",
        state_change="The achieved goal changes the situation.",
        pressure=cost,
        choice_a="Keep observing from the doorway.",
        choice_b="Use the porch camera to review its steps.",
        next_actor="Mara",
        clock_changes=[{"clock": "mystery", "change": 1}],
        canon_updates=[cost],
        magic_cost_type="time",
        magic_effect_detail=cost,
    )


@pytest.mark.parametrize(
    "field_name",
    (
        "scene_objective",
        "adjudication",
        "state_change",
        "pressure",
        "choice_a",
        "choice_b",
        "canon_updates",
        "magic_effect_detail",
    ),
)
def test_forbidden_magic_result_claims_are_scanned_across_the_entire_plan(
    tmp_path, field_name
):
    _, runner, _ = _runner(tmp_path, orchestrator_responses=[], two_pass_directing=True)
    runner._game_state.record_magic_roll(
        {
            "attribute": "Intellect",
            "attribute_score": 3,
            "die_faces": [3, 4],
            "situational_modifier": 0,
            "total": 7,
            "outcome": "costly_success",
            "challenge": _MAGIC_TEST_CHALLENGE,
            "success_criteria": _MAGIC_TEST_CRITERIA,
        }
    )
    runner.forbidden_magic_result_terms = ("ligament",)
    plan = _valid_costly_magic_plan()
    forbidden = "Possible ligament damage is mentioned."
    updates = {
        "scene_objective": plan.scene_objective + " Possible ligament damage is mentioned.",
        "adjudication": forbidden,
        "state_change": forbidden,
        "pressure": plan.magic_effect_detail + " " + forbidden,
        "choice_a": plan.choice_a + " Possible ligament damage is mentioned.",
        "choice_b": plan.choice_b + " Possible ligament damage is mentioned.",
        "canon_updates": [*plan.canon_updates, forbidden],
        "magic_effect_detail": plan.magic_effect_detail + " " + forbidden,
    }
    plan = plan.model_copy(update={field_name: updates[field_name]})

    issue = runner._review_director_plan(plan, 2)

    assert issue is not None
    assert issue.code == "MAGIC_RESULT_CLAIM_UNSUPPORTED"


def test_runtime_adjudication_owns_result_status_and_answer(tmp_path):
    _, runner, _ = _runner(tmp_path, orchestrator_responses=[], two_pass_directing=True)
    runner._game_state.record_magic_roll(
        {
            "attribute": "Intellect",
            "attribute_score": 3,
            "die_faces": [3, 4],
            "situational_modifier": 0,
            "total": 7,
            "outcome": "costly_success",
            "challenge": _MAGIC_TEST_CHALLENGE,
            "success_criteria": _MAGIC_TEST_CRITERIA,
        }
    )

    adjudication = runner._game_state.pending_magic_adjudication
    assert adjudication is not None
    assert adjudication.outcome.value == "costly_success"
    assert adjudication.goal_status.value == "achieved"
    assert adjudication.goal_answer == _MAGIC_TEST_CRITERIA
    assert runner._review_magic_outcome_consequence(_valid_costly_magic_plan()) is None


def test_magic_detail_is_runtime_compiled_without_cross_field_copy(tmp_path):
    _, runner, _ = _runner(tmp_path, orchestrator_responses=[], two_pass_directing=True)
    runner._game_state.record_magic_roll(
        {
            "attribute": "Intellect",
            "attribute_score": 3,
            "die_faces": [3, 4],
            "situational_modifier": 0,
            "total": 7,
            "outcome": "costly_success",
            "challenge": _MAGIC_TEST_CHALLENGE,
            "success_criteria": _MAGIC_TEST_CRITERIA,
        }
    )
    detail = "Mara spends twenty minutes reviewing the frozen feed."
    plan = _valid_costly_magic_plan().model_copy(
        update={
            "pressure": "The support window closes before the family can call.",
            "canon_updates": ["The porch camera remains unavailable to the family."],
            "magic_effect_detail": detail,
        }
    )

    assert runner._review_magic_outcome_consequence(plan) is None
    visible_beat = _compile_director_beat(
        "The family watches from the kitchen doorway.",
        plan,
        "the shaded porch",
        magic_adjudication=runner._game_state.pending_magic_adjudication,
    )
    assert detail in visible_beat
    assert plan.pressure in visible_beat


def test_invalid_magic_roll_does_not_partially_mutate_runtime_state():
    state = DirectorGameState()
    state.pending_magic_challenge = _MAGIC_TEST_CHALLENGE
    state.pending_magic_success_criteria = _MAGIC_TEST_CRITERIA
    state.pending_magic_actor = "char-1"
    state.pending_magic_modifier = 1

    with pytest.raises(ValueError, match="MAGIC total does not match"):
        state.answer_magic_challenge(
            character_id="char-1",
            name="Mara",
            roll={
                "attribute": "Intellect",
                "attribute_score": 3,
                "die_faces": [3, 4],
                "situational_modifier": 0,
                "total": 6,
                "outcome": "costly_success",
                "challenge": _MAGIC_TEST_CHALLENGE,
                "success_criteria": _MAGIC_TEST_CRITERIA,
            },
        )

    assert state.pending_magic_challenge == _MAGIC_TEST_CHALLENGE
    assert state.pending_magic_success_criteria == _MAGIC_TEST_CRITERIA
    assert state.pending_magic_actor == "char-1"
    assert state.pending_magic_modifier == 1
    assert state.last_magic_roll is None
    assert state.pending_magic_result is None
    assert state.pending_magic_adjudication is None


def test_recording_a_valid_magic_roll_commits_and_clears_the_pending_challenge():
    state = DirectorGameState(
        pending_magic_challenge=_MAGIC_TEST_CHALLENGE,
        pending_magic_success_criteria=_MAGIC_TEST_CRITERIA,
        pending_magic_actor="char-1",
        pending_magic_modifier=0,
    )

    state.record_magic_roll(
        {
            "attribute": "Intellect",
            "attribute_score": 3,
            "die_faces": [3, 4],
            "situational_modifier": 0,
            "total": 7,
            "outcome": "costly_success",
            "challenge": _MAGIC_TEST_CHALLENGE,
            "success_criteria": _MAGIC_TEST_CRITERIA,
        }
    )

    assert state.last_magic_roll is not None
    assert state.pending_magic_challenge is None
    assert state.pending_magic_actor is None
    assert state.pending_magic_modifier == 0
    assert state.pending_magic_adjudication is not None


def test_precommitted_success_criteria_survive_roll_until_consequence_is_accepted():
    state = DirectorGameState()
    opening = _valid_costly_magic_plan().model_copy(
        update={
            "magic_challenge": _MAGIC_TEST_CHALLENGE,
            "magic_success_criteria": _MAGIC_TEST_CRITERIA,
            "magic_cost_type": None,
            "magic_effect_detail": None,
        }
    )
    state.apply(opening)
    assert state.pending_magic_success_criteria == _MAGIC_TEST_CRITERIA

    state.answer_magic_challenge(
        character_id="char-1",
        name="Mara",
        roll={
            "challenge": _MAGIC_TEST_CHALLENGE,
            "success_criteria": _MAGIC_TEST_CRITERIA,
            "attribute": "Intellect",
            "attribute_score": 3,
            "die_faces": [3, 4],
            "situational_modifier": 0,
            "total": 7,
            "outcome": "costly_success",
        },
    )
    assert state.pending_magic_result == "costly_success"
    assert state.pending_magic_success_criteria == _MAGIC_TEST_CRITERIA
    assert state.pending_magic_adjudication is not None

    state.apply(
        _valid_costly_magic_plan(),
        magic_adjudication=state.pending_magic_adjudication,
    )
    assert state.pending_magic_result is None
    assert state.pending_magic_success_criteria is None
    assert state.pending_magic_adjudication is None
    assert state.last_magic_adjudication is not None
    assert state.last_magic_adjudication.goal_answer == _MAGIC_TEST_CRITERIA


def test_postroll_correction_directive_mentions_only_consequence_inputs(tmp_path):
    _, runner, _ = _runner(tmp_path, orchestrator_responses=[], two_pass_directing=True)
    runner._game_state.record_magic_roll(
        {
            "attribute": "Intellect",
            "attribute_score": 3,
            "die_faces": [2, 3],
            "situational_modifier": 0,
            "total": 5,
            "outcome": "setback",
            "challenge": _MAGIC_TEST_CHALLENGE,
            "success_criteria": _MAGIC_TEST_CRITERIA,
        }
    )

    directive = runner._magic_result_correction_directive()

    assert "POST-ROLL MAGIC CONSEQUENCE CORRECTION" in directive
    assert "runtime owns the recorded MAGIC outcome, goal status, and goal answer" in directive
    assert "magic_effect_detail" in directive
    assert "magic_cost_type" in directive
    assert "magic_result_ack" not in directive
    assert "magic_goal_status" not in directive
    assert "magic_goal_answer" not in directive


def test_scene_runner_completes_four_rounds_and_is_idempotent(tmp_path):
    database, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=[_tagged_orchestrator(n) for n in range(1, 5)],
    )

    result = asyncio.run(runner.execute())

    assert result.reason == "turn_limit"
    assert result.turns == 16
    assert result.transcript.line_count == 16
    assert result.transcript.turns[0].kind == "direction"
    assert database.connection.execute("SELECT status FROM runs").fetchone()[0] == "COMPLETED"
    assert database.connection.execute("SELECT turn_count FROM runs").fetchone()[0] == 16
    assert database.connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0] == 20
    assert database.connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0] == 20
    accepted = database.connection.execute(
        "SELECT turn_id, round_number, disposition, accepted_sequence, "
        "caused_by_turn_id, accepted_at FROM turns ORDER BY accepted_sequence"
    ).fetchall()
    assert [row["accepted_sequence"] for row in accepted] == list(range(1, 21))
    assert all(row["accepted_at"] == "2026-08-21T13:00:00+00:00" for row in accepted)
    for row in accepted:
        if row["disposition"] == "NARRATION_ACCEPT":
            assert row["caused_by_turn_id"] is None
        else:
            assert row["caused_by_turn_id"] == f"S01-run-01:stage:{row['round_number']}"

    replay = asyncio.run(runner.execute())

    assert replay.reason == "turn_limit"
    assert replay.turns == 16
    assert database.connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0] == 20


@pytest.mark.parametrize(
    "objective,accepted",
    [
        ("Does the archive hold a record of survival— or proof that survival is impossible?", True),
        ("  Does the archive hold a record of survival — or proof that survival is impossible?  ", True),
        ("Does\tthe archive hold a record of survival—\n or proof that survival is impossible?", True),
        ("Does the archive hold a record of survival—\u00a0or proof that survival is impossible?", True),
        ("Does the archive hold a record of survival—or proof that survival is possible?", False),
        ("Does the archive hold a record of survival—or proof that survivalis impossible?", False),
        ("Does the archive hold a record of survival—or proof that survival is impossible!", False),
    ],
)
def test_director_objective_ignores_cosmetic_whitespace_only(tmp_path, objective, accepted):
    _, runner, _ = _runner(tmp_path, orchestrator_responses=[], two_pass_directing=True)
    canonical = "Does the archive hold a record of survival—or proof that survival is impossible?"
    runner._game_state.scene_objective = canonical
    plan = DirectorPlanEnvelope(
        scene_objective=objective,
        adjudication="The archive rhythm matches the thermal cycle.",
        state_change="The archive interface opens.",
        pressure="Cooling reserves approach their limit.",
        choice_a="Retrieve the remaining archive data.",
        choice_b="Seal the interface to preserve cooling.",
        next_actor="Mara",
        clock_changes=[{"clock": "mystery", "change": 1}],
        canon_updates=["Archive interface is open."],
    )

    issue = runner._review_director_plan(plan, 4)

    if accepted:
        assert issue is None
    else:
        assert issue is not None
        assert issue.code == "SCENE_OBJECTIVE_DRIFT"
    assert runner._game_state.scene_objective == canonical
    assert plan.scene_objective == objective


def test_two_pass_director_persists_a_game_plan_and_renders_its_choices(tmp_path):
    responses = []
    for round_number in range(1, 5):
        responses.extend((_tagged_director_plan(round_number), _tagged_director_render(round_number)))
    database, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=responses,
        two_pass_directing=True,
    )

    result = asyncio.run(runner.execute())

    assert result.turns == 16
    assert database.connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0] == 24
    plans = database.connection.execute(
        "SELECT payload_json FROM domain_events WHERE event_type = 'DirectorPlanAccepted' ORDER BY created_at, event_id"
    ).fetchall()
    assert len(plans) == 4
    assert '"scene_objective": "Find why the lighthouse remembers the cast before dawn."' in plans[0][0]
    script = result.transcript.script_view()
    assert "Choice A: Use the numbered key at the east landing." in script
    assert "Choice B: Study the numbered key before the bell." in script


def test_v16_mint_loss_passes_director_plan_review(tmp_path):
    _, runner, _ = _runner(tmp_path, orchestrator_responses=[], two_pass_directing=True)
    plan = DirectorPlanEnvelope(
        scene_objective="What material cost does preserving the living archive demand?",
        adjudication="Hull seals; mint pulse fades to silence.",
        state_change="Mint withers completely; archive resonance stops.",
        pressure="Fusion core overheats; three minutes to failure.",
        choice_a="Vent heat, lose habitat stability.",
        choice_b="Keep heat, lose cooling reserve.",
        next_actor="Mara",
        clock_changes=[{"clock": "danger", "change": 1}, {"clock": "relationship", "change": -1}],
        canon_updates=["Mint plant is dead; no pulse remains.", "Archive record is inert; living quality lost."],
    )
    assert runner._review_director_plan(plan, 3) is None


def test_director_plan_repetition_guard_keeps_active_state_terms_live(tmp_path):
    _, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=[],
        two_pass_directing=True,
    )
    active_state = "Archive signal now pulses in sync with slurry fracture rhythm."
    stale_texture = "Metallic conduits shimmer beneath amber instrumentation."
    runner.transcript.add_direction(active_state)
    runner.transcript.add_direction(active_state)
    runner.transcript.add_direction(stale_texture)
    runner.transcript.add_direction(stale_texture)
    runner._game_state.last_state_change = active_state
    runner._game_state.last_pressure = "Habitat O2: 53% (no recovery path)"

    spent = runner._active_plan_spent_imagery()
    assert "archive" not in spent
    assert "pulse" not in spent
    assert "slurry" not in spent
    assert "metallic" in spent

    plan = DirectorPlanEnvelope(
        scene_objective="What does preserving a living record demand?",
        adjudication="The archive signal syncs with slurry fracture rhythm.",
        state_change="Slurry growth now pulses in rhythm with archive signal.",
        pressure="Habitat O2: 53% (no recovery path).",
        choice_a="Sever the archive from slurry.",
        choice_b="Feed one final pulse to preserve the record.",
        next_actor="Mara",
        clock_changes=[{"clock": "danger", "change": 1}],
        canon_updates=["Archive signal remains linked to slurry growth."],
    )
    assert runner._review_director_plan(plan, 4) is None


def test_death_cost_correction_explicitly_replaces_only_lethal_stakes():
    prompt = _director_plan_correction_instruction("DIRECTOR_SENSITIVE_STAKES")
    assert "required exception to preserving the rejected cost" in prompt
    assert "severe but nonlethal" in prompt
    assert "deadline, urgency" in prompt


def test_magic_result_correction_names_offending_terms_and_requires_observation_only_language():
    prompt = _director_plan_correction_instruction(
        "MAGIC_RESULT_CLAIM_UNSUPPORTED",
        forbidden_magic_terms=("torn", "trauma"),
    )
    assert "torn, trauma" in prompt
    assert "close medical synonym" in prompt
    assert "observation-only language" in prompt
    assert "diagnosis, tissue, and severity unresolved" in prompt


def test_director_magic_retry_prompt_lists_terms_found_in_rejected_plan(tmp_path):
    rejected = _tagged_director_plan(
        2,
        pressure="Possible trauma requires a faster decision.",
        canon_updates=["Possible trauma is noted in the record."],
        magic_cost_type="time",
        magic_effect_detail="Possible trauma is noted in the record.",
    )
    corrected = _tagged_director_plan(
        2,
        pressure="The support window closes before the family can call.",
        canon_updates=["The porch camera remains unavailable to the family."],
        magic_cost_type="time",
        magic_effect_detail="Mara spends twenty minutes reviewing the frozen feed.",
    )
    database, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=[rejected, corrected, _tagged_director_render(2)],
        two_pass_directing=True,
    )
    runner.forbidden_magic_result_terms = ("trauma",)
    runner._game_state.record_magic_roll(
        {
            "attribute": "Intellect",
            "attribute_score": 3,
            "die_faces": [3, 4],
            "situational_modifier": 0,
            "total": 7,
            "outcome": "costly_success",
            "challenge": _MAGIC_TEST_CHALLENGE,
            "success_criteria": _MAGIC_TEST_CRITERIA,
        }
    )

    asyncio.run(runner._call_two_pass_orchestrator(2))

    correction_call = database.connection.execute(
        "SELECT prompt_path FROM model_calls "
        "WHERE purpose='director_plan_round:2' AND attempt=2"
    ).fetchone()
    correction_prompt = Path(
        tmp_path / "private" / "orchestrator" / correction_call[0]
    ).read_text()
    assert "FORBIDDEN MAGIC RESULT TERMS FOUND IN REJECTED PLAN: trauma" in correction_prompt
    assert "must not appear in the corrected plan" in correction_prompt
    assert "observation-only language" in correction_prompt


def test_two_pass_director_replaces_a_lethal_cost_with_nonlethal_urgency(tmp_path):
    def plan(choice_a):
        return ScriptedStream((
            "<SCENE_OBJECTIVE>Find why the lighthouse remembers the cast before dawn.</SCENE_OBJECTIVE>"
            "<ADJUDICATION>The manual breach exposes the archive and drains cooling.</ADJUDICATION>"
            "<STATE_CHANGE>The archive opens while cooling falls to two percent.</STATE_CHANGE>"
            "<PRESSURE>Only two minutes of cooling remain.</PRESSURE>"
            f"<CHOICE_A>{choice_a}</CHOICE_A>"
            "<CHOICE_B>Seal the archive and preserve habitat capacity.</CHOICE_B>"
            "<NEXT_ACTOR>Mara</NEXT_ACTOR><COMPLETE>false</COMPLETE>"
            "<CLOCK_CHANGE>danger:+1</CLOCK_CHANGE>"
            "<CANON_UPDATE>Cooling is limited to two percent.</CANON_UPDATE>"
        ))
    responses = [
        _tagged_director_plan(1), _tagged_director_render(1),
        _tagged_director_plan(2), _tagged_director_render(2),
        plan("Carry the archive and abandon the vessel to heat death."),
        plan("Carry the archive and permanently lose propulsion."),
        _tagged_director_render(3),
        _tagged_director_plan(4), _tagged_director_render(4),
    ]
    database, runner, _ = _runner(tmp_path, orchestrator_responses=responses, two_pass_directing=True)

    result = asyncio.run(runner.execute())

    assert result.turns == 16
    calls = database.connection.execute(
        "SELECT call_id,correction_of_call_id,acceptance_status,validator_code FROM model_calls "
        "WHERE purpose='director_plan_round:3' ORDER BY attempt"
    ).fetchall()
    assert calls[0]["validator_code"] == "DIRECTOR_SENSITIVE_STAKES"
    assert calls[1]["correction_of_call_id"] == calls[0]["call_id"]
    assert calls[1]["acceptance_status"] == "ACCEPTED"
    assert "permanently lose propulsion" in result.transcript.script_view()
    assert "heat death" not in result.transcript.script_view()


def test_two_pass_render_correction_preserves_plan_and_provenance(tmp_path):
    responses = [
        _tagged_director_plan(1),
        ScriptedStream(("<NARRATION>Mara feels the heat through her suit.</NARRATION>",)),
        ScriptedStream(("<NARRATION>Warm air gathers beneath the lamps.</NARRATION>",)),
    ]
    for n in range(2, 5):
        responses.extend((_tagged_director_plan(n), _tagged_director_render(n)))
    database, runner, _ = _runner(tmp_path, orchestrator_responses=responses, two_pass_directing=True)

    result = asyncio.run(runner.execute())

    assert result.turns == 16
    calls = database.connection.execute(
        "SELECT call_id,correction_of_call_id,acceptance_status,validator_code FROM model_calls "
        "WHERE purpose='orchestrator_round:1' ORDER BY attempt"
    ).fetchall()
    assert len(calls) == 2
    assert calls[0]["validator_code"] == "ACTOR_PUPPETEERING"
    assert calls[0]["acceptance_status"] == "REJECTED"
    assert calls[1]["acceptance_status"] == "ACCEPTED"
    assert calls[1]["correction_of_call_id"] == calls[0]["call_id"]
    script = result.transcript.script_view()
    assert "Mara feels" not in script
    assert "Warm air gathers" in script
    assert "Choice A: Use the numbered key at the east landing." in script
    assert "Choice B: Study the numbered key before the bell." in script
    assert database.connection.execute(
        "SELECT COUNT(*) FROM domain_events WHERE event_type='DirectorPlanAccepted'"
    ).fetchone()[0] == 4


def test_two_pass_render_does_not_misread_cast_name_in_validated_choice(tmp_path):
    responses = [
        _tagged_director_plan(1, choice_b="Have Eli call the wildlife transport team."),
        _tagged_director_render(1),
    ]
    for n in range(2, 5):
        responses.extend((_tagged_director_plan(n), _tagged_director_render(n)))
    database, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=responses,
        two_pass_directing=True,
    )

    result = asyncio.run(runner.execute())

    assert result.turns == 16
    first_round = database.connection.execute(
        "SELECT acceptance_status,validator_code FROM model_calls "
        "WHERE purpose='orchestrator_round:1' ORDER BY attempt"
    ).fetchall()
    assert [tuple(row) for row in first_round] == [("ACCEPTED", None)]


@pytest.mark.parametrize("correction,reason", [
    ("<NARRATION>Mara feels the heat again.</NARRATION>", "orchestrator_director_contract_invalid"),
    ("not a structured response", "director_render_correction_output_invalid"),
])
def test_two_pass_render_correction_is_bounded_and_fail_closed(tmp_path, correction, reason):
    database, runner, _ = _runner(
        tmp_path, two_pass_directing=True,
        orchestrator_responses=[
            _tagged_director_plan(1),
            ScriptedStream(("<NARRATION>Mara feels the heat through her suit.</NARRATION>",)),
            ScriptedStream((correction,)),
        ],
    )
    with pytest.raises(SceneRunError, match=reason):
        asyncio.run(runner.execute())
    assert database.connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0] == 0
    assert database.connection.execute(
        "SELECT COUNT(*) FROM model_calls WHERE purpose='orchestrator_round:1'"
    ).fetchone()[0] == 2


def test_two_pass_final_director_plan_cannot_skip_the_fourth_actor_round(tmp_path):
    responses = []
    for round_number in range(1, 4):
        responses.extend((_tagged_director_plan(round_number), _tagged_director_render(round_number)))
    responses.extend(
        (_tagged_director_plan(4, complete=True), _tagged_director_plan(4, complete=True))
    )
    database, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=responses,
        two_pass_directing=True,
    )

    with pytest.raises(SceneRunError, match="director_plan_contract_invalid"):
        asyncio.run(runner.execute())

    assert database.connection.execute("SELECT turn_count FROM runs").fetchone()[0] == 12
    rejected = database.connection.execute(
        "SELECT validator_code FROM model_calls WHERE purpose = 'director_plan_round:4' "
        "ORDER BY attempt"
    ).fetchall()
    assert [row[0] for row in rejected] == [
        "FINAL_ROUND_PREEMPTS_ACTORS",
        "FINAL_ROUND_PREEMPTS_ACTORS",
    ]


def test_two_pass_director_surgically_corrects_a_forbidden_prior_act_mechanism(tmp_path):
    rejected_plan = ScriptedStream(
        (
            "<SCENE_OBJECTIVE>Find why the lighthouse remembers the cast before dawn.</SCENE_OBJECTIVE>"
            "<ADJUDICATION>The manual patch holds while propulsion loses power.</ADJUDICATION>"
            "<STATE_CHANGE>Archive sensors fail as propulsion falls to ten percent.</STATE_CHANGE>"
            "<PRESSURE>Habitat stability fails within forty-five minutes.</PRESSURE>"
            "<CHOICE_A>Reconnect sensors using scarce coolant.</CHOICE_A>"
            "<CHOICE_B>Seal the observation blister and preserve habitat.</CHOICE_B>"
            "<NEXT_ACTOR>Mara</NEXT_ACTOR><COMPLETE>false</COMPLETE>"
            "<CLOCK_CHANGE>danger:+1</CLOCK_CHANGE><CLOCK_CHANGE>mission:+1</CLOCK_CHANGE>"
            "<CANON_UPDATE>Propulsion is limited to ten percent.</CANON_UPDATE>"
        )
    )
    corrected_plan = ScriptedStream(
        (
            "<SCENE_OBJECTIVE>Find why the lighthouse remembers the cast before dawn.</SCENE_OBJECTIVE>"
            "<ADJUDICATION>The manual patch holds while propulsion loses power.</ADJUDICATION>"
            "<STATE_CHANGE>Archive sensors fail as propulsion falls to ten percent.</STATE_CHANGE>"
            "<PRESSURE>Habitat stability fails within forty-five minutes.</PRESSURE>"
            "<CHOICE_A>Reconnect sensors using scarce coolant.</CHOICE_A>"
            "<CHOICE_B>Spend habitat reserves to preserve the archive.</CHOICE_B>"
            "<NEXT_ACTOR>Mara</NEXT_ACTOR><COMPLETE>false</COMPLETE>"
            "<CLOCK_CHANGE>danger:+1</CLOCK_CHANGE><CLOCK_CHANGE>mission:+1</CLOCK_CHANGE>"
            "<CANON_UPDATE>Propulsion is limited to ten percent.</CANON_UPDATE>"
        )
    )
    responses = [
        _tagged_director_plan(1),
        _tagged_director_render(1),
        rejected_plan,
        corrected_plan,
        _tagged_director_render(2),
        _tagged_director_plan(3),
        _tagged_director_render(3),
        _tagged_director_plan(4),
        _tagged_director_render(4),
    ]
    database, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=responses,
        two_pass_directing=True,
        forbidden_story_terms=("blister",),
    )

    result = asyncio.run(runner.execute())

    assert result.turns == 16
    calls = database.connection.execute(
        "SELECT call_id, correction_of_call_id, acceptance_status, validator_code, prompt_path "
        "FROM model_calls WHERE purpose = 'director_plan_round:2' ORDER BY attempt"
    ).fetchall()
    assert len(calls) == 2
    assert calls[0]["acceptance_status"] == "REJECTED"
    assert calls[0]["validator_code"] == "EPISODE_SPINE_FALLBACK_REUSED"
    assert calls[1]["acceptance_status"] == "ACCEPTED"
    assert calls[1]["correction_of_call_id"] == calls[0]["call_id"]
    correction_prompt = (tmp_path / "private" / "orchestrator" / calls[1]["prompt_path"]).read_text()
    assert "Preserve the scene_objective exactly" in correction_prompt
    assert "blister" in correction_prompt


def test_two_pass_director_restores_safe_fields_after_correction_paraphrase(tmp_path):
    rejected_plan = ScriptedStream(
        (
            "<SCENE_OBJECTIVE>Find why the lighthouse remembers the cast before dawn.</SCENE_OBJECTIVE>"
            "<ADJUDICATION>The archive reaches the machine bay junction.</ADJUDICATION>"
            "<STATE_CHANGE>Archive sensors fail as propulsion falls to ten percent.</STATE_CHANGE>"
            "<PRESSURE>Habitat stability fails within forty-five minutes.</PRESSURE>"
            "<CHOICE_A>Reconnect sensors using scarce coolant.</CHOICE_A>"
            "<CHOICE_B>Seal the observation hatch and preserve habitat.</CHOICE_B>"
            "<NEXT_ACTOR>Mara</NEXT_ACTOR><COMPLETE>false</COMPLETE>"
            "<CLOCK_CHANGE>danger:+1</CLOCK_CHANGE><CLOCK_CHANGE>mission:+1</CLOCK_CHANGE>"
            "<CANON_UPDATE>Propulsion is limited to ten percent.</CANON_UPDATE>"
        )
    )
    corrected_plan = ScriptedStream(
        (
            "<SCENE_OBJECTIVE>Find why the lighthouse remembers the cast before dawn.</SCENE_OBJECTIVE>"
            "<ADJUDICATION>The archive reaches the machine bay interface.</ADJUDICATION>"
            "<STATE_CHANGE>Archive sensors fail as propulsion falls to ten percent.</STATE_CHANGE>"
            "<PRESSURE>Habitat stability fails within forty-five minutes.</PRESSURE>"
            "<CHOICE_A>Reconnect sensors with reserve coolant.</CHOICE_A>"
            "<CHOICE_B>Protect the crew and abandon the archive.</CHOICE_B>"
            "<NEXT_ACTOR>Mara</NEXT_ACTOR><COMPLETE>false</COMPLETE>"
            "<CLOCK_CHANGE>danger:+1</CLOCK_CHANGE><CLOCK_CHANGE>mission:+1</CLOCK_CHANGE>"
            "<CANON_UPDATE>Propulsion is limited to ten percent.</CANON_UPDATE>"
        )
    )
    responses = [
        _tagged_director_plan(1),
        _tagged_director_render(1),
        rejected_plan,
        corrected_plan,
        _tagged_director_render(2),
        _tagged_director_plan(3),
        _tagged_director_render(3),
        _tagged_director_plan(4),
        _tagged_director_render(4),
    ]
    database, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=responses,
        two_pass_directing=True,
        forbidden_story_terms=("junction",),
    )

    result = asyncio.run(runner.execute())

    assert result.turns == 16
    script = result.transcript.script_view()
    assert "Choice A: Reconnect sensors using scarce coolant." in script
    assert "Choice B: Seal the observation hatch and preserve habitat." in script
    call = database.connection.execute(
        "SELECT acceptance_status, validator_code, validator_detail "
        "FROM model_calls WHERE purpose='director_plan_round:2' ORDER BY attempt DESC LIMIT 1"
    ).fetchone()
    assert call["acceptance_status"] == "ACCEPTED"
    assert call["validator_code"] == "DIRECTOR_PLAN_CORRECTION_SCOPE_REPAIRED"
    assert "choice_a, choice_b" in call["validator_detail"]
    event = database.connection.execute(
        "SELECT payload_json FROM domain_events "
        "WHERE event_type='DirectorPlanCorrectionScopeRepaired'"
    ).fetchone()
    assert event is not None
    assert '"restored_fields": ["choice_a", "choice_b"]' in event[0]


def test_scene_runner_resumes_after_failed_call_without_duplicate_turns(tmp_path):
    # Keep the first attempt intentionally small: Mara succeeds, Nox fails,
    # and the replacement runner supplies all remaining attempts.
    first_clients = [
        ScriptedFakeClient([_tagged_actor("Mara first")]),
        ScriptedFakeClient([ScriptedStream(("partial",), error=TimeoutError())]),
        ScriptedFakeClient(),
        ScriptedFakeClient(),
    ]
    database, first_runner, clock = _runner(
        tmp_path,
        orchestrator_responses=[_tagged_orchestrator(1)],
        actor_clients=first_clients,
    )

    with pytest.raises(SceneRunError, match="actor_call_char-2_failed"):
        asyncio.run(first_runner.execute())
    assert database.connection.execute("SELECT status FROM runs").fetchone()[0] == "INTERRUPTED"
    assert database.connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0] == 2

    replacement_clients = [
        ScriptedFakeClient([_tagged_actor("Mara second"), _tagged_actor("Mara third"), _tagged_actor("Mara fourth")]),
        ScriptedFakeClient([_tagged_actor("Nox retry"), _tagged_actor("Nox second"), _tagged_actor("Nox third"), _tagged_actor("Nox fourth")]),
        ScriptedFakeClient([_tagged_actor("Iris first"), _tagged_actor("Iris second"), _tagged_actor("Iris third"), _tagged_actor("Iris fourth")]),
        ScriptedFakeClient([_tagged_actor("Sol first"), _tagged_actor("Sol second"), _tagged_actor("Sol third"), _tagged_actor("Sol fourth")]),
    ]
    # Reuse the durable database and replace only the model sessions.
    resumed_runner = SceneRunner(
        run_id="S01-run-01",
        opening=_OPENING,
        private_plan=_PLAN,
        actors=tuple(
            SceneActor(
                character_id=actor.character_id,
                name=actor.name,
                role_sheet=actor.role_sheet,
                executor=_executor(
                    database,
                    replacement_clients[index],
                    tmp_path / "private" / actor.name.lower() / "replacement",
                    clock,
                ),
            )
            for index, actor in enumerate(first_runner.actors)
        ),
        orchestrator=_executor(
            database,
            ScriptedFakeClient([_tagged_orchestrator(2), _tagged_orchestrator(3), _tagged_orchestrator(4)]),
            tmp_path / "private" / "orchestrator" / "replacement",
            clock,
        ),
    )

    result = asyncio.run(resumed_runner.execute())

    assert result.turns == 16
    assert database.connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0] == 20
    attempts = database.connection.execute(
        "SELECT attempt, status FROM model_calls WHERE purpose = ? ORDER BY attempt",
        ("actor_turn:char-2:round:1",),
    ).fetchall()
    assert [(row["attempt"], row["status"]) for row in attempts] == [(1, "FAILED"), (2, "COMPLETED")]


def test_scene_runner_stops_on_orchestrator_completion(tmp_path):
    database, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=[_tagged_orchestrator(1, complete=True)],
    )

    result = asyncio.run(runner.execute())

    assert result.reason == "natural_completion"
    assert result.turns == 0
    assert database.connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0] == 1
    assert database.connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0] == 1


def test_scene_runner_rejects_director_text_that_authors_a_cast_member(tmp_path):
    database, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=[
            ScriptedStream(
                (
                    "<NARRATION>Mara grips the rail and says, 'We should run.'</NARRATION>"
                    "<COMPLETE>false</COMPLETE>",
                )
            )
        ],
    )

    with pytest.raises(SceneRunError, match="orchestrator_actor_puppeteering"):
        asyncio.run(runner.execute())
    assert database.connection.execute("SELECT status FROM runs").fetchone()[0] == "INTERRUPTED"
    assert database.connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0] == 0


def test_scene_runner_interrupts_and_preserves_wellness_signal(tmp_path):
    actors = [
        ScriptedFakeClient(
            [_tagged_actor("Mara says stop", wellness="Please pause the scene; this is too much.")]
        ),
        ScriptedFakeClient(),
        ScriptedFakeClient(),
        ScriptedFakeClient(),
    ]
    database, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=[_tagged_orchestrator(1)],
        actor_clients=actors,
    )

    result = asyncio.run(runner.execute())

    assert result.reason == "wellness_redirect"
    assert result.turns == 0
    assert database.connection.execute("SELECT status FROM runs").fetchone()[0] == "INTERRUPTED"
    event = database.connection.execute(
        "SELECT event_type, payload_json FROM domain_events WHERE event_type = 'WellnessSignalObserved'"
    ).fetchone()
    assert event["event_type"] == "WellnessSignalObserved"
    assert "too much" not in event["payload_json"]
    model_output = database.connection.execute(
        "SELECT output_path FROM model_calls WHERE purpose = 'actor_turn:char-1:round:1'"
    ).fetchone()[0]
    assert "Please pause the scene" in open(model_output, encoding="utf-8").read()
    assert database.connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0] == 1


def test_scene_runner_requests_one_correction_and_keeps_original_private(tmp_path):
    actors = [
            ScriptedFakeClient(
                [
                    _tagged_actor("I wait beside the door."),
                    _tagged_actor("Nox screams and runs for the hatch."),
                    _tagged_actor("I confront Nox without touching them."),
                    _tagged_actor("I watch the door."),
                    _tagged_actor("I listen to the hinges."),
                ]
            ),
        ScriptedFakeClient([_tagged_actor(f"Nox turn {index}") for index in range(1, 5)]),
        ScriptedFakeClient([_tagged_actor(f"Iris turn {index}") for index in range(1, 5)]),
        ScriptedFakeClient([_tagged_actor(f"Sol turn {index}") for index in range(1, 5)]),
    ]
    database, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=[_tagged_orchestrator(n) for n in range(1, 5)],
        actor_clients=actors,
    )

    result = asyncio.run(runner.execute())

    assert result.turns == 16
    assert "CONTENT REVIEW — NOT CANON" in result.transcript.script_view()
    assert "I confront Nox without touching them." in result.transcript.script_view()
    dispositions = database.connection.execute(
        "SELECT event_type, payload_json FROM domain_events "
        "WHERE event_type IN ('TurnDisposition', 'CorrectionRequested') "
        "ORDER BY event_type"
    ).fetchall()
    assert len(dispositions) == 2
    assert any(row["event_type"] == "CorrectionRequested" for row in dispositions)
    assert any("OTHER_CHARACTER_AUTONOMY" in row["payload_json"] for row in dispositions)
    assert database.connection.execute(
        "SELECT COUNT(*) FROM model_calls WHERE purpose LIKE 'actor_correction:%'"
    ).fetchone()[0] == 1
    correction_input = database.connection.execute(
        "SELECT prompt_path FROM model_calls WHERE purpose LIKE 'actor_correction:%'"
    ).fetchone()[0]
    prompt = open(correction_input, encoding="utf-8").read()
    assert "REJECTED TURN: Nox screams and runs for the hatch." in prompt
    assert "Correct it surgically" in prompt
    assert "Preserve the same choice" in prompt
    assert "Do not invent a replacement plan" in prompt


def test_scene_runner_keeps_second_invalid_turn_noncanon_and_inserts_neutral_pause(tmp_path):
    actors = [
        ScriptedFakeClient(
            [
                _tagged_actor("Nox screams and runs for the hatch."),
                _tagged_actor("Nox kicks the hatch and flees."),
                _tagged_actor("I keep my distance."),
                _tagged_actor("I study the door."),
                _tagged_actor("I wait for the lights."),
            ]
        ),
        ScriptedFakeClient([_tagged_actor(f"Nox turn {index}") for index in range(1, 5)]),
        ScriptedFakeClient([_tagged_actor(f"Iris turn {index}") for index in range(1, 5)]),
        ScriptedFakeClient([_tagged_actor(f"Sol turn {index}") for index in range(1, 5)]),
    ]
    database, runner, _ = _runner(
        tmp_path,
        orchestrator_responses=[_tagged_orchestrator(n) for n in range(1, 5)],
        actor_clients=actors,
    )

    result = asyncio.run(runner.execute())

    assert result.turns == 15
    assert "The scene pauses" in result.transcript.script_view()
    assert database.connection.execute(
        "SELECT COUNT(*) FROM turns WHERE disposition = 'NEUTRAL_INTERRUPTION'"
    ).fetchone()[0] == 1
    assert database.connection.execute(
        "SELECT COUNT(*) FROM domain_events WHERE event_type = 'TurnDisposition'"
    ).fetchone()[0] == 2
    resumed = asyncio.run(runner.execute())
    assert resumed.turns == 15
    assert len(runner._neutral_interruptions) == 1
    assert len(runner._resolved) == 16
