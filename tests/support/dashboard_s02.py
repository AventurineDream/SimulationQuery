"""Deterministic, production-isolated S02 evidence for dashboard rehearsal."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from improv_troupe.application import ServicePaths
from improv_troupe.domain import (
    CastMember,
    Diary,
    DiaryStatus,
    OpeningSnapshot,
    Publication,
    PublicationStatus,
    ScheduleSlot,
    Season,
    SeasonStatus,
)
from improv_troupe.infrastructure import (
    ModelCallRepository,
    RecordRepository,
    SQLiteDatabase,
    SeasonRepository,
)


PRODUCTION_DATA_ROOT = Path("/var/lib/improv-troupe").resolve()
FIXTURE_NOW = datetime(2026, 9, 7, 20, tzinfo=timezone.utc)


@dataclass(frozen=True)
class SyntheticDashboardFixture:
    """Handles for one isolated dashboard rehearsal database."""

    paths: ServicePaths
    database: SQLiteDatabase
    season_id: str = "S02"
    now: datetime = FIXTURE_NOW


def build_s02_dashboard_fixture(root: str | Path) -> SyntheticDashboardFixture:
    """Build healthy, partial, recovery, private, failed, and closed S02 states."""
    candidate = Path(root).expanduser().resolve(strict=False)
    _require_nonproduction_root(candidate)
    paths = ServicePaths.from_root(candidate)
    paths.prepare()
    database = SQLiteDatabase(paths.database_path)
    database.migrate()

    pacific = ZoneInfo("America/Los_Angeles")
    local_times = [
        datetime(2026, 9, 7, 6, tzinfo=pacific),
        datetime(2026, 9, 7, 12, tzinfo=pacific),
        datetime(2026, 9, 7, 18, tzinfo=pacific),
    ]
    schedule = [
        ScheduleSlot(
            slot_id=f"S02-run-{index:02d}",
            season_id="S02",
            day_number=1,
            slot_number=index,
            run_number=index,
            scheduled_local=local,
            scheduled_utc=local.astimezone(timezone.utc),
            utc_offset="-07:00",
        )
        for index, local in enumerate(local_times, start=1)
    ]
    cast = [
        CastMember(character_id="mara", name="Mara"),
        CastMember(character_id="tavi", name="Tavi", distress_signal_count=1),
        CastMember(character_id="oren", name="Oren"),
        CastMember(character_id="sable", name="Sable"),
    ]
    SeasonRepository(database).create(
        Season(
            season_id="S02",
            season_number=2,
            title="Weather Library",
            start_date=date(2026, 9, 7),
            idea="A library lends weather to a city that has forgotten the sky.",
            preflight_passed=True,
            status=SeasonStatus.RECOVERY_REQUIRED,
            opening=OpeningSnapshot(
                set="The weather returns desk",
                setting="A municipal library below a sealed observatory.",
                cast=[member.name for member in cast],
                world_rules=[
                    "Borrowed weather must be returned before midnight.",
                    "No forecast can name the person it is about.",
                ],
            ),
            cast=cast,
            schedule=schedule,
            auto_tap_out=False,
            version=6,
        ),
        now=datetime(2026, 9, 7, 12, tzinfo=timezone.utc),
    )

    with database.transaction() as connection:
        for version in (1, 2, 3):
            connection.execute(
                "INSERT INTO season_opening_versions(season_id, version, set_text, setting, "
                "cast_json, world_rules_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "S02", version, "The weather returns desk",
                    "A municipal library below a sealed observatory.",
                    json.dumps([member.name for member in cast]),
                    json.dumps([
                        "Borrowed weather must be returned before midnight.",
                        "No forecast can name the person it is about.",
                    ]),
                    f"2026-09-07T11:0{version}:00+00:00",
                ),
            )
        connection.execute(
            "INSERT INTO preparation_workspaces(season_id, version, idea, idea_version, "
            "opening_version, updated_at) VALUES ('S02', 5, ?, 2, 3, ?)",
            (
                "A library lends weather to a city that has forgotten the sky.",
                "2026-09-07T18:05:00+00:00",
            ),
        )
        cards = {
            "mara": ("Mara", "she / her", "Maintenance archivist who hears weather in the library walls before anyone else does.", ["Archive maintenance", "Acoustic diagnosis", "Repair"], ["Precise under pressure", "Names sensations first", "Dry, protective humor"], ["Never explains the joke"], "DRAFT", 4),
            "tavi": ("Tavi", "they / them", "Circulation clerk who remembers every borrower but distrusts every forecast.", ["Catalog systems", "Pattern recall"], ["Quiet confidence", "Asks one exact question"], ["Warms their hands on fog cards"], "APPROVED", 3),
            "oren": ("Oren", "he / him", "Municipal meteorologist assigned to audit weather that should not exist.", ["Forecasting", "Field instruments"], ["Earnest precision", "Admits uncertainty"], ["Folds receipts into birds"], "APPROVED", 2),
            "sable": ("Sable", "she / they", "Observatory caretaker who knows which sealed doors still breathe.", ["Mechanical access", "Night navigation"], ["Economical speech", "Unexpected warmth"], ["Counts stairs under their breath"], "APPROVED", 3),
        }
        connection.execute(
            "INSERT INTO character_card_versions(season_id, character_id, version, status, "
            "name, pronouns, public_brief, occupation_skills_json, voice_anchors_json, "
            "habits_json, derived_opening_version, created_at, approved_at) "
            "VALUES ('S02', 'mara', 3, 'APPROVED', 'Mara', 'she / her', ?, ?, ?, ?, 3, ?, ?)",
            (
                "Maintenance archivist who treats impossible weather as a repair queue.",
                json.dumps(["Archive maintenance", "Repair"]),
                json.dumps(["Precise under pressure", "Dry humor"]),
                json.dumps(["Labels every loose part"]),
                "2026-09-07T17:58:00+00:00", "2026-09-07T17:59:00+00:00",
            ),
        )
        for character_id, values in cards.items():
            name, pronouns, brief, skills, anchors, habits, status, version = values
            connection.execute(
                "INSERT INTO character_card_versions(season_id, character_id, version, status, "
                "name, pronouns, public_brief, occupation_skills_json, voice_anchors_json, "
                "habits_json, derived_opening_version, created_at, approved_at) "
                "VALUES ('S02', ?, ?, ?, ?, ?, ?, ?, ?, ?, 3, ?, ?)",
                (
                    character_id, version, status, name, pronouns, brief,
                    json.dumps(skills), json.dumps(anchors), json.dumps(habits),
                    "2026-09-07T18:02:00+00:00",
                    "2026-09-07T18:03:00+00:00" if status == "APPROVED" else None,
                ),
            )
            for artifact_kind, content in (
                (
                    "role_sheet",
                    {
                        "objectives": [f"Protect {name}'s private interpretation of the weather library."],
                        "boundaries": ["Do not narrate another character's private thoughts."],
                        "voice_guidance": anchors,
                    },
                ),
                (
                    "orientation",
                    {
                        "accepted": True,
                        "brief": f"{name} received the private rehearsal orientation.",
                        "wellness_signal_present": False,
                    },
                ),
            ):
                connection.execute(
                    "INSERT INTO private_preparation_versions(season_id, character_id, artifact_kind, "
                    "version, source_character_card_version, status, content_json, created_at) "
                    "VALUES ('S02', ?, ?, 1, ?, 'READY', ?, ?)",
                    (
                        character_id, artifact_kind, version, json.dumps(content),
                        "2026-09-07T18:04:30+00:00",
                    ),
                )
        connection.execute(
            "INSERT INTO model_assignment_versions(season_id, version, status, manifest_name, "
            "assignments_json, created_at) VALUES ('S02', 1, 'DRAFT', ?, ?, ?)",
            (
                "s02-rehearsal-manifest-v1",
                json.dumps({
                    "mara": "candidate-12b-a", "tavi": "candidate-8b-b",
                    "oren": "candidate-12b-a", "sable": "candidate-8b-b",
                    "orchestrator": "candidate-12b-director",
                }),
                "2026-09-07T18:04:00+00:00",
            ),
        )
        for step, workspace_version, detail in (
            ("idea", 2, {"idea_version": 2}),
            ("opening", 3, {"opening_version": 3}),
        ):
            connection.execute(
                "INSERT INTO preparation_receipts(receipt_id, season_id, step, workspace_version, "
                "status, detail_json, created_at) VALUES (?, 'S02', ?, ?, 'APPROVED', ?, ?)",
                (
                    f"S02:prepare:{step}:v{workspace_version}", step, workspace_version,
                    json.dumps(detail), "2026-09-07T18:05:00+00:00",
                ),
            )

    records = RecordRepository(database)
    records.insert_day(season_id="S02", day_number=1, original_date="2026-09-07")
    records.update_day(
        season_id="S02",
        day_number=1,
        cutoff_at="2026-09-07T20:00:00+00:00",
        closed=True,
    )
    records.insert_run(
        run_id="S02-run-01", season_id="S02", slot_id="S02-run-01", status="COMPLETED"
    )
    records.insert_run(
        run_id="S02-run-02",
        season_id="S02",
        slot_id="S02-run-02",
        status="RECOVERY_REQUIRED",
    )
    records.insert_run(
        run_id="S02-run-03", season_id="S02", slot_id="S02-run-03", status="QUEUED"
    )
    with database.transaction() as connection:
        connection.execute(
            "UPDATE runs SET turn_count = 16, completion_reason = ?, actual_started_at = ?, "
            "actual_completed_at = ?, delay = ?, version = 2 WHERE run_id = ?",
            (
                "four_round_complete",
                "2026-09-07T13:00:05+00:00",
                "2026-09-07T13:06:40+00:00",
                "ON_TIME",
                "S02-run-01",
            ),
        )
        connection.execute(
            "UPDATE runs SET turn_count = 3, completion_reason = ?, actual_started_at = ?, "
            "delay = ?, version = 2 WHERE run_id = ?",
            (
                "model_unavailable_after_partial_acceptance",
                "2026-09-07T19:00:10+00:00",
                "ON_TIME",
                "S02-run-02",
            ),
        )

    narration = _write_private(
        paths,
        "runs/S02-run-01/narration.md",
        "The returns desk opens an umbrella indoors, and rain climbs toward it.",
    )
    accepted_turn = _write_private(
        paths,
        "runs/S02-run-01/mara.md",
        "I stamp the thunder overdue before anyone can hear whose name it carries.",
    )
    partial_turn = _write_private(
        paths,
        "runs/S02-run-02/tavi.md",
        "The fog card is warm. I put it back without reading the borrower.",
    )
    records.insert_turn(
        turn_id="S02-run-01:stage:1",
        run_id="S02-run-01",
        round_number=1,
        character_id="stage",
        disposition="NARRATION_ACCEPT",
        content_path=str(narration),
        accepted_at="2026-09-07T13:00:30+00:00",
    )
    records.insert_turn(
        turn_id="S02-run-01:r1:mara",
        run_id="S02-run-01",
        round_number=1,
        character_id="mara",
        disposition="ACCEPT",
        content_path=str(accepted_turn),
        accepted_at="2026-09-07T13:01:00+00:00",
    )
    records.insert_turn(
        turn_id="S02-run-02:r1:tavi",
        run_id="S02-run-02",
        round_number=1,
        character_id="tavi",
        disposition="ACCEPT",
        content_path=str(partial_turn),
        accepted_at="2026-09-07T19:00:30+00:00",
    )

    mara_diary = _write_private(
        paths,
        "seasons/S02/day-01/diary/mara.md",
        "The rain climbed because none of us were ready to call it weather.",
    )
    oren_diary = _write_private(
        paths,
        "seasons/S02/day-01/diary/oren.md",
        "I returned the wind late and it kept one receipt.",
    )
    records.insert_diary(
        Diary(
            diary_id="S02:day:1:diary:mara",
            season_id="S02",
            character_id="mara",
            day_number=1,
            chosen_slot_number=1,
            status=DiaryStatus.WRITTEN,
            word_count=12,
            content_path=str(mara_diary),
        )
    )
    records.insert_diary(
        Diary(
            diary_id="S02:day:1:diary:tavi",
            season_id="S02",
            character_id="tavi",
            day_number=1,
            chosen_slot_number=2,
            status=DiaryStatus.PRIVATE,
        )
    )
    records.insert_diary(
        Diary(
            diary_id="S02:day:1:diary:oren",
            season_id="S02",
            character_id="oren",
            day_number=1,
            chosen_slot_number=1,
            status=DiaryStatus.LATE,
            word_count=10,
            late=True,
            content_path=str(oren_diary),
        )
    )
    records.insert_diary(
        Diary(
            diary_id="S02:day:1:diary:sable",
            season_id="S02",
            character_id="sable",
            day_number=1,
            status=DiaryStatus.MISSING,
        )
    )

    records.insert_recovery(
        recovery_id="S02-run-02:recovery:1",
        season_id="S02",
        run_id="S02-run-02",
        status="RECOVERY_REQUIRED",
        created_at="2026-09-07T19:02:00+00:00",
    )
    records.insert_notification(
        notification_id="S02:attention:run-02",
        kind="RECOVERY_REQUIRED",
        season_id="S02",
        payload={"run_id": "S02-run-02", "reason": "synthetic_model_timeout"},
    )
    records.insert_publication(
        Publication(
            publication_id="S02:publication:1",
            season_id="S02",
            version=1,
            status=PublicationStatus.PRIVATE,
            eligible_diary_ids=["S02:day:1:diary:mara", "S02:day:1:diary:oren"],
        )
    )
    with database.transaction() as connection:
        connection.execute(
            "UPDATE notifications SET created_at = ? WHERE notification_id = ?",
            ("2026-09-07T19:02:00+00:00", "S02:attention:run-02"),
        )
        connection.execute(
            "UPDATE publications SET created_at = ? WHERE publication_id = ?",
            ("2026-09-07T20:00:00+00:00", "S02:publication:1"),
        )

    calls = ModelCallRepository(database)
    accepted_output = _write_private(
        paths,
        "model-calls/S02-run-01-mara/output.md",
        "I stamp the thunder overdue before anyone can hear whose name it carries.",
    )
    calls.create(
        call_id="S02-run-01:mara:r1:a1",
        run_id="S02-run-01",
        purpose="actor:mara:round:1",
        attempt=1,
        status="STREAMING",
        backend="synthetic",
        model="fixture-healthy",
        started_at="2026-09-07T13:01:00+00:00",
        character_id="mara",
        response_format_mode="NATIVE_SCHEMA",
        prompt_version_id="scene-actor-v6",
        schema_version_id="actor-turn-v4",
        context_version_id="run-01-round-1-v2",
        role_sheet_version_id="mara-v1",
        character_card_version_id="mara-card-v1",
    )
    calls.finish(
        call_id="S02-run-01:mara:r1:a1",
        status="ACCEPTED",
        ended_at="2026-09-07T13:01:01+00:00",
        latency_ms=1000,
        output_path=str(accepted_output),
        finish_reason="stop",
        usage_json='{"total_tokens": 48}',
    )
    calls.record_diagnostics(
        call_id="S02-run-01:mara:r1:a1",
        parse_status="PARSED",
        validation_status="PASSED",
        acceptance_status="ACCEPTED",
        render_status="RENDERED",
        parsed_path=str(accepted_output),
        validated_path=str(accepted_output),
        accepted_path=str(accepted_output),
        rendered_path=str(accepted_turn),
        review_turn_id="S02-run-01:r1:mara",
    )
    failed_output = _write_private(
        paths,
        "model-calls/S02-run-02-tavi/output.partial.md",
        "The fog card is warm—",
    )
    calls.create(
        call_id="S02-run-02:tavi:r1:a1",
        run_id="S02-run-02",
        purpose="actor:tavi:round:1",
        attempt=1,
        status="STREAMING",
        backend="synthetic",
        model="fixture-failing",
        started_at="2026-09-07T19:01:00+00:00",
        character_id="tavi",
        response_format_mode="TAGGED_FALLBACK",
        prompt_version_id="scene-actor-v6",
        schema_version_id="actor-turn-v4",
        context_version_id="run-02-round-1-v2",
        role_sheet_version_id="tavi-v1",
        character_card_version_id="tavi-card-v1",
    )
    calls.finish(
        call_id="S02-run-02:tavi:r1:a1",
        status="RETRYABLE_FAILURE",
        ended_at="2026-09-07T19:01:30+00:00",
        latency_ms=30000,
        output_path=str(failed_output),
        finish_reason="timeout",
        error_type="SyntheticTimeout",
        usage_json='{"total_tokens": 12}',
    )
    calls.record_diagnostics(
        call_id="S02-run-02:tavi:r1:a1",
        parse_status="NOT_REACHED",
        validation_status="NOT_REACHED",
        acceptance_status="NOT_REACHED",
        render_status="NOT_REACHED",
    )

    invalid_output = _write_private(
        paths,
        "model-calls/S02-run-02-director-invalid/output.md",
        '{"narration":"The archive lights dim.","state_changes":"corridor sealed"}',
    )
    calls.create(
        call_id="S02-run-02:director:r4:a1",
        run_id="S02-run-02",
        purpose="orchestrator:round:4",
        attempt=1,
        status="COMPLETED",
        backend="synthetic",
        model="fixture-schema-failure",
        started_at="2026-09-07T19:01:40+00:00",
        character_id="stage",
        response_format_mode="NATIVE_SCHEMA",
        prompt_version_id="scene-director-v6",
        schema_version_id="director-beat-v4",
        context_version_id="run-02-round-4-v15",
        role_sheet_version_id="director-v2",
    )
    calls.finish(
        call_id="S02-run-02:director:r4:a1",
        status="COMPLETED",
        ended_at="2026-09-07T19:02:22.800000+00:00",
        latency_ms=42800,
        output_path=str(invalid_output),
        finish_reason="stop",
        usage_json='{"total_tokens": 1462}',
    )
    calls.record_diagnostics(
        call_id="S02-run-02:director:r4:a1",
        parse_status="PARSED",
        validation_status="FAILED",
        acceptance_status="REJECTED",
        render_status="NOT_RENDERED",
        parsed_path=str(invalid_output),
        validator_code="schema_failure.state_changes",
        validator_detail="Expected array; received string.",
    )

    malformed_output = _write_private(
        paths,
        "model-calls/S02-run-02-oren-malformed/output.md",
        "<ACTOR_TEXT>The barometer remembers",
    )
    calls.create(
        call_id="S02-run-02:oren:r1:a1",
        run_id="S02-run-02",
        purpose="actor_turn:oren:round:1",
        attempt=1,
        status="COMPLETED",
        backend="synthetic",
        model="fixture-parse-failure",
        started_at="2026-09-07T19:00:40+00:00",
        character_id="oren",
        response_format_mode="TAGGED_FALLBACK",
        prompt_version_id="scene-actor-v6",
        schema_version_id="actor-turn-v4",
        context_version_id="run-02-round-1-v2",
        role_sheet_version_id="oren-v1",
        character_card_version_id="oren-card-v1",
    )
    calls.finish(
        call_id="S02-run-02:oren:r1:a1",
        status="COMPLETED",
        ended_at="2026-09-07T19:00:41+00:00",
        latency_ms=1000,
        output_path=str(malformed_output),
        finish_reason="stop",
    )
    calls.record_diagnostics(
        call_id="S02-run-02:oren:r1:a1",
        parse_status="FAILED",
        validation_status="NOT_REACHED",
        acceptance_status="NOT_REACHED",
        render_status="NOT_REACHED",
        validator_code="parse_failure",
        validator_detail="Response was neither valid JSON nor a complete strict tagged envelope.",
    )
    private_output = _write_private(
        paths,
        "model-calls/S02-tavi-diary/output.md",
        "<DIARY_SLOT>2</DIARY_SLOT><WRITE_NOW>true</WRITE_NOW>"
        "<DIARY_TEXT>The fog knew which shelf I was avoiding.</DIARY_TEXT>"
        "<EVIDENCE_REFS>1</EVIDENCE_REFS>"
        "<WELLNESS_SIGNAL>Keep this attempt private.</WELLNESS_SIGNAL>",
    )
    calls.create(
        call_id="S02:diary:tavi:day:1:slot:2:a1",
        run_id=None,
        purpose="diary:S02:tavi:day:1:slot:2",
        attempt=1,
        status="STREAMING",
        backend="synthetic",
        model="fixture-private",
        started_at="2026-09-07T19:30:00+00:00",
    )
    calls.finish(
        call_id="S02:diary:tavi:day:1:slot:2:a1",
        status="MANUAL_REVIEW",
        ended_at="2026-09-07T19:30:02+00:00",
        latency_ms=2000,
        output_path=str(private_output),
        finish_reason="stop",
        usage_json='{"total_tokens": 36}',
    )

    return SyntheticDashboardFixture(paths=paths, database=database)


def set_s02_live_running(fixture: SyntheticDashboardFixture) -> SyntheticDashboardFixture:
    """Convert a fresh recovery fixture into a healthy, leased Live rehearsal."""
    database = fixture.database
    with database.transaction() as connection:
        connection.execute(
            "UPDATE seasons SET status = 'RUNNING', updated_at = ? WHERE season_id = 'S02'",
            (fixture.now.isoformat(),),
        )
        connection.execute(
            "UPDATE runs SET status = 'RUNNING', completion_reason = NULL "
            "WHERE run_id = 'S02-run-02'"
        )
        connection.execute(
            "UPDATE recovery_requests SET status = 'SUPERSEDED', resolved_at = ?, version = version + 1 "
            "WHERE recovery_id = 'S02-run-02:recovery:1'",
            (fixture.now.isoformat(),),
        )
        connection.execute(
            "UPDATE notifications SET read_at = ? WHERE notification_id = 'S02:attention:run-02'",
            (fixture.now.isoformat(),),
        )
        connection.execute(
            "UPDATE days SET closed = 0, cutoff_at = NULL WHERE season_id = 'S02' AND day_number = 1"
        )
        connection.execute(
            "INSERT INTO work_items(work_id, natural_key, kind, payload_json, status, available_at, "
            "lease_owner, lease_until, attempts, priority) VALUES (?, ?, 'RUN_SCENE', ?, 'LEASED', ?, ?, ?, 1, 2)",
            (
                "live:S02-run-02", "live:S02-run-02",
                json.dumps({"season_id": "S02", "run_id": "S02-run-02"}),
                "2026-09-07T19:59:30+00:00", "fixture-worker",
                "2026-09-07T20:05:00+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO work_items(work_id, natural_key, kind, payload_json, status, available_at, "
            "attempts, priority) VALUES (?, ?, 'RUN_SCENE', ?, 'QUEUED', ?, 0, 3)",
            (
                "work:S02-run-03", "run:S02-run-03",
                json.dumps({"season_id": "S02", "run_id": "S02-run-03"}),
                "2026-09-08T01:00:00+00:00",
            ),
        )
    ModelCallRepository(database).create(
        call_id="S02-run-02:mara:r2:a1", run_id="S02-run-02",
        purpose="actor:mara:round:2", attempt=1, status="STREAMING",
        backend="synthetic", model="fixture-running",
        started_at="2026-09-07T19:59:42+00:00", character_id="mara",
        response_format_mode="NATIVE_SCHEMA", prompt_version_id="scene-actor-v6",
        schema_version_id="actor-turn-v4", context_version_id="run-02-round-2-v3",
        role_sheet_version_id="mara-v1", character_card_version_id="mara-card-v3",
    )
    return fixture


def _write_private(paths: ServicePaths, relative: str, content: str) -> Path:
    target = paths.roots.prepare_file_parent("private", relative)
    target.write_text(content, encoding="utf-8")
    return target


def _require_nonproduction_root(candidate: Path) -> None:
    if (
        candidate == PRODUCTION_DATA_ROOT
        or PRODUCTION_DATA_ROOT in candidate.parents
        or candidate in PRODUCTION_DATA_ROOT.parents
    ):
        raise ValueError(
            "synthetic dashboard fixtures cannot use or contain the production data root"
        )
