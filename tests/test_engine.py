from pathlib import Path

from improv_troupe.domain import ProductionPlan
from improv_troupe.engine import Orchestrator
from improv_troupe.engine.events import SceneEnded, TurnCompleted
from improv_troupe.engine.export import to_markdown
from improv_troupe.engine.orchestrator import ActorRuntime
from improv_troupe.engine.parsing import clean_line
from improv_troupe.llm.fake import FakeClient

EXAMPLE = Path(__file__).parent.parent / "examples" / "the_last_train.plan.json"


def _runtimes(plan):
    fake = FakeClient()
    return [ActorRuntime(actor=a, client=fake, model="fake") for a in plan.cast]


async def test_full_dry_run_produces_transcript():
    plan = ProductionPlan.model_validate_json(EXAMPLE.read_text())
    orch = Orchestrator(plan, _runtimes(plan))

    completed, ended = [], None
    async for event in orch.run():
        if isinstance(event, TurnCompleted):
            completed.append(event.turn)
        elif isinstance(event, SceneEnded):
            ended = event

    assert len(completed) == plan.constraints.max_turns
    assert ended is not None and ended.line_count == plan.constraints.max_turns
    # First speaker respected.
    assert completed[0].speaker == "JONAS"
    # Round-robin alternates.
    assert completed[1].speaker == "MARA"


async def test_markdown_export_has_cast_and_lines():
    plan = ProductionPlan.model_validate_json(EXAMPLE.read_text())
    runtimes = _runtimes(plan)
    orch = Orchestrator(plan, runtimes)
    async for _ in orch.run():
        pass
    md = to_markdown(plan, orch.transcript, runtimes)
    assert "# The Last Train" in md
    assert "**JONAS.**" in md
    assert "Cast:" in md


def test_clean_line_strips_self_label_and_other_speakers():
    raw = "MARA: I told you not to come.\nJONAS: But I—"
    out = clean_line(raw, "MARA", ["JONAS"])
    assert out == "I told you not to come."


def test_clean_line_strips_wrapping_quotes():
    assert clean_line('"Just breathe."', "JONAS", ["MARA"]) == "Just breathe."
