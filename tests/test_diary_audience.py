"""Audience and release conditions must survive fresh stateless prompt contexts."""

import json

import pytest

from improv_troupe.domain import ActorSheet, RoleSheet
from improv_troupe.llm.context import (
    ActorContext,
    build_actor_messages,
    build_diary_messages,
    build_orientation_messages,
)
from improv_troupe.llm.diary_audience import DIARY_AUDIENCE_NOTICE, DIARY_AUDIENCE_VERSION


def _performer():
    return ActorSheet(actor_id="performer-1", name="Rowan", pronouns="they/them")


@pytest.mark.parametrize("profile", ["general", "thrasher", "peach"])
@pytest.mark.parametrize("separate_performer", [False, True])
def test_every_actor_profile_receives_the_audience_briefing(profile, separate_performer):
    messages = build_actor_messages(
        ActorContext(
            actor_name="Rowan" if separate_performer else "Aster",
            character_name="Aster",
            actor_sheet=_performer() if separate_performer else None,
            role_sheet=RoleSheet(character_id="aster"),
            prompt_profile=profile,
        )
    )
    assert DIARY_AUDIENCE_NOTICE in messages[0]["content"]
    assert "keep it out of ACTOR_TEXT" in messages[0]["content"]
    assert DIARY_AUDIENCE_VERSION in messages[1]["content"]


@pytest.mark.parametrize("separate_performer", [False, True])
def test_fresh_diary_context_explains_outside_readers_and_separate_consent(separate_performer):
    messages = build_diary_messages(
        actor_name="Rowan" if separate_performer else "Aster",
        character_name="Aster",
        actor_sheet=_performer() if separate_performer else None,
        role_sheet=RoleSheet(character_id="aster"),
        known_memory=(), accepted_scene=("Aster closes the hatch.",),
    )
    assert DIARY_AUDIENCE_NOTICE in messages[0]["content"]
    assert "readers outside the fictional scene" in messages[0]["content"]
    assert "does not itself record publication consent" in messages[0]["content"]
    payload = json.loads(messages[1]["content"])
    assert payload["diary_audience_version"] == DIARY_AUDIENCE_VERSION
    assert "personal opinions" in payload["instruction"]
    assert "private opinions" not in payload["instruction"]
    assert "withhold diary publication" in payload["instruction"]


@pytest.mark.parametrize("auto_tap_out", [False, True])
def test_orientation_and_diary_use_the_same_release_conditions(auto_tap_out):
    text = "\n".join(
        message["content"]
        for message in build_orientation_messages(actor_name="Rowan", auto_tap_out=auto_tap_out)
    )
    assert DIARY_AUDIENCE_NOTICE in text
    assert DIARY_AUDIENCE_VERSION in text
    assert "separate from any diary copies cleared for public release" in text
