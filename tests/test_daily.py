import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

from improv_troupe.application import (
    DailyDirector,
    DayClosureService,
    DiaryActor,
    DiaryService,
    ModelCallExecutor,
)
from improv_troupe.clock import VirtualClock
from improv_troupe.domain import HiddenSeasonPlan, OpeningSnapshot, RoleSheet, Season
from improv_troupe.infrastructure import RecordRepository, SQLiteDatabase, SeasonRepository
from improv_troupe.llm import ScriptedFakeClient, ScriptedStream


def _executor(database, client, root, clock):
    return ModelCallExecutor(
        database=database,
        client=client,
        clock=clock,
        audit_root=root,
        backend="scripted-fake",
        model="pilot-model",
    )


def _database(tmp_path):
    database = SQLiteDatabase(tmp_path / "state" / "improv.sqlite3")
    database.migrate()
    SeasonRepository(database).create(Season(season_id="S01", season_number=1))
    return database


def test_day_closure_waits_for_cutoff_marks_missing_and_accepts_late_diary(tmp_path):
    database = _database(tmp_path)
    clock = VirtualClock(datetime(2026, 8, 21, 15, tzinfo=timezone.utc))
    closure = DayClosureService(
        season_id="S01",
        day_number=1,
        original_date=date(2026, 8, 21),
        active_character_ids=("mara", "nox"),
        database=database,
        clock=clock,
    )
    third_resolved = datetime(2026, 8, 21, 14, tzinfo=timezone.utc)

    open_result = closure.close_if_ready(
        run_statuses=("COMPLETED", "COMPLETED", "COMPLETED"),
        third_run_resolved_at=third_resolved,
    )

    assert open_result.status == "OPEN"
    assert open_result.reason == "diaries_pending"
    records = RecordRepository(database)
    mara = records.get_diary(season_id="S01", character_id="mara", day_number=1)
    records.update_diary(
        diary_id=mara["diary_id"],
        chosen_slot_number=1,
        status="WRITTEN",
        word_count=400,
        late=False,
        content_path="/private/mara/day-01.md",
    )
    clock.advance(timedelta(hours=1, minutes=1))
    closed = closure.close_if_ready(
        run_statuses=("COMPLETED", "COMPLETED", "COMPLETED"),
        third_run_resolved_at=third_resolved,
    )

    assert closed.status == "CLOSED"
    assert closed.missing_diary_ids == ("S01:day:1:diary:nox",)
    assert database.connection.execute("SELECT closed FROM days").fetchone()[0] == 1
    missing = records.get_diary(season_id="S01", character_id="nox", day_number=1)
    assert missing["status"] == "MISSING"

    nox_executor = _executor(
        database,
        ScriptedFakeClient(
            [
                ScriptedStream(
                    (
                        "<DIARY_SLOT>3</DIARY_SLOT><WRITE_NOW>true</WRITE_NOW>"
                        "<DIARY_TEXT>I arrived late and remember one blue light.</DIARY_TEXT>"
                        "<EVIDENCE_REFS>1</EVIDENCE_REFS>",
                    )
                )
            ]
        ),
        tmp_path / "private" / "nox",
        clock,
    )
    nox_actor = DiaryActor(
        character_id="nox",
        name="Nox",
        role_sheet=RoleSheet(character_id="nox"),
        executor=nox_executor,
    )
    late = asyncio.run(
        DiaryService(
            season_id="S01",
            day_number=1,
            actors=(nox_actor,),
            clock=clock,
        ).write_after_run(
            nox_actor,
            current_slot_number=3,
            accepted_scene=("Nox: I only know what Nox saw.",),
            cutoff_at=closed.cutoff_at,
        )
    )
    assert late.status == "LATE"
    assert records.get_diary(season_id="S01", character_id="nox", day_number=1)["status"] == "LATE"


def test_daily_director_requires_closure_and_keeps_direction_private(tmp_path):
    database = _database(tmp_path)
    clock = VirtualClock(datetime(2026, 8, 21, 18, tzinfo=timezone.utc))
    records = RecordRepository(database)
    records.insert_day(season_id="S01", day_number=1, original_date="2026-08-21")
    records.update_day(
        season_id="S01",
        day_number=1,
        cutoff_at="2026-08-21T16:00:00+00:00",
        closed=True,
    )
    executor = _executor(
        database,
        ScriptedFakeClient(
            [
                ScriptedStream(
                    (
                            "<NARRATION>The house wakes beneath a second moon.</NARRATION>"
                        "<COMPLETE>false</COMPLETE>",
                    )
                )
            ]
        ),
        tmp_path / "private" / "orchestrator",
        clock,
    )
    director = DailyDirector(
        season_id="S01",
        source_day_number=1,
        opening=OpeningSnapshot(set="House", setting="Night", cast=["Mara", "Nox", "Iris", "Sol"]),
        private_plan=HiddenSeasonPlan(hidden_mysteries=["private moon"]),
        orchestrator=executor,
    )

    with pytest.raises(ValueError, match="closed day"):
        asyncio.run(director.write_next_day(closed_diaries=("diary",), day_is_closed=False))

    result = asyncio.run(
        director.write_next_day(
            closed_diaries=("Mara only knows the door.",),
            day_is_closed=True,
        )
    )

    assert result.target_day_number == 2
    assert "second moon" in open(result.content_path, encoding="utf-8").read()
    prompt = database.connection.execute(
        "SELECT prompt_path FROM model_calls WHERE purpose LIKE 'next-day-direction:%'"
    ).fetchone()[0]
    assert "Mara only knows the door." in open(prompt, encoding="utf-8").read()


def test_daily_director_repairs_cast_puppeteering_once_without_losing_direction(tmp_path):
    database = _database(tmp_path)
    clock = VirtualClock(datetime(2026, 8, 21, 18, tzinfo=timezone.utc))
    records = RecordRepository(database)
    records.insert_day(season_id="S01", day_number=1, original_date="2026-08-21")
    records.update_day(
        season_id="S01",
        day_number=1,
        cutoff_at="2026-08-21T16:00:00+00:00",
        closed=True,
    )
    executor = _executor(
        database,
        ScriptedFakeClient(
            [
                ScriptedStream((
                    "<NARRATION>The House wakes. Mara runs to the blue door.</NARRATION>"
                    "<COMPLETE>false</COMPLETE>",
                )),
                ScriptedStream((
                    "<NARRATION>The House wakes around a newly humming blue door.</NARRATION>"
                    "<COMPLETE>false</COMPLETE>",
                )),
            ]
        ),
        tmp_path / "private" / "orchestrator",
        clock,
    )
    director = DailyDirector(
        season_id="S01",
        source_day_number=1,
        opening=OpeningSnapshot(set="House", setting="Night", cast=["Mara", "Nox"]),
        private_plan=HiddenSeasonPlan(hidden_mysteries=["private moon"]),
        orchestrator=executor,
        enforce_continuity=True,
    )

    result = asyncio.run(
        director.write_next_day(closed_diaries=("Mara remembers blue.",), day_is_closed=True)
    )

    assert "newly humming blue door" in open(result.content_path, encoding="utf-8").read()
    calls = database.connection.execute(
        "SELECT call_id,correction_of_call_id,acceptance_status,prompt_path "
        "FROM model_calls WHERE purpose LIKE 'next-day-direction:%' ORDER BY rowid"
    ).fetchall()
    assert len(calls) == 2
    assert calls[0]["acceptance_status"] == "REJECTED"
    assert calls[1]["acceptance_status"] == "ACCEPTED"
    assert calls[1]["correction_of_call_id"] == calls[0]["call_id"]
    correction_prompt = open(calls[1]["prompt_path"], encoding="utf-8").read()
    assert "discard the rejected narration" in correction_prompt
    assert "CAST NAMES TO EXCLUDE: Mara, Nox" in correction_prompt
