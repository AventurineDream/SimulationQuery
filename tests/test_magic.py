import json

import pytest
from pydantic import ValidationError

from improv_troupe.domain.magic import (
    MagicCostType,
    MagicGoalStatus,
    MagicAttribute,
    MagicOutcome,
    MagicScores,
    adjudicate_magic_roll,
    resolve_magic_roll,
)
from improv_troupe.llm.structured import (
    ActorTurnEnvelope,
    DirectorPlanEnvelope,
    StructuredOutputError,
    parse_actor_output,
    parse_director_plan_output,
)


@pytest.mark.parametrize(
    ("faces", "score", "modifier", "total", "outcome"),
    [
        ((5, 5), 3, 0, 10, MagicOutcome.CLEAN_SUCCESS),
        ((3, 4), 3, 0, 7, MagicOutcome.COSTLY_SUCCESS),
        ((2, 3), 3, 0, 5, MagicOutcome.SETBACK),
        ((6, 6), 5, 2, 16, MagicOutcome.CLEAN_SUCCESS),
        ((1, 1), 1, -2, -2, MagicOutcome.SETBACK),
    ],
)
def test_magic_roll_applies_the_formula_and_outcome_thresholds(
    faces, score, modifier, total, outcome
):
    result = resolve_magic_roll(
        attribute=MagicAttribute.GUSTO,
        attribute_score=score,
        die_faces=faces,
        situational_modifier=modifier,
    )

    assert result.total == total
    assert result.outcome is outcome


def test_magic_scores_default_to_neutral_and_reject_out_of_scale_values():
    assert MagicScores().score_for(MagicAttribute.COOL) == 3
    with pytest.raises(ValidationError):
        MagicScores(gusto=6)


def test_magic_roll_rejects_invalid_faces_and_modifiers():
    with pytest.raises(ValueError, match="two six-sided"):
        resolve_magic_roll(
            attribute=MagicAttribute.MIGHT,
            attribute_score=3,
            die_faces=(0, 7),
        )


@pytest.mark.parametrize(
    ("faces", "expected_outcome", "expected_status", "expected_answer"),
    [
        ((5, 5), MagicOutcome.CLEAN_SUCCESS, MagicGoalStatus.ACHIEVED, "The paw lands softly."),
        ((3, 4), MagicOutcome.COSTLY_SUCCESS, MagicGoalStatus.ACHIEVED, "The paw lands softly."),
        (
            (2, 3),
            MagicOutcome.SETBACK,
            MagicGoalStatus.NOT_ACHIEVED,
            "Success criterion remains unestablished: The paw lands softly.",
        ),
    ],
)
def test_runtime_adjudication_derives_status_and_answer_from_the_roll(
    faces, expected_outcome, expected_status, expected_answer
):
    result = resolve_magic_roll(
        attribute=MagicAttribute.INTELLECT,
        attribute_score=3,
        die_faces=faces,
    )

    adjudication = adjudicate_magic_roll(
        result,
        success_criteria="The paw lands softly.",
    )

    assert adjudication.outcome is expected_outcome
    assert adjudication.goal_status is expected_status
    assert adjudication.goal_answer == expected_answer


def test_runtime_adjudication_requires_a_precommitted_criterion():
    result = resolve_magic_roll(
        attribute=MagicAttribute.INTELLECT,
        attribute_score=3,
        die_faces=(5, 5),
    )

    with pytest.raises(ValueError, match="precommitted success criteria"):
        adjudicate_magic_roll(result, success_criteria=" ")
    with pytest.raises(ValueError, match="between -2 and 2"):
        resolve_magic_roll(
            attribute=MagicAttribute.MIGHT,
            attribute_score=3,
            die_faces=(2, 4),
            situational_modifier=3,
        )


def test_actor_can_select_one_magic_attribute_in_json_or_tagged_output():
    native = ActorTurnEnvelope.model_validate(
        {
            "kind": "actor_turn",
            "text": "I read the tracks from the path.",
            "magic_stat": "Intellect",
            "magic_method": "I compare the track spacing from the path.",
        }
    )
    tagged = parse_actor_output(
        "<ACTOR_TEXT>I read the tracks from the path.</ACTOR_TEXT>"
        "<MAGIC_STAT>intellect</MAGIC_STAT>"
        "<MAGIC_METHOD>I compare the track spacing from the path.</MAGIC_METHOD>"
    )

    assert native == tagged
    assert tagged.magic_stat is MagicAttribute.INTELLECT
    assert tagged.magic_method == "I compare the track spacing from the path."
    assert parse_actor_output("<ACTOR_TEXT>I wait and listen.</ACTOR_TEXT>").magic_stat is None


def test_actor_magic_attempt_requires_a_separate_method_field():
    with pytest.raises(StructuredOutputError):
        parse_actor_output(
            '{"kind":"actor_turn","text":"I compare the tracks.","magic_stat":"Intellect"}'
        )
    with pytest.raises(StructuredOutputError):
        parse_actor_output(
            '{"kind":"actor_turn","text":"I compare the tracks.",'
            '"magic_method":"I compare the tracks."}'
        )


@pytest.mark.parametrize(
    ("text", "expected_text"),
    [
        (
            "I observe the tracks. <MAGIC_STAT>Intellect</MAGIC_STAT>"
            "<MAGIC_METHOD>I compare the track spacing.</MAGIC_METHOD>",
            "I observe the tracks.",
        ),
        (
            "<MAGIC_STAT>Intellect</MAGIC_STAT>"
            "<MAGIC_METHOD>I compare the track spacing.</MAGIC_METHOD> I observe the tracks.",
            "I observe the tracks.",
        ),
    ],
)
def test_actor_parser_moves_a_boundary_magic_tag_from_native_json_text(text, expected_text):
    parsed = parse_actor_output(
        '{"kind":"actor_turn","text":' + json.dumps(text) + '}'
    )

    assert parsed.text == expected_text
    assert parsed.magic_stat is MagicAttribute.INTELLECT
    assert parsed.magic_method == "I compare the track spacing."


def test_actor_parser_does_not_normalize_an_unknown_trailing_magic_tag():
    with pytest.raises(StructuredOutputError):
        parse_actor_output(
            '{"kind":"actor_turn","text":"I observe the tracks. '
            '<MAGIC_STAT>Luck</MAGIC_STAT>"}'
        )


def test_actor_cannot_select_an_unknown_magic_attribute():
    with pytest.raises(StructuredOutputError):
        parse_actor_output(
            "<ACTOR_TEXT>I read the tracks.</ACTOR_TEXT><MAGIC_STAT>luck</MAGIC_STAT>"
        )


def test_director_plan_parses_challenge_and_ignores_legacy_result_acknowledgement():
    parsed = parse_director_plan_output(
        "<SCENE_OBJECTIVE>Why did the cheetah arrive?</SCENE_OBJECTIVE>"
        "<ADJUDICATION>The porch view leaves one uncertain detail.</ADJUDICATION>"
        "<STATE_CHANGE>A fresh track is visible beyond the garden.</STATE_CHANGE>"
        "<PRESSURE>The rain will soften it before noon.</PRESSURE>"
        "<CHOICE_A>Check the track from the doorway.</CHOICE_A>"
        "<CHOICE_B>Call the wildlife team first.</CHOICE_B>"
        "<NEXT_ACTOR>Mara</NEXT_ACTOR><CLOCK_CHANGE>mystery:+1</CLOCK_CHANGE>"
        "<CANON_UPDATE>A track leads toward the wildlife corridor.</CANON_UPDATE>"
        "<MAGIC_CHALLENGE>Can Mara read the track without approaching?</MAGIC_CHALLENGE>"
        "<MAGIC_SUCCESS_CRITERIA>The family identifies the track's direction from the porch.</MAGIC_SUCCESS_CRITERIA>"
        "<MAGIC_MODIFIER>-1</MAGIC_MODIFIER>"
        "<MAGIC_RESULT_ACK>none</MAGIC_RESULT_ACK>"
    )

    assert parsed.magic_challenge == "Can Mara read the track without approaching?"
    assert parsed.magic_success_criteria == "The family identifies the track's direction from the porch."
    assert parsed.magic_modifier == -1
    assert "magic_result_ack" not in parsed.model_dump()


def test_director_plan_parses_only_director_supplied_magic_consequence():
    parsed = parse_director_plan_output(
        "<SCENE_OBJECTIVE>What does the cheetah's posture reveal?</SCENE_OBJECTIVE>"
        "<ADJUDICATION>The recorded result changes what the family knows.</ADJUDICATION>"
        "<STATE_CHANGE>The family has a clearer view of the raised hind paw.</STATE_CHANGE>"
        "<PRESSURE>Wildlife support is still on its way.</PRESSURE>"
        "<CHOICE_A>Keep observing from the doorway.</CHOICE_A>"
        "<CHOICE_B>Review the porch camera footage.</CHOICE_B>"
        "<NEXT_ACTOR>Mara</NEXT_ACTOR><CLOCK_CHANGE>mystery:+1</CLOCK_CHANGE>"
        "<CANON_UPDATE>The family has not approached the cheetah.</CANON_UPDATE>"
        "<MAGIC_RESULT_ACK>costly_success</MAGIC_RESULT_ACK>"
        "<MAGIC_GOAL_STATUS>achieved</MAGIC_GOAL_STATUS>"
        "<MAGIC_GOAL_ANSWER>The family confirms the breathing rhythm from the porch.</MAGIC_GOAL_ANSWER>"
        "<MAGIC_COST_TYPE>time</MAGIC_COST_TYPE>"
        "<MAGIC_EFFECT_DETAIL>Wildlife support arrives twenty minutes later.</MAGIC_EFFECT_DETAIL>"
    )

    assert parsed.magic_cost_type is MagicCostType.TIME
    assert parsed.magic_effect_detail == "Wildlife support arrives twenty minutes later."
    assert "magic_result_ack" not in parsed.model_dump()
    assert "magic_goal_status" not in parsed.model_dump()
    assert "magic_goal_answer" not in parsed.model_dump()


def test_director_plan_schema_exposes_only_consequence_inputs():
    schema = DirectorPlanEnvelope.model_json_schema()
    properties = set(schema["properties"])

    assert {"magic_cost_type", "magic_effect_detail"}.issubset(properties)
    assert {
        "magic_result_ack",
        "magic_goal_status",
        "magic_goal_answer",
    }.isdisjoint(properties)


def test_director_plan_requires_challenge_for_modifier():
    with pytest.raises(ValidationError, match="requires a declared challenge"):
        DirectorPlanEnvelope(
            scene_objective="Why did the cheetah arrive?",
            adjudication="The porch view leaves one uncertain detail.",
            state_change="A fresh track is visible beyond the garden.",
            pressure="The rain will soften it before noon.",
            choice_a="Check the track from the doorway.",
            choice_b="Call the wildlife team first.",
            next_actor="Mara",
            clock_changes=[{"clock": "mystery", "change": 1}],
            canon_updates=["A track leads toward the wildlife corridor."],
            magic_modifier=1,
        )
