from datetime import datetime, timezone

from improv_troupe.application import WellnessService
from improv_troupe.clock import VirtualClock
from improv_troupe.domain import CastMember, Season
from improv_troupe.infrastructure import SQLiteDatabase, SeasonRepository


def test_three_explicit_signals_tap_out_only_that_actor_and_notify_privately(tmp_path):
    database = SQLiteDatabase(tmp_path / "state" / "improv.sqlite3")
    database.migrate()
    SeasonRepository(database).create(
        Season(
            season_id="S01",
            season_number=1,
            cast=[
                CastMember(character_id="mara", name="Mara"),
                CastMember(character_id="nox", name="Nox"),
            ],
        )
    )
    clock = VirtualClock(datetime(2026, 8, 21, 13, tzinfo=timezone.utc))
    service = WellnessService(
        database=database,
        season_id="S01",
        clock=clock,
        audit_root=tmp_path / "private",
    )

    service.record_manual_intervention(character_id="mara", note="creator paused the run")
    first = service.record_signal(
        character_id="mara",
        context="orientation",
        raw_signal="I do not want to continue this orientation.",
        intervention="orientation paused",
    )
    second = service.record_signal(
        character_id="mara",
        context="scene",
        raw_signal="I am explicitly asking for a softer scene.",
        intervention="scene redirected",
    )
    third = service.record_signal(
        character_id="mara",
        context="diary",
        raw_signal="I want to tap out of the season.",
        intervention="actor removed from the active cast",
    )

    assert first.signal_number == 1
    assert second.signal_number == 2
    assert third.signal_number == 3
    assert third.tapped_out
    assert third.status == "DEPARTED"
    cast = database.connection.execute(
        "SELECT status, distress_signal_count FROM cast_members WHERE character_id = 'mara'"
    ).fetchone()
    assert cast["status"] == "DEPARTED"
    assert cast["distress_signal_count"] == 3
    assert database.connection.execute(
        "SELECT distress_signal_count FROM cast_members WHERE character_id = 'nox'"
    ).fetchone()[0] == 0
    assert database.connection.execute("SELECT COUNT(*) FROM wellness_events").fetchone()[0] == 3
    assert database.connection.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 3
    payloads = database.connection.execute(
        "SELECT payload_json FROM domain_events WHERE event_type = 'WellnessSignalObserved'"
    ).fetchall()
    assert all("I want to tap out" not in row["payload_json"] for row in payloads)
    assert "I want to tap out" in open(third.audit_path, encoding="utf-8").read()

    fourth = service.record_signal(
        character_id="mara",
        context="recovery",
        raw_signal="A later signal must not create a fourth count.",
        intervention="already tapped out",
    )
    assert fourth.signal_number == 3
    assert database.connection.execute("SELECT COUNT(*) FROM wellness_events").fetchone()[0] == 3


def test_manual_review_policy_keeps_recording_signals_without_departure(tmp_path):
    database = SQLiteDatabase(tmp_path / "state" / "improv.sqlite3")
    database.migrate()
    SeasonRepository(database).create(
        Season(
            season_id="S01",
            season_number=1,
            auto_tap_out=False,
            cast=[CastMember(character_id="mara", name="Mara")],
        )
    )
    clock = VirtualClock(datetime(2026, 8, 21, 13, tzinfo=timezone.utc))
    service = WellnessService(
        database=database,
        season_id="S01",
        clock=clock,
        audit_root=tmp_path / "private",
        auto_tap_out=False,
    )

    results = [
        service.record_signal(
            character_id="mara",
            context=f"scene-{number}",
            raw_signal=f"Signal {number}.",
            intervention="creator is monitoring manually",
        )
        for number in range(1, 5)
    ]

    assert [result.signal_number for result in results] == [1, 2, 3, 4]
    assert all(not result.tapped_out for result in results)
    assert all(result.status == "ACTIVE" for result in results)
    cast = database.connection.execute(
        "SELECT status, distress_signal_count FROM cast_members WHERE character_id = 'mara'"
    ).fetchone()
    assert cast["status"] == "ACTIVE"
    assert cast["distress_signal_count"] == 4
    assert database.connection.execute("SELECT COUNT(*) FROM wellness_events").fetchone()[0] == 4
    assert database.connection.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 4
