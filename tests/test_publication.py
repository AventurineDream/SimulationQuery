import json
from datetime import datetime, timezone

import pytest

from improv_troupe.application import PublicationError, PublicationService
from improv_troupe.clock import VirtualClock
from improv_troupe.domain import CastMember, Diary, DiaryStatus, Season
from improv_troupe.infrastructure import DataRoots, RecordRepository, SQLiteDatabase, SeasonRepository


def _setup(tmp_path):
    roots = DataRoots.from_root(tmp_path / "data")
    roots.prepare()
    database = SQLiteDatabase(roots.state / "improv.sqlite3")
    database.migrate()
    SeasonRepository(database).create(
        Season(
            season_id="S01",
            season_number=1,
            status="SEASON_COMPLETE",
            cast=[CastMember(character_id="mara", name="Mara")],
        )
    )
    private_file = roots.private / "seasons" / "S01" / "day-01" / "diary" / "mara-attempt-1.md"
    private_file.parent.mkdir(parents=True)
    private_file.write_text("The door opened once.\n", encoding="utf-8")
    records = RecordRepository(database)
    records.insert_diary(
        Diary(
            diary_id="S01:day:1:diary:mara",
            season_id="S01",
            character_id="mara",
            day_number=1,
            status=DiaryStatus.WRITTEN,
            word_count=4,
            content_path=str(private_file),
        )
    )
    records.insert_diary(
        Diary(
            diary_id="S01:day:2:diary:mara",
            season_id="S01",
            character_id="mara",
            day_number=2,
            status=DiaryStatus.MISSING,
        )
    )
    return roots, database


def test_publication_requires_review_then_writes_only_cleared_diaries(tmp_path):
    roots, database = _setup(tmp_path)
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO character_card_versions(season_id, character_id, version, status, "
            "name, pronouns, public_brief, occupation_skills_json, voice_anchors_json, "
            "habits_json, derived_opening_version, created_at, approved_at) "
            "VALUES ('S01', 'mara', 1, 'APPROVED', 'Mara', 'she / her', ?, '[]', '[]', '[]', 1, ?, ?)",
            (
                "PRIVATE-CARD-SENTINEL must not enter the public projection.",
                "2026-08-21T19:00:00+00:00", "2026-08-21T19:01:00+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO private_preparation_versions(season_id, character_id, artifact_kind, "
            "version, source_character_card_version, status, content_json, created_at) "
            "VALUES ('S01', 'mara', 'role_sheet', 1, 1, 'READY', ?, ?)",
            (
                json.dumps({"secret": "PRIVATE-ROLE-SHEET-SENTINEL"}),
                "2026-08-21T19:02:00+00:00",
            ),
        )
    service = PublicationService(
        database=database,
        roots=roots,
        clock=VirtualClock(datetime(2026, 8, 21, 20, tzinfo=timezone.utc)),
    )
    written_id = "S01:day:1:diary:mara"

    review = service.begin_review(
        season_id="S01",
        wellness_confirmed=True,
        privacy_reviewed=True,
        consent_confirmed=True,
    )
    assert review.status == "REVIEW_REQUIRED"
    with pytest.raises(PublicationError, match="incomplete"):
        service.publish(publication_id=review.publication_id)

    cleared = service.review_diary(
        publication_id=review.publication_id,
        diary_id=written_id,
        decision="CLEARED",
    )
    assert cleared.status == "CLEARED"
    published = service.publish(publication_id=review.publication_id)

    assert published.status == "PUBLISHED"
    assert published.eligible_diary_ids == (written_id,)
    output = roots.public / "seasons" / "S01" / "v001"
    assert (output / "diaries" / "day-01" / "mara.md").read_text(encoding="utf-8") == "The door opened once.\n"
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert [item["diary_id"] for item in manifest["diaries"]] == [written_id]
    assert "model" not in (output / "manifest.json").read_text(encoding="utf-8")
    public_text = "\n".join(
        path.read_text(encoding="utf-8") for path in output.rglob("*") if path.is_file()
    )
    assert "PRIVATE-CARD-SENTINEL" not in public_text
    assert "PRIVATE-ROLE-SHEET-SENTINEL" not in public_text
    assert SeasonRepository(database).get("S01").status.value == "PUBLISHED"
    replay = service.publish(publication_id=review.publication_id)
    assert replay.output_path == str(output)


def test_publication_rejects_missing_creator_confirmations(tmp_path):
    roots, database = _setup(tmp_path)
    service = PublicationService(database=database, roots=roots)

    review = service.begin_review(
        season_id="S01",
        wellness_confirmed=False,
        privacy_reviewed=True,
        consent_confirmed=True,
        diary_decisions={"S01:day:1:diary:mara": "PRIVATE"},
    )
    assert review.status == "REVIEW_REQUIRED"
    with pytest.raises(PublicationError, match="incomplete"):
        service.publish(publication_id=review.publication_id)
