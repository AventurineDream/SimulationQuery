"""DASH-07 synthetic one-day operator acceptance fixture."""

from __future__ import annotations

import asyncio
import json

import pytest

from improv_troupe.application.one_day_rehearsal import (
    OneDayRehearsalError,
    PRODUCTION_DATA_ROOT,
    _drain_rehearsal_slots,
    _seed_live_aether_one_day,
    run_one_day_rehearsal,
)
from improv_troupe.application import SceneModelManifest
from improv_troupe.clock import VirtualClock
from improv_troupe.config import AppConfig, BackendConfig
from datetime import datetime, timezone
from improv_troupe.infrastructure import SQLiteDatabase


def test_one_day_rehearsal_exercises_three_changed_states_and_writes_a_safe_report(tmp_path):
    root = tmp_path / "one-day"
    report = asyncio.run(run_one_day_rehearsal(root))

    assert [slot["slot"] for slot in report.slots] == ["morning", "afternoon", "evening"]
    assert [slot["status"] for slot in report.slots] == ["COMPLETED", "COMPLETED", "COMPLETED"]
    assert all(slot["turn_count"] == 16 for slot in report.slots)
    assert report.diary_counts == {"WRITTEN": 4}
    assert report.day_closed is True
    assert report.next_day_direction_recorded is True
    assert any(receipt_id.endswith(":day:1:closed") for receipt_id in report.receipt_ids)
    assert {"OrchestratorRoundAccepted", "TurnAccepted", "DiaryWritten", "DayClosed", "NextDayDirectionCreated"} <= set(report.receipt_event_types)
    assert report.provenance["model_endpoint_contacted"] is False
    assert report.unresolved == ()
    assert report.publication == "not attempted at report generation; no public projection was created"
    assert report.audit_summary["pending"] == 0
    assert report.public_archive_sha256 == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert "http" not in json.dumps(report.as_dict()).lower()

    persisted = json.loads((root / "state" / "one-day-rehearsal-report.json").read_text())
    assert persisted == report.as_dict()
    assert not (root / "public" / "seasons").exists()


def test_one_day_rehearsal_refuses_production_or_existing_data_roots(tmp_path):
    with pytest.raises(OneDayRehearsalError, match="production"):
        asyncio.run(run_one_day_rehearsal(PRODUCTION_DATA_ROOT))

    root = tmp_path / "occupied"
    root.mkdir()
    (root / "preserve.txt").write_text("do not replace", encoding="utf-8")
    with pytest.raises(OneDayRehearsalError, match="new or empty"):
        asyncio.run(run_one_day_rehearsal(root))
    assert (root / "preserve.txt").read_text(encoding="utf-8") == "do not replace"


def test_live_resume_does_not_replay_completed_slots():
    class _Run:
        def __init__(self, status):
            self.status = status

        def __getitem__(self, key):
            assert key == "status"
            return self.status

    class _Records:
        def __init__(self):
            self.evening_completed = False

        def get_run(self, run_id):
            return _Run(
                "COMPLETED"
                if run_id.endswith(("01", "02")) or self.evening_completed
                else "QUEUED"
            )

    class _Database:
        pass

    class _Worker:
        def __init__(self, records):
            self.calls = 0
            self.records = records

        async def drain_due(self, *, limit=None):
            assert limit == 1
            self.calls += 1
            self.records.evening_completed = True
            return 1

    # Patch the small repository seam so this regression test proves that an
    # explicit resume calls the worker only for the outstanding evening slot.
    import improv_troupe.application.one_day_rehearsal as rehearsal

    original = rehearsal.RecordRepository
    records = _Records()
    rehearsal.RecordRepository = lambda _: records
    try:
        worker = _Worker(records)
        asyncio.run(
            _drain_rehearsal_slots(
                worker=worker,
                database=_Database(),
                clock=VirtualClock(datetime(2026, 9, 7, 13, tzinfo=timezone.utc)),
                resume=True,
            )
        )
    finally:
        rehearsal.RecordRepository = original

    assert worker.calls == 1


def test_live_resume_claims_an_interrupted_slot_before_treating_it_as_terminal():
    class _Run:
        def __init__(self, status):
            self.status = status

        def __getitem__(self, key):
            assert key == "status"
            return self.status

    class _Records:
        def __init__(self):
            self.status = "INTERRUPTED"

        def get_run(self, run_id):
            return _Run("COMPLETED" if run_id.endswith(("01", "02")) else self.status)

    class _Queue:
        def __init__(self, _database):
            pass

        def requeue_completed_for_manual_resume(self, **_kwargs):
            return False

    class _Database:
        pass

    class _Worker:
        def __init__(self, records):
            self.records = records
            self.calls = 0

        async def drain_due(self, *, limit=None):
            assert limit == 1
            self.calls += 1
            self.records.status = "COMPLETED"
            return 1

    import improv_troupe.application.one_day_rehearsal as rehearsal

    original_records, original_queue = rehearsal.RecordRepository, rehearsal.WorkQueue
    records = _Records()
    rehearsal.RecordRepository = lambda _: records
    rehearsal.WorkQueue = _Queue
    try:
        worker = _Worker(records)
        asyncio.run(
            _drain_rehearsal_slots(
                worker=worker,
                database=_Database(),
                clock=VirtualClock(datetime(2026, 9, 7, 13, tzinfo=timezone.utc)),
                resume=True,
            )
        )
    finally:
        rehearsal.RecordRepository, rehearsal.WorkQueue = original_records, original_queue

    assert worker.calls == 1


def test_live_rehearsal_holds_when_an_earlier_slot_blocks_later_work():
    class _Run:
        def __getitem__(self, key):
            assert key == "status"
            return "QUEUED"

    class _Records:
        def get_run(self, _run_id):
            return _Run()

    class _Database:
        pass

    class _Result:
        status = "BLOCKED_BY_EARLIER_RUN"

    class _Worker:
        def __init__(self):
            self.calls = 0
            self.results = []

        async def drain_due(self, *, limit=None):
            assert limit == 1
            self.calls += 1
            self.results.append(_Result())
            return 1

    import improv_troupe.application.one_day_rehearsal as rehearsal

    original = rehearsal.RecordRepository
    rehearsal.RecordRepository = lambda _: _Records()
    try:
        worker = _Worker()
        asyncio.run(
            _drain_rehearsal_slots(
                worker=worker,
                database=_Database(),
                clock=VirtualClock(datetime(2026, 9, 7, 13, tzinfo=timezone.utc)),
                resume=False,
            )
        )
    finally:
        rehearsal.RecordRepository = original

    assert worker.calls == 1


def test_live_rehearsal_persists_the_exact_identity_inputs_used_for_comparison(tmp_path):
    database = SQLiteDatabase(tmp_path / "state" / "improv.sqlite3")
    database.migrate()
    config = AppConfig(backends={"local": BackendConfig(base_url="http://localhost", kind="ollama")})
    manifest = SceneModelManifest.model_validate(
        {
            "orchestrator": {"backend": "local", "model": "director"},
            "actor_default": {"backend": "local", "model": "actor"},
        }
    )

    _seed_live_aether_one_day(
        database,
        VirtualClock(datetime(2026, 9, 7, 13, tzinfo=timezone.utc)),
        config=config,
        manifest=manifest,
    )

    assert database.connection.execute("SELECT COUNT(*) FROM character_card_versions").fetchone()[0] == 4
    assert database.connection.execute("SELECT COUNT(*) FROM role_sheet_versions").fetchone()[0] == 4
    assert database.connection.execute(
        "SELECT COUNT(*) FROM character_card_versions WHERE status = 'REHEARSAL_ANCHOR'"
    ).fetchone()[0] == 4
