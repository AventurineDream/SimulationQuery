import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from improv_troupe.application.actor_audition_rehearsal import ActorAuditionRehearsalError, _drain, run_live_actor_audition_rehearsal
from improv_troupe.application.live_runtime import SceneModelManifest
from improv_troupe.application.one_day_rehearsal import DeterministicRehearsalClient
from improv_troupe.clock import VirtualClock
from improv_troupe.config import AppConfig, BackendConfig
from improv_troupe.domain import ScheduleSlot, Season
from improv_troupe.infrastructure import RecordRepository, ScheduleRepository, SeasonRepository, SQLiteDatabase, WorkQueue


class CorrectingResolutionClient(DeterministicRehearsalClient):
    def __init__(self):
        super().__init__()
        self.resolution_calls = 0

    async def stream_chat(self, model, messages, **params):
        instruction = "\n".join(message["content"] for message in messages)
        if "<OUTCOME>" in instruction:
            self.resolution_calls += 1
            if self.resolution_calls == 1:
                yield (
                    "<OUTCOME>SUCCESS</OUTCOME>"
                    "<CENTRAL_QUESTION_ANSWERED>The archive is preserved while propulsion is permanently lost.</CENTRAL_QUESTION_ANSWERED>"
                    "<NARRATION>Ivy releases the override while the archive settles into protected storage.</NARRATION>"
                    "<IRREVERSIBLE_CHANGE>Propulsion is permanently disabled.</IRREVERSIBLE_CHANGE>"
                    "<GAINED>The living archive remains intact.</GAINED>"
                    "<LOST>The vessel permanently loses propulsion.</LOST>"
                    "<CANON_UPDATE>The archive is protected.</CANON_UPDATE>"
                    "<CANON_UPDATE>Propulsion is permanently disabled.</CANON_UPDATE>"
                    "<COMPLETE>true</COMPLETE>"
                )
            else:
                yield (
                    "<OUTCOME>COSTLY_SUCCESS</OUTCOME>"
                    "<CENTRAL_QUESTION_ANSWERED>The archive is preserved while propulsion is permanently lost.</CENTRAL_QUESTION_ANSWERED>"
                    "<NARRATION>The archive settles into protected storage as propulsion falls permanently silent. Ambient machinery replaces the emergency alarms.</NARRATION>"
                    "<IRREVERSIBLE_CHANGE>Propulsion is permanently disabled.</IRREVERSIBLE_CHANGE>"
                    "<GAINED>The living archive remains intact.</GAINED>"
                    "<LOST>The vessel permanently loses propulsion.</LOST>"
                    "<CANON_UPDATE>The archive is protected.</CANON_UPDATE>"
                    "<CANON_UPDATE>Propulsion is permanently disabled.</CANON_UPDATE>"
                    "<COMPLETE>true</COMPLETE>"
                )
            return
        async for chunk in super().stream_chat(model, messages, **params):
            yield chunk


def test_audition_drain_advances_to_a_queued_retry_time(tmp_path):
    database = SQLiteDatabase(tmp_path / "state.sqlite3")
    database.migrate()
    SeasonRepository(database).create(Season(season_id="S02-ACTOR-AUDITION", season_number=2))
    scheduled = datetime.fromisoformat("2026-09-15T12:00:00-07:00")
    run_id = "S02-ACTOR-AUDITION-run-01"
    ScheduleRepository(database).add(ScheduleSlot(
        slot_id=run_id, season_id="S02-ACTOR-AUDITION", day_number=1,
        slot_number=2, run_number=1, scheduled_local=scheduled,
        scheduled_utc=scheduled.astimezone(timezone.utc), utc_offset="-07:00",
    ))
    records = RecordRepository(database)
    records.insert_run(run_id=run_id, season_id="S02-ACTOR-AUDITION", slot_id=run_id, status="QUEUED")
    retry_at = scheduled.astimezone(timezone.utc) + timedelta(minutes=1)
    WorkQueue(database).enqueue(
        work_id=f"work:{run_id}", natural_key=f"retry:{run_id}", kind="RUN_SCENE",
        payload={"run_id": run_id}, available_at=retry_at.isoformat(), priority=1,
    )
    clock = VirtualClock(scheduled.astimezone(timezone.utc))

    class Worker:
        async def drain_due(self, *, limit):
            if clock.now() < retry_at:
                return 0
            records.update_run_status(
                run_id=run_id, status="COMPLETED", completion_reason="test",
                expected_status="QUEUED",
            )
            return 1

    asyncio.run(_drain(Worker(), database, clock))
    assert clock.now() == retry_at
    assert records.get_run(run_id)["status"] == "COMPLETED"


def test_actor_audition_rehearsal_reaches_a_private_resolution(tmp_path):
    client = DeterministicRehearsalClient()
    config = AppConfig(
        backends={
            "synthetic": BackendConfig(
                base_url="http://synthetic.invalid",
                kind="ollama",
                models=("director", "gpt", "thrasher", "qwen"),
            )
        },
        default_backend="synthetic",
    )
    manifest = SceneModelManifest.model_validate({
        "orchestrator": {"backend": "synthetic", "model": "director"},
        "actors": {
            "boson-reefer": {"backend": "synthetic", "model": "gpt"},
            "chrysanthemum-ballad": {"backend": "synthetic", "model": "thrasher", "prompt_profile": "thrasher"},
            "click-tourmaline": {"backend": "synthetic", "model": "qwen"},
        },
    })

    report = asyncio.run(run_live_actor_audition_rehearsal(
        tmp_path / "audition", config=config, manifest=manifest,
        client_factory=lambda _: client,
    ))

    assert len(report.runs) == 4
    assert all(run["turn_count"] == 12 for run in report.runs)
    assert len(report.diaries) == 6
    assert report.resolution["complete"] is True
    assert report.resolution["outcome"] == "COSTLY_SUCCESS"
    assert report.director_evidence["resolution_recorded"] is True
    assert report.audit["pending"] == 0
    assert report.unresolved == ()


def test_actor_audition_refuses_peach_casting(tmp_path):
    config = AppConfig(
        backends={
            "synthetic": BackendConfig(
                base_url="http://synthetic.invalid",
                kind="ollama",
                models=("director", "peach"),
            )
        },
        default_backend="synthetic",
    )
    manifest = SceneModelManifest.model_validate({
        "orchestrator": {"backend": "synthetic", "model": "director"},
        "actor_default": {"backend": "synthetic", "model": "peach-roleplay"},
        "actors": {
            "williams-lophophora-ii": {"backend": "synthetic", "model": "Peach-2.0-9B"},
        },
    })

    with pytest.raises(ActorAuditionRehearsalError, match="Peach is excluded"):
        asyncio.run(run_live_actor_audition_rehearsal(
            tmp_path / "audition",
            config=config,
            manifest=manifest,
            client_factory=lambda _: DeterministicRehearsalClient(),
        ))


def test_final_diaries_close_before_one_surgical_resolution_correction(tmp_path):
    client = CorrectingResolutionClient()
    config = AppConfig(
        backends={
            "synthetic": BackendConfig(
                base_url="http://synthetic.invalid",
                kind="ollama",
                models=("director", "gpt", "thrasher", "qwen"),
            )
        },
        default_backend="synthetic",
    )
    manifest = SceneModelManifest.model_validate({
        "orchestrator": {"backend": "synthetic", "model": "director"},
        "actors": {
            "boson-reefer": {"backend": "synthetic", "model": "gpt"},
            "chrysanthemum-ballad": {"backend": "synthetic", "model": "thrasher"},
            "click-tourmaline": {"backend": "synthetic", "model": "qwen"},
        },
    })

    report = asyncio.run(run_live_actor_audition_rehearsal(
        tmp_path / "audition-correction",
        config=config,
        manifest=manifest,
        client_factory=lambda _: client,
    ))

    assert client.resolution_calls == 2
    assert report.resolution["outcome"] == "COSTLY_SUCCESS"
    assert len(report.diaries) == 6
    assert all(diary["status"] == "WRITTEN" for diary in report.diaries)
    assert report.audit["rejected"] == 1
