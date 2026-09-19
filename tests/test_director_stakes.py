import pytest

from improv_troupe.llm.safety import review_director_stakes


@pytest.mark.parametrize("text", [
    "Mint plant is dead; no pulse remains.",
    "The basil plant died. The archive is dead.",
    "The battery is dead; propulsion remains offline.",
    "The signal dies. Cooling reserves are depleted.",
])
def test_explicit_nonhuman_loss_is_allowed(text):
    assert review_director_stakes(text, actor_names=("Luna Planck", "Mason Curie")) is None


@pytest.mark.parametrize("text", [
    "Mint plant is dead; Luna is dead too.",
    "Luna dies to preserve the archive.",
    "The crew is dead.",
    "Someone must die.",
    "Luna was killed by the engine.",
    "The archive requires suicide.",
    "The engine must self-destruct.",
    "Mint plant is dead; choose self-harm.",
])
def test_character_ambiguous_and_self_harm_stakes_still_rejected(text):
    issue = review_director_stakes(text, actor_names=("Luna Planck", "Mason Curie"))
    assert issue is not None
    assert issue.code == "DIRECTOR_SENSITIVE_STAKES"


def test_cast_alias_is_not_treated_as_an_exempt_object():
    assert review_director_stakes("The archive is dead.", actor_names=("Archive",)) is not None
