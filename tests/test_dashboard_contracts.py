from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from improv_troupe.web.dashboard_contracts import (
    CallRawDisclosure,
    DashboardEnvelope,
    DashboardMeta,
    DiaryAttemptDisclosure,
    Freshness,
)


def test_dashboard_envelope_has_a_strict_versioned_evidence_boundary():
    checked_at = datetime(2026, 8, 25, 18, tzinfo=timezone.utc)
    envelope = DashboardEnvelope(
        meta=DashboardMeta(
            checked_at=checked_at,
            environment="sandbox",
            season_id="S02",
            season_version=18,
            freshness=Freshness.PARTIAL,
        ),
        data={"attention_count": 1},
    )

    assert envelope.model_dump(mode="json") == {
        "meta": {
            "contract_version": 1,
            "checked_at": "2026-08-25T18:00:00Z",
            "environment": "sandbox",
            "season_id": "S02",
            "season_version": 18,
            "freshness": "partial",
        },
        "data": {"attention_count": 1},
    }
    with pytest.raises(ValidationError):
        DashboardMeta(
            checked_at=checked_at,
            environment="sandbox",
            freshness=Freshness.FRESH,
            hidden_plan="not allowed",
        )


def test_diary_attempt_contract_cannot_grow_raw_wellness_or_output_fields():
    disclosure = {
        "diary_id": "S02:day:1:diary:tavi",
        "season_id": "S02",
        "character_id": "tavi",
        "character_name": "Tavi",
        "day_number": 1,
        "status": "PRIVATE",
        "source": "private_attempt",
        "content": "The fog knew which shelf I was avoiding.",
        "wellness_signal_present": True,
        "attempt_number": 1,
        "evidence_note": "Diary text safely separated.",
    }
    assert DiaryAttemptDisclosure(**disclosure).immutable_read is True
    with pytest.raises(ValidationError):
        DiaryAttemptDisclosure(**disclosure, raw_output="forbidden")
    with pytest.raises(ValidationError):
        DiaryAttemptDisclosure(**disclosure, wellness_text="forbidden")


def test_call_raw_disclosure_cannot_grow_wellness_or_path_fields():
    disclosure = {
        "call_id": "S02-run-01:mara:r1:a1",
        "season_id": "S02",
        "content": "Synthetic non-wellness output.",
        "evidence_note": "Read only.",
    }
    assert CallRawDisclosure(**disclosure).immutable_read is True
    with pytest.raises(ValidationError):
        CallRawDisclosure(**disclosure, wellness_text="forbidden")
    with pytest.raises(ValidationError):
        CallRawDisclosure(**disclosure, output_path="/private/forbidden")
