import asyncio

from improv_troupe.application import SceneModelManifest, run_live_three_day_rehearsal
from improv_troupe.application.one_day_rehearsal import DeterministicRehearsalClient
from improv_troupe.config import AppConfig, BackendConfig


def test_three_day_rehearsal_completes_and_proves_continuity_context(tmp_path):
    client = DeterministicRehearsalClient()
    config = AppConfig(
        backends={
            "synthetic": BackendConfig(
                base_url="http://synthetic.invalid",
                kind="ollama",
                models=("synthetic-director", "synthetic-actor"),
            )
        },
        default_backend="synthetic",
    )
    manifest = SceneModelManifest.model_validate(
        {
            "orchestrator": {"backend": "synthetic", "model": "synthetic-director"},
            "actor_default": {"backend": "synthetic", "model": "synthetic-actor"},
        }
    )

    report = asyncio.run(
        run_live_three_day_rehearsal(
            tmp_path / "three-day",
            config=config,
            manifest=manifest,
            client_factory=lambda _: client,
        )
    )

    assert len(report.days) == 3
    assert all(len(day["runs"]) == 3 for day in report.days)
    assert all(run["turn_count"] == 16 for day in report.days for run in day["runs"])
    assert all(len(day["diaries"]) == 4 for day in report.days)
    assert all(day["closed"] for day in report.days)
    assert all(day["next_day_direction_recorded"] for day in report.days)
    assert len(report.continuity_evidence) == 2
    assert all(row["prior_canon_items"] > 0 for row in report.continuity_evidence)
    assert all(row["actor_memory_items"] > 0 for row in report.continuity_evidence)
    assert all(row["private_day_direction_present"] for row in report.continuity_evidence)
    assert report.audit["pending"] == 0
    assert report.unresolved == ()
    assert (tmp_path / "three-day" / "state" / "three-day-rehearsal-report.json").is_file()
