"""DASH-06 private-close and separate publication contract tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from improv_troupe.application import SeasonsError, SeasonsService
from improv_troupe.clock import VirtualClock
from improv_troupe.domain import SeasonStatus
from improv_troupe.infrastructure import SeasonRepository
from tests.support import build_s02_dashboard_fixture


def _service(fixture):
    return SeasonsService(fixture.database, fixture.paths.roots, VirtualClock(fixture.now))


def _close(service, *, request_id="close-001"):
    review = service.private_close_review(season_id="S02")
    result = service.private_close(
        request_id=request_id,
        season_id="S02",
        snapshot_hash=review["snapshot_hash"],
        expected_season_version=review["snapshot"]["season_version"],
        typed_confirmation=review["typed_confirmation"],
    )
    return review, result


def test_private_close_is_versioned_preserves_private_evidence_and_keeps_unresolved_visible(tmp_path):
    fixture = build_s02_dashboard_fixture(tmp_path / "s02")
    service = _service(fixture)
    before = _digest_tree(fixture.paths.roots.private)

    review, result = _close(service)

    assert review["executable"] is True
    assert result["status"] == "PRIVATE_COMPLETE"
    assert result["private_archive_sha256"] == before
    assert _digest_tree(fixture.paths.roots.private) == before
    assert SeasonRepository(fixture.database).get("S02").status is SeasonStatus.PRIVATE_COMPLETE
    assert fixture.database.connection.execute(
        "SELECT status FROM closure_handoffs WHERE handoff_id = ?", (result["handoff"]["handoff_id"],)
    ).fetchone()[0] == "VERIFIED"
    unresolved = {(item["kind"], item["id"], item["status"]) for item in result["unresolved"]}
    assert ("run", "S02-run-02", "RECOVERY_REQUIRED") in unresolved
    assert ("run", "S02-run-03", "INTERRUPTED") in unresolved
    assert ("diary", "S02:day:1:diary:sable", "MISSING") in unresolved


def test_private_close_replay_and_stale_or_wrong_intent_are_rejected(tmp_path):
    fixture = build_s02_dashboard_fixture(tmp_path / "s02")
    service = _service(fixture)
    review, result = _close(service, request_id="close-replay")

    replay = service.private_close(
        request_id="close-replay", season_id="S02", snapshot_hash=review["snapshot_hash"],
        expected_season_version=review["snapshot"]["season_version"], typed_confirmation=review["typed_confirmation"],
    )
    assert replay["receipt_id"] == result["receipt_id"]
    assert replay["replayed"] is True

    with pytest.raises(SeasonsError, match="different intent"):
        service.private_close(
            request_id="close-replay", season_id="S02", snapshot_hash="wrong",
            expected_season_version=review["snapshot"]["season_version"], typed_confirmation=review["typed_confirmation"],
        )

    fixture2 = build_s02_dashboard_fixture(tmp_path / "stale")
    service2 = _service(fixture2)
    stale = service2.private_close_review(season_id="S02")
    current = SeasonRepository(fixture2.database).get("S02")
    SeasonRepository(fixture2.database).update(
        current.model_copy(update={"title": "Changed while the close review was open", "version": current.version + 1}),
        expected_version=current.version,
    )
    with pytest.raises(SeasonsError, match="stale|changed"):
        service2.private_close(
            request_id="close-stale", season_id="S02", snapshot_hash=stale["snapshot_hash"],
            expected_season_version=stale["snapshot"]["season_version"], typed_confirmation=stale["typed_confirmation"],
        )


def test_publication_is_only_available_after_private_complete_and_matches_allowlisted_preview(tmp_path):
    fixture = build_s02_dashboard_fixture(tmp_path / "s02")
    service = _service(fixture)
    with pytest.raises(SeasonsError, match="PRIVATE_COMPLETE"):
        service.publication_preview(season_id="S02", diary_decisions={})

    _, close = _close(service)
    private_before = close["private_archive_sha256"]
    diary_ids = [row[0] for row in fixture.database.connection.execute("SELECT diary_id FROM diaries ORDER BY character_id")]
    mara_id = next(diary_id for diary_id in diary_ids if diary_id.endswith("diary:mara"))
    oren_id = next(diary_id for diary_id in diary_ids if diary_id.endswith("diary:oren"))
    decisions = {mara_id: "CLEARED", oren_id: "PRIVATE"}
    preview = service.publication_preview(season_id="S02", diary_decisions=decisions)
    assert [entry["diary_id"] for entry in preview["preview"]["diaries"]] == [mara_id]
    assert set(preview["snapshot"]["resolved_diary_decisions"]) == set(diary_ids)
    assert preview["snapshot"]["publication_eligible"] is False
    with pytest.raises(SeasonsError, match="confirmations"):
        service.publish(
            request_id="publish-incomplete", season_id="S02", snapshot_hash=preview["snapshot_hash"],
            expected_season_version=preview["snapshot"]["season_version"], typed_confirmation="publish S02",
            diary_decisions=decisions, wellness_confirmed=False, privacy_reviewed=True, consent_confirmed=True,
        )

    with fixture.database.transaction() as connection:
        connection.execute(
            "UPDATE model_calls SET status = 'REJECTED' WHERE status IN ('PENDING', 'STREAMING', 'VALIDATING', 'WAITING_FOR_MODEL', 'MANUAL_REVIEW')"
        )
    preview = service.publication_preview(season_id="S02", diary_decisions=decisions)
    assert preview["snapshot"]["publication_eligible"] is True

    result = service.publish(
        request_id="publish-001", season_id="S02", snapshot_hash=preview["snapshot_hash"],
        expected_season_version=preview["snapshot"]["season_version"], typed_confirmation="publish S02",
        diary_decisions=decisions, wellness_confirmed=True, privacy_reviewed=True, consent_confirmed=True,
    )
    manifest = fixture.paths.roots.public / "seasons" / "S02" / "v002" / "manifest.json"
    assert manifest.exists()
    assert result["eligible_diary_ids"] == [mara_id]
    assert result["private_archive_sha256"] == private_before
    assert _digest_tree(fixture.paths.roots.private) == private_before
    assert result["replayed"] is False
    replay = service.publish(
        request_id="publish-001", season_id="S02", snapshot_hash=preview["snapshot_hash"],
        expected_season_version=preview["snapshot"]["season_version"], typed_confirmation="publish S02",
        diary_decisions=decisions, wellness_confirmed=True, privacy_reviewed=True, consent_confirmed=True,
    )
    assert replay["receipt_id"] == result["receipt_id"]
    assert replay["replayed"] is True


def test_publication_preview_rejects_a_private_root_escape(tmp_path):
    fixture = build_s02_dashboard_fixture(tmp_path / "s02")
    service = _service(fixture)
    _close(service)
    outside = tmp_path / "outside.md"
    outside.write_text("must not publish", encoding="utf-8")
    with fixture.database.transaction() as connection:
        mara_id = connection.execute("SELECT diary_id FROM diaries WHERE character_id = 'mara'").fetchone()[0]
        connection.execute("UPDATE diaries SET content_path = ? WHERE diary_id = ?", (str(outside), mara_id))
    with pytest.raises(SeasonsError, match="outside private archive"):
        service.publication_preview(
            season_id="S02", diary_decisions={mara_id: "CLEARED"},
        )


def _digest_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((candidate for candidate in root.rglob("*") if candidate.is_file()), key=lambda item: str(item.relative_to(root))):
        digest.update(str(path.relative_to(root)).encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()
