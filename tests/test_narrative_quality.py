"""Offline contract checks. These scripted fixtures do not score model prose."""

import asyncio
import json
from pathlib import Path

import pytest

from improv_troupe.application.scene_runner import DirectorGameState, _compile_director_beat
from improv_troupe.domain.magic import MagicAdjudication, MagicCostType, MagicOutcome
from improv_troupe.llm import ScriptedFakeClient, ScriptedStream
from improv_troupe.llm.context import build_director_render_messages, build_orchestrator_messages
from improv_troupe.llm.safety import repeats_shared_phrase
from improv_troupe.llm.structured import (
    DirectorPlanEnvelope,
    StructuredOutputError,
    parse_director_render_output,
)
from tests.test_scene_runner import _OPENING, _PLAN, _runner, _tagged_director_plan, _tagged_orchestrator


def _plan():
    return DirectorPlanEnvelope(
        scene_objective="Will anyone answer the keeper's knock?",
        adjudication="PRIVATE: the keeper recognizes the stolen coat.",
        state_change="Three knocks interrupt the argument at the kitchen door.",
        pressure="The caller can hear every word through the thin door.",
        choice_a="Answer the door with the coat still on.",
        choice_b="Hide the coat before answering.",
        next_actor="Mara",
        clock_changes=[{"clock": "danger", "change": 1}],
        canon_updates=["Someone has knocked three times at the kitchen door."],
    )


def _shared_state(messages):
    content = next(message["content"] for message in messages
                   if message["content"].startswith("SHARED PLAY STATE"))
    return json.loads(content.split("\n", 1)[1])


def test_prose_renderer_sees_established_material_without_private_rationale_or_offers():
    plan = _plan().model_dump(mode="json")
    plan["future_private_field"] = "SECRET FUTURE TWIST"
    messages = build_director_render_messages(
        plan=plan, continuity_anchors=("kitchen",), spent_director_terms=("door",),
        established_scene=("[The kitchen door is closed.]",),
    )
    payload = json.loads(messages[-1]["content"])
    assert payload["established_beat"] == {
        "state_change": plan["state_change"], "pressure": plan["pressure"],
    }
    assert payload["established_scene"] == ["[The kitchen door is closed.]"]
    for key in ("scene_objective", "adjudication", "choice_a", "choice_b",
                "clock_changes", "canon_updates", "future_private_field"):
        assert str(plan[key]) not in messages[-1]["content"]


@pytest.mark.parametrize("raw", [
    '{"narration": ""}', '<NARRATION></NARRATION>', '<NARRATION>   </NARRATION>',
])
def test_empty_optional_detail_is_valid_but_not_an_empty_scene(raw):
    rendered = parse_director_render_output(raw)
    plan = _plan()
    beat = _compile_director_beat(rendered.narration, plan)
    assert beat == plan.state_change + "\n" + plan.pressure
    assert "PRIVATE" not in beat
    assert plan.choice_a not in beat
    assert plan.choice_b not in beat


@pytest.mark.parametrize("raw", ["", "{}", '{"narration": null}',
                                  '{"narration": "<CHOICE_A>Hide.</CHOICE_A>"}'])
def test_missing_or_markup_render_is_not_the_optional_empty_detail(raw):
    with pytest.raises(StructuredOutputError):
        parse_director_render_output(raw)


def test_repetition_guard_distinguishes_reused_language_from_continuity():
    previous = ("Morning light spills across the weathered boards; dust gathers at the door.",)
    assert repeats_shared_phrase("Morning LIGHT spills across the weathered boards.", previous)
    assert not repeats_shared_phrase("The door has swollen against the boards overnight.", previous)
    assert not repeats_shared_phrase("A knock.", previous)


def test_long_optional_detail_gets_a_bounded_correction_instead_of_padding_the_scene(tmp_path):
    long_detail = " ".join(["Detail"] * 36)
    database, runner, _ = _runner(tmp_path, two_pass_directing=True, orchestrator_responses=[
        _tagged_director_plan(1),
        ScriptedStream((f"<NARRATION>{long_detail}</NARRATION>",)),
        ScriptedStream(('<NARRATION></NARRATION>',)),
    ])
    runner.max_rounds = 1
    runner.max_actor_turns = 4
    result = asyncio.run(runner.execute())
    assert result.turns == 4
    calls = database.connection.execute(
        "SELECT call_id,correction_of_call_id,validator_code,acceptance_status "
        "FROM model_calls WHERE purpose='orchestrator_round:1' ORDER BY attempt"
    ).fetchall()
    assert len(calls) == 2
    assert calls[0]["validator_code"] == "DIRECTOR_LEAD_IN_TOO_VERBOSE"
    assert calls[1]["correction_of_call_id"] == calls[0]["call_id"]
    assert calls[1]["acceptance_status"] == "ACCEPTED"
    assert long_detail not in result.transcript.script_view()


def test_shared_choices_reach_every_actor_and_survive_replay_without_hidden_state(tmp_path):
    database, runner, _ = _runner(tmp_path, two_pass_directing=True, orchestrator_responses=[
        _tagged_director_plan(1), ScriptedStream(('<NARRATION></NARRATION>',)),
    ])
    runner.max_rounds = 1
    runner.max_actor_turns = 4
    result = asyncio.run(runner.execute())
    expected = ["Use the numbered key at the east landing.", "Study the numbered key before the bell."]
    calls = database.connection.execute(
        "SELECT prompt_path FROM model_calls WHERE purpose LIKE 'actor_turn:%'"
    ).fetchall()
    assert len(calls) == 4
    for call in calls:
        state = _shared_state(json.loads(Path(call["prompt_path"]).read_text()))
        assert state == {"offered_choices": expected, "pending_challenge": None,
                         "latest_magic_result": None}
    script = result.transcript.script_view()
    assert "At lighthouse:" not in script
    assert "Pressure:" not in script
    assert "Choice A:" not in script
    assert "Use the numbered key" not in script
    runner._hydrate()
    assert runner.transcript.script_view() == script
    assert _shared_state(runner.actor_messages(runner.actors[0], 1))["offered_choices"] == expected
    assert runner._game_state.clocks["mystery"] == 1


def test_single_pass_beat_clears_old_options_and_historical_prose_is_not_rewritten(tmp_path):
    _, runner, _ = _runner(tmp_path, two_pass_directing=True, orchestrator_responses=[
        _tagged_director_plan(1), ScriptedStream(('<NARRATION></NARRATION>',)),
        _tagged_orchestrator(2),
    ])
    runner.max_rounds = 2
    runner.max_actor_turns = 8
    snapshots = []

    def switch_after_round_one(current, round_number):
        if round_number == 1:
            assert current._game_state.offered_choices
            snapshots.append(current.transcript.script_view())
            current.two_pass_directing = False
            current.enforce_narrative_acceptance = False

    runner.round_observer = switch_after_round_one
    second = asyncio.run(runner.execute()).transcript.script_view()
    assert second.startswith(snapshots[0])
    assert runner._game_state.offered_choices == ()
    runner._hydrate()
    assert runner.transcript.script_view() == second
    assert runner._game_state.offered_choices == ()


def test_shared_magic_state_distinguishes_unanswered_question_and_setback():
    state = DirectorGameState(scene_objective="PRIVATE OBJECTIVE")
    state.clocks["danger"] = 3
    state.apply_magic_fields(
        magic_challenge="Can Mara read the caller's note?",
        magic_success_criteria="The note identifies its sender.", next_actor="Mara", magic_modifier=0,
    )
    public = state.actor_play_state()
    assert public["pending_challenge"]["actor"] == "Mara"
    assert public["latest_magic_result"] is None
    assert "PRIVATE" not in json.dumps(public)
    assert "clocks" not in public
    state.record_magic_roll({
        "attribute": "Intellect", "attribute_score": 3, "die_faces": [2, 3],
        "situational_modifier": 0, "total": 5, "outcome": "setback",
        "success_criteria": "The note identifies its sender.",
    })
    public = state.actor_play_state()
    assert public["pending_challenge"] is None
    assert public["latest_magic_result"]["goal_status"] == "not_achieved"
    assert public["latest_magic_result"]["goal_answer"].startswith("Success criterion remains unestablished:")


@pytest.mark.parametrize("outcome", list(MagicOutcome))
def test_prose_composition_retains_exact_runtime_result_and_consequence(outcome):
    plan = _plan().model_copy(update={
        "magic_cost_type": MagicCostType.TIME if outcome is MagicOutcome.COSTLY_SUCCESS else None,
        "magic_effect_detail": "The caller knocks once more.",
    })
    adjudication = MagicAdjudication.from_outcome(
        outcome=outcome, success_criteria="The note identifies its sender.",
    )
    beat = _compile_director_beat("", plan, magic_adjudication=adjudication)
    assert adjudication.goal_answer in beat
    assert plan.magic_effect_detail in beat
    assert plan.state_change in beat
    assert plan.pressure in beat
    assert plan.choice_a not in beat
    assert "PRIVATE" not in beat


def test_prompt_probe_uses_current_composition_without_claiming_prose_quality(tmp_path):
    from scripts.probe_director_prompt import _probe_two_pass

    class StructuredFixture(ScriptedFakeClient):
        async def stream_structured_chat(self, model, messages, **params):
            async for token in self.stream_chat(model, messages, **params):
                yield token

    plan = _plan()
    client = StructuredFixture([
        ScriptedStream((plan.model_dump_json(),)),
        ScriptedStream(('{"narration": ""}',)),
    ])
    report = tmp_path / "probe.txt"
    code = asyncio.run(_probe_two_pass(
        client=client, model="scripted-fixture", params={}, opening=_OPENING,
        one_pass_messages=build_orchestrator_messages(
            opening=_OPENING, private_plan=_PLAN, accepted_canon=(), scene_transcript=(),
            spent_director_terms=("kitchen", "door", "knocks"),
        ), report=report,
    ))
    assert code == 0
    assert len(client.calls) == 2
    text = report.read_text()
    compiled = text.split("COMPILED BEAT\n", 1)[1].split("\nACCEPTANCE:", 1)[0]
    assert compiled == _compile_director_beat("", plan)
    assert "QUALITY: HUMAN_REVIEW_REQUIRED" in text
