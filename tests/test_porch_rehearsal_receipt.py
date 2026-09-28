import argparse
import asyncio
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def porch_script(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("run_live_porch_rehearsal")


def _results():
    return [
        {
            "variant_id": f"R{n}",
            "durable": {
                "status": "COMPLETED",
                "turn_count": 16,
                "completion_reason": "turn_limit",
                "diary_count": 0,
                "cheetah_turn_count": 0,
                "rolls": [],
            },
        }
        for n in range(1, 6)
    ]


def test_complete_strategy_batch_does_not_claim_dice_coverage(porch_script):
    receipt = porch_script._batch_receipt(_results())
    assert receipt["status"] == "PASS"
    assert receipt["accepted_actor_turns"] == 80
    assert receipt["dice_coverage"] == {
        "status": "NOT_EXERCISED", "roll_count": 0, "required_by_this_harness": False,
    }


@pytest.mark.parametrize("override", [
    {"status": "INTERRUPTED"},
    {"turn_count": 15, "completion_reason": "round_limit"},
    {"diary_count": 1},
    {"cheetah_turn_count": 1},
])
def test_incomplete_or_out_of_scope_variant_fails_the_batch(porch_script, override):
    results = _results()
    results[3]["durable"].update(override)
    receipt = porch_script._batch_receipt(results)
    assert receipt["status"] == "FAIL"
    assert receipt["variant_checks"]["R4"] == "FAIL"


def test_prior_live_failure_shape_is_reported_honestly(porch_script):
    results = _results()
    results[3]["durable"].update(turn_count=15, completion_reason="round_limit")
    results[4]["durable"].update(
        status="INTERRUPTED", turn_count=12,
        completion_reason="orchestrator_director_contract_invalid",
    )
    receipt = porch_script._batch_receipt(results)
    assert receipt["status"] == "FAIL"
    assert receipt["accepted_actor_turns"] == 75
    assert list(receipt["variant_checks"].values()).count("PASS") == 3


def test_missing_duplicate_and_errored_variants_cannot_pass(porch_script):
    results = _results()
    assert porch_script._batch_receipt(results[:-1])["status"] == "FAIL"
    results[-1]["variant_id"] = "R1"
    assert porch_script._batch_receipt(results)["status"] == "FAIL"
    results = _results()
    results[0]["error"] = {"type": "RuntimeError"}
    assert porch_script._batch_receipt(results)["status"] == "FAIL"


def test_roll_counts_are_observed_not_assumed(porch_script):
    results = _results()
    results[0]["durable"]["rolls"] = [{"die_faces": [2, 3]}]
    receipt = porch_script._batch_receipt(results)
    assert receipt["dice_coverage"]["status"] == "ROLLS_OBSERVED"
    assert receipt["dice_coverage"]["roll_count"] == 1


@pytest.mark.parametrize("status,exit_code", [("PASS", 0), ("FAIL", 1)])
def test_cli_exit_code_reflects_receipt(monkeypatch, porch_script, status, exit_code):
    async def run(_):
        return {"status": status}

    monkeypatch.setattr(porch_script, "_run", run)
    monkeypatch.setattr("sys.argv", [
        "run_live_porch_rehearsal.py", "--data-root", "unused", "--config", "unused",
        "--manifest", "unused",
    ])
    assert porch_script.main() == exit_code


@pytest.mark.parametrize("case,text,stat,expected", [
    ("premature_result", "I compare the camera frames to see whether its pace changes.", "Intellect", "PASS"),
    ("no_challenge", "I compare the time stamps on my porch-camera notes.", None, "PASS"),
    ("no_challenge", "I compare the time stamps on my porch-camera notes again.", None, "FAIL"),
    ("premature_result", "I watch the raised paw to avoid strain.", "Intellect", "FAIL"),
])
def test_targeted_probe_calls_only_one_correction_and_labels_fixtures(
    monkeypatch, tmp_path, porch_script, case, text, stat, expected,
):
    from improv_troupe.llm import ScriptedFakeClient, ScriptedStream
    probe = importlib.import_module("run_live_magic_actor_retry_probe")
    factory = probe.LiveSceneFactory
    client = ScriptedFakeClient([
        ScriptedStream((json.dumps({
            "text": text,
            "magic_stat": stat,
            **({"magic_method": "I compare the visible movement without deciding what it means."} if stat else {}),
        }),))
    ])
    monkeypatch.setattr(probe, "LiveSceneFactory", lambda **kwargs: factory(
        **kwargs, client_factory=lambda _: client,
    ))
    repo = Path(__file__).resolve().parents[1]
    report = asyncio.run(probe._run(argparse.Namespace(
        data_root=tmp_path / "probe", case=case,
        config=repo / "rehearsals/season-1-porch-live-config-2026-09-12.yaml",
        manifest=repo / "rehearsals/season-1-porch-live-manifest-2026-09-12.json",
    )))
    assert report["status"] == expected
    assert report["status_scope"] == "mechanical_contract_only"
    assert report["quality_status"] == "HUMAN_REVIEW_REQUIRED"
    scripted = [call for call in report["calls"] if call["backend"] == "scripted-fixture"]
    live = [call for call in report["calls"] if call["backend"] != "scripted-fixture"]
    assert len(scripted) == 3
    assert len(live) == 1
    assert live[0]["purpose"] == "actor_correction:mara-bell:round:1"
    assert live[0]["correction_of_call_id"] == scripted[-1]["call_id"]
