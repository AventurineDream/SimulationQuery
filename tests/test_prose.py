"""Tests for the shared prose-craft guidance and deterministic lint."""

from __future__ import annotations

from improv_troupe.domain import OpeningSnapshot, HiddenSeasonPlan, RoleSheet
from improv_troupe.llm.context import (
    ActorContext,
    build_actor_messages,
    build_director_render_messages,
    build_diary_messages,
    build_orchestrator_messages,
)
from improv_troupe.llm.prose import (
    ACTOR_PROSE_GUIDE,
    CLICHE_PHRASES,
    DIARY_VOICE_GUIDE,
    DIRECTOR_PROSE_GUIDE,
    lint_prose,
)
from improv_troupe.engine.prompts import build_system_prompt
from improv_troupe.domain import Actor, Constraints, ProductionPlan, Scene


def _joined(messages):
    return "\n".join(message["content"] for message in messages)


def test_lint_flags_stock_imagery_and_meta_leaks():
    issues = lint_prose(
        "The air was thick as an AI I cannot say. Her heart pounded; time stood still."
    )
    codes = {issue.code for issue in issues}
    assert "STOCK_IMAGERY" in codes
    assert "META_LEAK" in codes


def test_lint_flags_monotonous_openers_only_at_three():
    clean = lint_prose("I checked the latch. I checked it again. Mara watched from the steps.")
    assert not [i for i in clean if i.code == "MONOTONOUS_OPENERS"]
    flagged = lint_prose("I checked the latch. I checked the sill. I checked the yard. Mara waited.")
    assert any(i.code == "MONOTONOUS_OPENERS" for i in flagged)


def test_lint_passes_clean_concrete_prose():
    text = (
        "Mara sets the mug down before it spills. The porch light buzzes; a moth "
        "keeps hitting the shade. 'You first,' Rory says, and means it as a dare."
    )
    assert lint_prose(text) == []


def test_every_cliche_phrase_is_caught_case_insensitively():
    for phrase in CLICHE_PHRASES:
        issues = lint_prose(f"It was {phrase.upper()} indeed.")
        assert any(i.code == "STOCK_IMAGERY" for i in issues), phrase


def test_actor_prompt_carries_craft_guide_without_crossing_boundaries():
    role = RoleSheet(character_id="mara", secrets=["mara-secret"])
    for profile in ("general", "thrasher"):
        messages = build_actor_messages(
            ActorContext(
                actor_name="MARA",
                role_sheet=role,
                scene_transcript=("MARA: I listen.",),
                prompt_profile=profile,
            )
        )
        text = _joined(messages)
        assert "write like a person in the room" in text
        assert "other-secret" not in text


def test_orchestrator_and_render_prompts_carry_director_craft():
    opening = OpeningSnapshot(set="Station", setting="Orbit", cast=["MARA"])
    plan = HiddenSeasonPlan(hidden_mysteries=["private answer"])
    orchestrator = build_orchestrator_messages(
        opening=opening,
        private_plan=plan,
        accepted_canon=(),
        scene_transcript=("MARA: I listen.",),
        round_number=1,
        max_rounds=4,
    )
    assert "concrete and specific beats adjective-piled mood" in _joined(orchestrator)

    render = build_director_render_messages(
        plan={"state_change": "the vent fails"},
        continuity_anchors=("vent",),
        spent_director_terms=(),
    )
    assert "concrete and specific beats adjective-piled mood" in _joined(render)


def test_diary_prompt_carries_voice_guide_after_fidelity_rules():
    messages = build_diary_messages(
        actor_name="MARA",
        role_sheet=RoleSheet(character_id="mara"),
        known_memory=("I saw the hatch.",),
        accepted_scene=("The hatch opened.",),
    )
    text = _joined(messages)
    assert "one specific person on one specific day" in text
    assert "trace each sentence before returning the diary" in text


def test_standalone_scene_prompt_carries_scene_craft_rules():
    plan = ProductionPlan(
        title="t",
        scene=Scene(setting="s", premise="p", opening_beat="A door slams."),
        constraints=Constraints(turn_length="1-4 sentences"),
        cast=[Actor(name="MARA", character_brief="b")],
    )
    prompt = build_system_prompt(plan, plan.cast[0])
    assert "Concrete, specific detail over abstract mood words" in prompt
    assert "no tidy wrap-ups" in prompt


def test_guides_are_non_empty_strings():
    for guide in (ACTOR_PROSE_GUIDE, DIRECTOR_PROSE_GUIDE, DIARY_VOICE_GUIDE):
        assert isinstance(guide, str) and len(guide) > 100


def test_actor_guide_forbids_restating_narration():
    assert "Never restate" in ACTOR_PROSE_GUIDE
    assert "narration" in ACTOR_PROSE_GUIDE


def test_lint_flags_echo_of_reference_narration():
    narration = (
        "Sunlight slants across the worn wooden porch steps, catching dust "
        "motes - two parallel grooves deepen near the edge where shadow pools."
    )
    turn = (
        "I tell the dispatcher the cheetah left two parallel grooves deeper "
        "than before and keep watching the yard."
    )
    codes = [issue.code for issue in lint_prose(turn, reference=narration)]
    assert "ECHO_PHRASE" in codes


def test_lint_reports_echo_as_single_merged_run():
    adjudication = (
        "A new set of faint scuff marks appears in the dirt near the porch "
        "edge, partially obscured by shadow and debris."
    )
    turn = (
        "I explain that the cheetah left fresh scuff marks in the dirt near "
        "the porch edge and request help faster."
    )
    issues = [i for i in lint_prose(turn, reference=adjudication) if i.code == "ECHO_PHRASE"]
    assert len(issues) == 1
    assert "porch edge" in issues[0].detail


def test_lint_without_reference_never_echoes():
    turn = "I press the red button and describe the two parallel grooves again."
    assert all(issue.code != "ECHO_PHRASE" for issue in lint_prose(turn))


def test_lint_ignores_distinct_prose_against_reference():
    narration = "Sunlight slants across the worn wooden porch steps."
    turn = "I circle the fence line, counting fresh tracks in the wet grass."
    assert all(issue.code != "ECHO_PHRASE" for issue in lint_prose(turn, reference=narration))
