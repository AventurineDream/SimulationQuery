import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from improv_troupe.domain import ProductionPlan

EXAMPLE = Path(__file__).parent.parent / "examples" / "the_last_train.plan.json"


def test_example_plan_loads():
    plan = ProductionPlan.model_validate_json(EXAMPLE.read_text())
    assert plan.title == "The Last Train"
    assert plan.cast_names == ["MARA", "JONAS"]
    assert plan.direction.first_speaker == "JONAS"


def test_duplicate_cast_names_rejected():
    data = json.loads(EXAMPLE.read_text())
    data["cast"][1]["name"] = "MARA"
    with pytest.raises(ValidationError):
        ProductionPlan.model_validate(data)


def test_unknown_first_speaker_rejected():
    data = json.loads(EXAMPLE.read_text())
    data["direction"]["first_speaker"] = "NOBODY"
    with pytest.raises(ValidationError):
        ProductionPlan.model_validate(data)


def test_empty_cast_rejected():
    data = json.loads(EXAMPLE.read_text())
    data["cast"] = []
    with pytest.raises(ValidationError):
        ProductionPlan.model_validate(data)
