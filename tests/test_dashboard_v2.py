import io
import json
from datetime import timedelta
from urllib.parse import urlencode

import pytest

from improv_troupe.application import ServicePaths
from improv_troupe.clock import VirtualClock
from improv_troupe.domain import Season, SeasonStatus
from improv_troupe.infrastructure import RecordRepository, SeasonRepository
from improv_troupe.web.dashboard import DashboardApplication, DashboardConfig, hash_password
from tests.support import build_s02_dashboard_fixture, set_s02_live_running


def _call(app, path, *, method="GET", body=b"", headers=None):
    captured = {}
    request = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path.split("?", 1)[0],
        "QUERY_STRING": path.split("?", 1)[1] if "?" in path else "",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
        "wsgi.url_scheme": "http",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "8765",
        "SCRIPT_NAME": "",
        "SERVER_PROTOCOL": "HTTP/1.1",
    }
    request.update(headers or {})

    def start_response(status, response_headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = response_headers

    content = b"".join(app(request, start_response))
    return captured["status"], dict(captured["headers"]), content


def _authenticated_fixture(tmp_path):
    fixture = build_s02_dashboard_fixture(tmp_path / "dashboard-s02")
    app = DashboardApplication(
        DashboardConfig(
            paths=fixture.paths,
            username="owner",
            password_hash=hash_password("secret", salt=b"0123456789abcdef"),
            enable_v2=True,
            environment="sandbox",
        ),
        clock=VirtualClock(fixture.now),
    )
    status, headers, _ = _call(
        app,
        "/login",
        method="POST",
        body=urlencode({"username": "owner", "password": "secret"}).encode(),
        headers={"CONTENT_TYPE": "application/x-www-form-urlencoded"},
    )
    assert status.startswith("303")
    return fixture, app, headers["Set-Cookie"].split(";", 1)[0]


def _authenticated_running_fixture(tmp_path):
    fixture = set_s02_live_running(build_s02_dashboard_fixture(tmp_path / "dashboard-s02-running"))
    app = DashboardApplication(
        DashboardConfig(
            paths=fixture.paths, username="owner",
            password_hash=hash_password("secret", salt=b"0123456789abcdef"),
            enable_v2=True, environment="sandbox",
        ),
        clock=VirtualClock(fixture.now),
    )
    status, headers, _ = _call(
        app, "/login", method="POST",
        body=urlencode({"username": "owner", "password": "secret"}).encode(),
        headers={"CONTENT_TYPE": "application/x-www-form-urlencoded"},
    )
    assert status.startswith("303")
    return fixture, app, headers["Set-Cookie"].split(";", 1)[0]


def _csrf(app, cookie):
    session = app.auth.session(cookie.split("=", 1)[1])
    assert session is not None
    return session[1]


def _prepare_action(app, cookie, csrf, *, request_id, action, expected_version, **extra):
    payload = {
        "request_id": request_id,
        "season_id": "S02",
        "action": action,
        "expected_version": expected_version,
        **extra,
    }
    return _call(
        app,
        "/api/v2/prepare/action",
        method="POST",
        body=json.dumps(payload).encode("utf-8"),
        headers={
            "HTTP_COOKIE": cookie,
            "HTTP_X_CSRF_TOKEN": csrf,
            "CONTENT_TYPE": "application/json",
        },
    )


def _live_action(app, cookie, csrf, review, *, request_id, **extra):
    snapshot = review["snapshot"]
    payload = {
        "request_id": request_id,
        "season_id": snapshot["season_id"],
        "action": review["action"],
        "snapshot_hash": review["snapshot_hash"],
        "expected_season_version": snapshot["season_version"],
        "expected_run_version": snapshot["run_version"],
        "expected_recovery_version": snapshot["recovery_version"],
        **extra,
    }
    return _call(
        app, "/api/v2/live/action", method="POST",
        body=json.dumps(payload).encode("utf-8"),
        headers={
            "HTTP_COOKIE": cookie, "HTTP_X_CSRF_TOKEN": csrf,
            "CONTENT_TYPE": "application/json",
        },
    )


def _seasons_action(app, cookie, csrf, path, payload):
    return _call(
        app, path, method="POST", body=json.dumps(payload).encode("utf-8"),
        headers={
            "HTTP_COOKIE": cookie, "HTTP_X_CSRF_TOKEN": csrf,
            "CONTENT_TYPE": "application/json",
        },
    )


def test_v2_seasons_private_close_is_read_only_until_a_versioned_typed_post(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    before = fixture.database.connection.total_changes
    status, _, body = _call(app, "/api/v2/seasons?season_id=S02", headers={"HTTP_COOKIE": cookie})
    assert status.startswith("200")
    review = json.loads(body)
    assert review["mode"] == "private-close"
    assert review["executable"] is True
    assert review["snapshot"]["private_archive_sha256"]
    assert fixture.database.connection.total_changes == before

    status, _, page = _call(app, "/v2/seasons?season_id=S02", headers={"HTTP_COOKIE": cookie})
    assert status.startswith("200")
    assert b"Preserve before release" in page
    assert b"/api/publish" not in page

    csrf = _csrf(app, cookie)
    payload = {
        "request_id": "seasons-close-001", "season_id": "S02",
        "snapshot_hash": review["snapshot_hash"],
        "expected_season_version": review["snapshot"]["season_version"],
        "typed_confirmation": review["typed_confirmation"],
    }
    status, _, result_body = _seasons_action(app, cookie, csrf, "/api/v2/seasons/private-close", payload)
    assert status.startswith("200")
    result = json.loads(result_body)
    assert result["status"] == "PRIVATE_COMPLETE"
    assert result["handoff"]["status"] == "VERIFIED"
    assert result["private_archive_sha256"] == review["snapshot"]["private_archive_sha256"]

    status, _, replay_body = _seasons_action(app, cookie, csrf, "/api/v2/seasons/private-close", payload)
    assert status.startswith("200")
    assert json.loads(replay_body)["replayed"] is True


def test_v2_seasons_publication_requires_private_complete_and_stays_sandbox_only(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    csrf = _csrf(app, cookie)
    status, _, body = _seasons_action(
        app, cookie, csrf, "/api/v2/seasons/publication-preview",
        {"season_id": "S02", "diary_decisions": {}},
    )
    assert status.startswith("400")
    assert b"PRIVATE_COMPLETE" in body

    status, _, close_body = _call(app, "/api/v2/seasons?season_id=S02", headers={"HTTP_COOKIE": cookie})
    close = json.loads(close_body)
    status, _, _ = _seasons_action(
        app, cookie, csrf, "/api/v2/seasons/private-close",
        {"request_id": "seasons-close-publication", "season_id": "S02", "snapshot_hash": close["snapshot_hash"], "expected_season_version": close["snapshot"]["season_version"], "typed_confirmation": close["typed_confirmation"]},
    )
    assert status.startswith("200")
    status, _, preview_body = _seasons_action(
        app, cookie, csrf, "/api/v2/seasons/publication-preview",
        {"season_id": "S02", "diary_decisions": {}},
    )
    assert status.startswith("200")
    preview = json.loads(preview_body)
    assert preview["snapshot"]["publication_eligible"] is False
    assert not preview["preview"]["diaries"]
    assert b"role_sheet" not in preview_body

    status, _, s01_body = _seasons_action(
        app, cookie, csrf, "/api/v2/seasons/private-close",
        {"request_id": "no-s01", "season_id": "S01", "snapshot_hash": "x", "expected_season_version": 1, "typed_confirmation": "end S01 privately"},
    )
    assert status.startswith("400")
    assert b"cannot target S01" in s01_body

    production = DashboardApplication(
        DashboardConfig(paths=fixture.paths, username="owner", password_hash=hash_password("secret", salt=b"0123456789abcdef"), enable_v2=True, environment="production"),
        clock=VirtualClock(fixture.now),
    )
    status, headers, _ = _call(
        production, "/login", method="POST", body=urlencode({"username": "owner", "password": "secret"}).encode(),
        headers={"CONTENT_TYPE": "application/x-www-form-urlencoded"},
    )
    assert status.startswith("303")
    production_cookie = headers["Set-Cookie"].split(";", 1)[0]
    status, _, production_body = _seasons_action(
        production, production_cookie, _csrf(production, production_cookie), "/api/v2/seasons/private-close",
        {"request_id": "prod-close", "season_id": "S02", "snapshot_hash": "x", "expected_season_version": 1, "typed_confirmation": "end S02 privately"},
    )
    assert status.startswith("400")
    assert b"sandbox-only" in production_body


def test_v2_live_projects_safe_recovery_and_deliberate_accepted_transcript(tmp_path):
    _, app, cookie = _authenticated_fixture(tmp_path)
    status, _, body = _call(app, "/api/v2/live?season_id=S02", headers={"HTTP_COOKIE": cookie})
    assert status.startswith("200")
    data = json.loads(body)["data"]
    assert data["lifecycle"]["status"] == "RECOVERY_REQUIRED"
    assert data["run"]["run_id"] == "S02-run-02"
    assert data["run"]["version"] == 2
    assert data["run"]["accepted_count"] == 1
    assert data["recovery"]["version"] == 1
    assert data["recovery"]["selected_action"] is None
    assert data["recovery"]["actions"] == ["retry", "skip", "private_close"]
    assert "output.partial.md" not in body.decode("utf-8")

    status, _, transcript_body = _call(
        app, data["transcript_href"], headers={"HTTP_COOKIE": cookie}
    )
    assert status.startswith("200")
    transcript = json.loads(transcript_body)["data"]
    assert transcript["accepted_count"] == 1
    assert [record["turn_id"] for record in transcript["records"]] == ["S02-run-02:r1:tavi"]
    assert "malformed" not in transcript_body.decode("utf-8").lower()

    page_status, _, page_body = _call(
        app, "/v2/live?season_id=S02", headers={"HTTP_COOKIE": cookie}
    )
    assert page_status.startswith("200")
    assert b"Performance supervision" in page_body
    assert b"Live is not implemented" not in page_body


def test_v2_live_retry_is_review_bound_prioritized_and_idempotent(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    csrf = _csrf(app, cookie)
    status, _, body = _call(
        app, "/api/v2/live/impact-review?season_id=S02&action=retry",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    review = json.loads(body)
    assert review["snapshot"]["season_version"] == 6
    assert review["snapshot"]["run_version"] == 2
    assert review["snapshot"]["recovery_version"] == 1
    assert review["executable"] is True

    _, _, skip_review_body = _call(
        app, "/api/v2/live/impact-review?season_id=S02&action=skip",
        headers={"HTTP_COOKIE": cookie},
    )
    skip_review = json.loads(skip_review_body)
    first_status, _, first_body = _live_action(
        app, cookie, csrf, review, request_id="dash05-retry"
    )
    assert first_status.startswith("200")
    assert json.loads(first_body)["replayed"] is False
    second_status, _, second_body = _live_action(
        app, cookie, csrf, review, request_id="dash05-retry"
    )
    assert second_status.startswith("200")
    assert json.loads(second_body)["replayed"] is True
    conflict_status, _, conflict_body = _live_action(
        app, cookie, csrf, skip_review, request_id="dash05-retry",
        typed_confirmation=skip_review["typed_confirmation"],
    )
    assert conflict_status.startswith("400")
    assert "different intent" in json.loads(conflict_body)["error"]
    connection = fixture.database.connection
    run = connection.execute("SELECT status, version FROM runs WHERE run_id = 'S02-run-02'").fetchone()
    assert (run["status"], run["version"]) == ("QUEUED", 3)
    recovery = connection.execute(
        "SELECT status, version FROM recovery_requests WHERE recovery_id = 'S02-run-02:recovery:1'"
    ).fetchone()
    assert (recovery["status"], recovery["version"]) == ("RETRY", 2)
    work = connection.execute(
        "SELECT priority FROM work_items WHERE natural_key = 'retry:S02-run-02:dash05-retry'"
    ).fetchone()
    assert work is not None and work["priority"] == -100


def test_v2_live_skip_requires_typed_confirmation_and_stale_reviews_fail_closed(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    csrf = _csrf(app, cookie)
    _, _, body = _call(
        app, "/api/v2/live/impact-review?season_id=S02&action=skip",
        headers={"HTTP_COOKIE": cookie},
    )
    review = json.loads(body)
    status, _, rejected = _live_action(
        app, cookie, csrf, review, request_id="dash05-skip-wrong", typed_confirmation="skip"
    )
    assert status.startswith("400")
    assert "typed confirmation" in json.loads(rejected)["error"]

    with fixture.database.transaction() as connection:
        connection.execute("UPDATE seasons SET version = version + 1 WHERE season_id = 'S02'")
    status, _, rejected = _live_action(
        app, cookie, csrf, review, request_id="dash05-skip-stale",
        typed_confirmation=review["typed_confirmation"],
    )
    assert status.startswith("400")
    assert "stale" in json.loads(rejected)["error"]
    run = fixture.database.connection.execute(
        "SELECT status FROM runs WHERE run_id = 'S02-run-02'"
    ).fetchone()
    assert run["status"] == "RECOVERY_REQUIRED"


def test_v2_live_private_close_is_a_nonexecuting_route(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    status, _, body = _call(
        app, "/api/v2/live/impact-review?season_id=S02&action=private_close",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    review = json.loads(body)
    assert review["executable"] is False
    assert review["private_close_href"].startswith("/v2/seasons?")
    assert fixture.database.connection.execute(
        "SELECT status FROM seasons WHERE season_id = 'S02'"
    ).fetchone()["status"] == "RECOVERY_REQUIRED"


def test_v2_live_healthy_polling_is_read_only_and_pause_resume_are_reviewed(tmp_path):
    fixture, app, cookie = _authenticated_running_fixture(tmp_path)
    csrf = _csrf(app, cookie)
    before = fixture.database.connection.total_changes
    for _ in range(2):
        status, _, body = _call(
            app, "/api/v2/live?season_id=S02", headers={"HTTP_COOKIE": cookie}
        )
        assert status.startswith("200")
    data = json.loads(body)["data"]
    assert data["lifecycle"]["status"] == "RUNNING"
    assert data["worker"]["state"] == "active_lease"
    assert data["active_work"]["work_id"] == "live:S02-run-02"
    assert data["run"]["call"]["status"] == "STREAMING"
    assert data["recovery"] is None
    assert fixture.database.connection.total_changes == before

    _, _, pause_body = _call(
        app, "/api/v2/live/impact-review?season_id=S02&action=pause",
        headers={"HTTP_COOKIE": cookie},
    )
    pause_review = json.loads(pause_body)
    status, _, receipt_body = _live_action(
        app, cookie, csrf, pause_review, request_id="dash05-pause"
    )
    assert status.startswith("200")
    assert json.loads(receipt_body)["action"] == "pause"
    assert fixture.database.connection.execute(
        "SELECT status FROM seasons WHERE season_id = 'S02'"
    ).fetchone()["status"] == "PAUSED"

    _, _, resume_body = _call(
        app, "/api/v2/live/impact-review?season_id=S02&action=resume",
        headers={"HTTP_COOKIE": cookie},
    )
    resume_review = json.loads(resume_body)
    status, _, _ = _live_action(
        app, cookie, csrf, resume_review, request_id="dash05-resume"
    )
    assert status.startswith("200")
    assert fixture.database.connection.execute(
        "SELECT status FROM seasons WHERE season_id = 'S02'"
    ).fetchone()["status"] == "RUNNING"


def test_v2_home_projects_truth_without_private_or_model_leakage(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)

    status, _, body = _call(
        app,
        "/api/v2/home?season_id=S02",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    payload = json.loads(body)

    assert payload["meta"] == {
        "checked_at": "2026-09-07T20:00:00Z",
        "contract_version": 1,
        "environment": "sandbox",
        "freshness": "partial",
        "season_id": "S02",
        "season_version": 6,
    }
    home = payload["data"]
    assert home["state"] == "ready"
    assert home["lifecycle"]["status"] == "RECOVERY_REQUIRED"
    assert home["attention"]["count"] == 1
    assert home["attention"]["highest_priority"]["kind"] == "recovery"
    assert home["progress"] == {
        "completed": 1,
        "days_closed": 1,
        "days_scheduled": 1,
        "resolved": 1,
        "scheduled": 3,
        "skipped": 0,
        "unresolved": 2,
    }
    assert home["day_completion"]["state"] == "closed_with_unresolved"
    assert home["day_completion"]["complete"] is False
    assert home["worker"] == {
        "active_leases": 0,
        "expired_leases": 0,
        "label": "No active lease observed",
        "queue_due": 0,
        "queue_total": 0,
        "state": "no_active_lease",
    }
    assert home["health"]["database_integrity"] == "ok"
    assert home["health"]["model_availability"] == "not_probed"
    assert home["last_accepted_beat"]["excerpt"].startswith("The fog card is warm.")
    assert home["last_accepted_beat"]["accepted_at"] == "2026-09-07T19:00:30Z"
    assert "Derived order" in home["last_accepted_beat"]["evidence_basis"]
    assert home["next_slot"]["run_id"] == "S02-run-02"

    raw = body.decode("utf-8")
    for forbidden in (
        str(fixture.paths.data_root),
        str(fixture.paths.roots.private),
        "fixture-healthy",
        "fixture-failing",
        "fixture-private",
        "Keep this attempt private",
        "synthetic_model_timeout",
        "prompt_path",
        "content_path",
    ):
        assert forbidden not in raw


def test_v2_day_review_is_causal_and_omits_private_diary_attempts(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)

    status, _, body = _call(
        app,
        "/api/v2/review/day?season_id=S02&day=1&run_id=S02-run-01",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    payload = json.loads(body)
    review = payload["data"]

    assert review["day"] == {
        "closed": True,
        "cutoff_at": "2026-09-07T20:00:00Z",
        "day_number": 1,
        "evidence_notes": [
            "The day is marked closed while one or more scheduled runs remain unresolved."
        ],
        "evidence_state": "partial",
        "original_date": "2026-09-07",
        "resolved_runs": 1,
        "scheduled_runs": 3,
    }
    assert review["selected_run_id"] == "S02-run-01"
    normal = review["runs"][0]
    assert normal["status"] == "COMPLETED"
    assert normal["completion_reason"] == "four_round_complete"
    assert normal["completion_evidence"] == "confirmed"
    assert normal["order_evidence"] == "persisted"
    assert [record["kind"] for record in normal["records"]] == [
        "director_beat",
        "actor_turn",
    ]
    assert normal["records"][1]["caused_by_turn_id"] == normal["records"][0]["turn_id"]
    assert normal["fiction_clock"] == {
        "basis": "schedule_derived",
        "day_number": 1,
        "label": "Day 1, morning",
        "slot_number": 1,
    }

    partial = review["runs"][1]
    assert partial["status"] == "RECOVERY_REQUIRED"
    assert partial["completion_reason"] == "model_unavailable_after_partial_acceptance"
    assert partial["order_evidence"] == "derived"
    assert partial["records"][0]["sequence_source"] == "derived"
    assert review["diary_counts"] == {
        "LATE": 1,
        "MISSING": 1,
        "PRIVATE": 1,
        "WRITTEN": 1,
    }
    assert all("content" not in diary for diary in review["diaries"])
    assert review["cast"][0] == {
        "character_card_version": 3,
        "character_id": "mara",
        "habits": ["Labels every loose part"],
        "memory_href": (
            "/v2/review?season_id=S02&day=1&tab=cast&character_id=mara&"
            "run_id=S02-run-01"
        ),
        "memory_version": 0,
        "name": "Mara",
        "occupation_skills": ["Archive maintenance", "Repair"],
        "pronouns": "she / her",
        "public_brief": "Maintenance archivist who treats impossible weather as a repair queue.",
        "status": "ACTIVE",
        "voice_anchors": ["Precise under pressure", "Dry humor"],
    }
    assert review["continuity"]["unresolved_state"] == "unavailable"

    raw = body.decode("utf-8")
    for forbidden in (
        "The fog knew which shelf I was avoiding.",
        "Keep this attempt private.",
        "fixture-private",
        "fixture-healthy",
        "output_path",
        "content_path",
        str(fixture.paths.roots.private),
    ):
        assert forbidden not in raw


def test_v2_diary_disclosure_is_deliberate_sanitized_and_read_only(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    connection = fixture.database.connection
    before = {
        "diary": tuple(
            connection.execute(
                "SELECT status, content_path, word_count, late FROM diaries "
                "WHERE diary_id = 'S02:day:1:diary:tavi'"
            ).fetchone()
        ),
        "canon": connection.execute("SELECT COUNT(*) FROM canon_entries").fetchone()[0],
        "wellness": connection.execute("SELECT COUNT(*) FROM wellness_events").fetchone()[0],
        "publication": tuple(
            connection.execute(
                "SELECT status, eligible_diary_ids_json FROM publications "
                "WHERE publication_id = 'S02:publication:1'"
            ).fetchone()
        ),
    }

    status, _, body = _call(
        app,
        "/api/v2/review/diary-attempt?season_id=S02&"
        "diary_id=S02%3Aday%3A1%3Adiary%3Atavi",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    disclosure = json.loads(body)["data"]
    assert disclosure == {
        "attempt_number": 1,
        "character_id": "tavi",
        "character_name": "Tavi",
        "content": "The fog knew which shelf I was avoiding.",
        "day_number": 1,
        "diary_id": "S02:day:1:diary:tavi",
        "evidence_note": (
            "Diary text was safely separated from a held private attempt; "
            "wellness wording remains undisclosed."
        ),
        "immutable_read": True,
        "season_id": "S02",
        "source": "private_attempt",
        "status": "PRIVATE",
        "wellness_signal_present": True,
    }
    assert "Keep this attempt private." not in body.decode("utf-8")
    assert "WELLNESS_SIGNAL" not in body.decode("utf-8")

    after = {
        "diary": tuple(
            connection.execute(
                "SELECT status, content_path, word_count, late FROM diaries "
                "WHERE diary_id = 'S02:day:1:diary:tavi'"
            ).fetchone()
        ),
        "canon": connection.execute("SELECT COUNT(*) FROM canon_entries").fetchone()[0],
        "wellness": connection.execute("SELECT COUNT(*) FROM wellness_events").fetchone()[0],
        "publication": tuple(
            connection.execute(
                "SELECT status, eligible_diary_ids_json FROM publications "
                "WHERE publication_id = 'S02:publication:1'"
            ).fetchone()
        ),
    }
    assert after == before


def test_v2_diary_disclosure_fails_closed_on_private_path_escape(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    escaped = tmp_path / "outside-diary-attempt.txt"
    escaped.write_text(
        "private diary body <WELLNESS_SIGNAL>raw wellness wording</WELLNESS_SIGNAL>",
        encoding="utf-8",
    )
    with fixture.database.transaction() as connection:
        connection.execute(
            "UPDATE model_calls SET output_path = ? "
            "WHERE call_id = 'S02:diary:tavi:day:1:slot:2:a1'",
            (str(escaped),),
        )

    status, _, body = _call(
        app,
        "/api/v2/review/diary-attempt?season_id=S02&"
        "diary_id=S02%3Aday%3A1%3Adiary%3Atavi",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    payload = json.loads(body)
    assert payload["meta"]["freshness"] == "partial"
    assert payload["data"]["source"] == "unavailable"
    assert payload["data"]["content"] is None
    raw = body.decode("utf-8")
    assert str(escaped) not in raw
    assert "raw wellness wording" not in raw
    assert "private diary body" not in raw


def test_v2_review_orders_legacy_turns_director_first_and_labels_derivation(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    with fixture.database.transaction() as connection:
        connection.execute(
            "UPDATE turns SET accepted_sequence = NULL, caused_by_turn_id = NULL, "
            "accepted_at = NULL WHERE run_id = 'S02-run-01'"
        )

    status, _, body = _call(
        app,
        "/api/v2/review/day?season_id=S02&day=1&run_id=S02-run-01",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    run = json.loads(body)["data"]["runs"][0]
    assert run["order_evidence"] == "derived"
    assert [record["kind"] for record in run["records"]] == [
        "director_beat",
        "actor_turn",
    ]
    assert all(record["sequence_source"] == "derived" for record in run["records"])
    assert "Legacy or incomplete evidence" in run["order_explanation"]


def test_v2_review_preserves_corrected_and_recovered_acceptance_evidence(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    records = RecordRepository(fixture.database)
    corrected = fixture.paths.roots.prepare_file_parent(
        "private", "runs/S02-run-01/tavi-corrected.md"
    )
    corrected.write_text("I return the fog card face down, after checking its seal.", encoding="utf-8")
    records.insert_turn(
        turn_id="S02-run-01:r1:tavi",
        run_id="S02-run-01",
        round_number=1,
        character_id="tavi",
        disposition="ACCEPT_AFTER_CORRECTION",
        content_path=str(corrected),
        accepted_at="2026-09-07T13:01:30+00:00",
    )

    recovered_stage = fixture.paths.roots.prepare_file_parent(
        "private", "runs/S02-run-02/narration.md"
    )
    recovered_stage.write_text(
        "The fog drawer catches, then opens on its second attempt.", encoding="utf-8"
    )
    records.insert_turn(
        turn_id="S02-run-02:stage:1",
        run_id="S02-run-02",
        round_number=1,
        character_id="stage",
        disposition="NARRATION_ACCEPT",
        content_path=str(recovered_stage),
        accepted_at="2026-09-07T19:00:20+00:00",
    )
    with fixture.database.transaction() as connection:
        connection.execute(
            "UPDATE turns SET accepted_sequence = NULL "
            "WHERE turn_id = 'S02-run-02:r1:tavi'"
        )
        connection.execute(
            "UPDATE turns SET accepted_sequence = 1 "
            "WHERE turn_id = 'S02-run-02:stage:1'"
        )
        connection.execute(
            "UPDATE turns SET accepted_sequence = 2, caused_by_turn_id = 'S02-run-02:stage:1' "
            "WHERE turn_id = 'S02-run-02:r1:tavi'"
        )
        connection.execute(
            "UPDATE runs SET status = 'COMPLETED', completion_reason = 'recovered_after_retry', "
            "actual_completed_at = '2026-09-07T19:04:00+00:00' "
            "WHERE run_id = 'S02-run-02'"
        )

    status, _, body = _call(
        app,
        "/api/v2/review/day?season_id=S02&day=1&run_id=S02-run-02",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    runs = json.loads(body)["data"]["runs"]
    normal = runs[0]
    recovered = runs[1]
    corrected_record = next(
        record for record in normal["records"] if record["character_id"] == "tavi"
    )
    assert corrected_record["disposition"] == "ACCEPT_AFTER_CORRECTION"
    assert corrected_record["caused_by_turn_id"] == "S02-run-01:stage:1"
    assert normal["order_evidence"] == "persisted"
    assert recovered["status"] == "COMPLETED"
    assert recovered["completion_reason"] == "recovered_after_retry"
    assert recovered["order_evidence"] == "persisted"
    assert [record["kind"] for record in recovered["records"]] == [
        "director_beat",
        "actor_turn",
    ]


def test_v2_shell_preserves_selected_season_and_approved_dom_order(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    SeasonRepository(fixture.database).create(
        Season(
            season_id="S01",
            season_number=1,
            title="Earlier Season",
            status=SeasonStatus.SEASON_COMPLETE,
        )
    )

    status, _, body = _call(
        app,
        "/v2/home?season_id=S01",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    page = body.decode("utf-8")
    assert 'data-selected-season="S01"' in page
    assert 'href="/v2/home?season_id=S01"' in page
    assert 'href="/v2/review?season_id=S01"' in page
    assert 'href="/v2/seasons?season_id=S01"' in page
    assert page.index("v2-mobile-context") < page.index("v2-rail") < page.index("v2-main")
    assert page.index("v2-hero") < page.index("v2-state-banner") < page.index("v2-metrics")
    assert page.index("v2-beat") < page.index("v2-next") < page.index("v2-review")
    assert page.index("v2-review") < page.index("v2-notes") < page.index("v2-bottom")
    assert "/api/recover" not in page
    assert "/api/publish" not in page
    assert str(fixture.paths.roots.private) not in page

    status, _, body = _call(
        app,
        "/v2/review?season_id=S01",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    review = body.decode("utf-8")
    assert "Read what actually happened." in review
    assert 'data-review-reader class="v2-review-reader"' in review
    assert 'data-review-tab="script"' in review
    assert 'data-review-tab="diaries"' in review
    assert 'data-review-newer hidden' in review
    assert 'data-selected-season="S01"' in review
    assert "/api/v2/review/diary-attempt" not in review

    status, _, _ = _call(
        app,
        "/api/v2/context?season_id=missing",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("404")


def test_v2_home_has_explicit_no_season_state(tmp_path):
    paths = ServicePaths.from_root(tmp_path / "empty")
    app = DashboardApplication(
        DashboardConfig(
            paths=paths,
            password_hash=hash_password("secret", salt=b"0123456789abcdef"),
            enable_v2=True,
        )
    )
    status, headers, _ = _call(
        app,
        "/login",
        method="POST",
        body=urlencode({"username": "owner", "password": "secret"}).encode(),
    )
    assert status.startswith("303")
    cookie = headers["Set-Cookie"].split(";", 1)[0]

    status, _, body = _call(app, "/api/v2/home", headers={"HTTP_COOKIE": cookie})
    assert status.startswith("200")
    payload = json.loads(body)
    assert payload["data"]["state"] == "no_season"
    assert payload["data"]["context"]["selected_season_id"] is None
    assert payload["data"]["day_completion"]["state"] == "not_scheduled"
    assert payload["data"]["last_accepted_beat"]["available"] is False


def test_v2_worker_lease_and_day_completion_claim_only_stored_evidence(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    with fixture.database.transaction() as connection:
        connection.execute(
            "INSERT INTO work_items(work_id, natural_key, kind, payload_json, status, "
            "available_at, lease_owner, lease_until) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "active-work",
                "active-work",
                "RUN_SCENE",
                "{}",
                "LEASED",
                fixture.now.isoformat(),
                "fixture-worker",
                (fixture.now + timedelta(minutes=5)).isoformat(),
            ),
        )

    status, _, body = _call(
        app,
        "/api/v2/home?season_id=S02",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    home = json.loads(body)["data"]
    assert home["worker"]["state"] == "active_lease"
    assert home["worker"]["label"] == "Active lease observed"
    assert home["day_completion"]["complete"] is False

    with fixture.database.transaction() as connection:
        connection.execute(
            "UPDATE work_items SET lease_until = ? WHERE work_id = 'active-work'",
            ((fixture.now - timedelta(seconds=1)).isoformat(),),
        )
        connection.execute(
            "UPDATE runs SET status = 'COMPLETED' WHERE run_id = 'S02-run-02'"
        )
        connection.execute(
            "UPDATE runs SET status = 'SKIPPED' WHERE run_id = 'S02-run-03'"
        )

    status, _, body = _call(
        app,
        "/api/v2/home?season_id=S02",
        headers={"HTTP_COOKIE": cookie},
    )
    home = json.loads(body)["data"]
    assert home["worker"]["state"] == "expired_lease"
    assert home["worker"]["label"] == "Expired lease observed"
    assert home["day_completion"]["state"] == "closed"
    assert home["day_completion"]["complete"] is True

    with fixture.database.transaction() as connection:
        connection.execute(
            "INSERT INTO schedule_slots(slot_id, season_id, day_number, slot_number, "
            "run_number, scheduled_local, scheduled_utc, utc_offset) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "S02-run-04",
                "S02",
                2,
                1,
                4,
                "2026-09-08T06:00:00-07:00",
                "2026-09-08T13:00:00+00:00",
                "-07:00",
            ),
        )
        connection.execute(
            "INSERT INTO runs(run_id, season_id, slot_id, status) "
            "VALUES ('S02-run-04', 'S02', 'S02-run-04', 'COMPLETED')"
        )
        connection.execute(
            "INSERT INTO days(season_id, day_number, original_date, closed) "
            "VALUES ('S02', 2, '2026-09-08', 1)"
        )

    status, _, body = _call(
        app,
        "/api/v2/home?season_id=S02",
        headers={"HTTP_COOKIE": cookie},
    )
    home = json.loads(body)["data"]
    assert home["day_completion"]["day_number"] == 2
    assert home["day_completion"]["state"] == "closed"
    assert home["day_completion"]["complete"] is True


def test_v2_home_refuses_a_private_path_escape_without_leaking_it(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    escaped = tmp_path / "outside-private.txt"
    escaped.write_text("this must not be disclosed", encoding="utf-8")
    with fixture.database.transaction() as connection:
        connection.execute(
            "UPDATE turns SET content_path = ? WHERE turn_id = 'S02-run-02:r1:tavi'",
            (str(escaped),),
        )

    status, _, body = _call(
        app,
        "/api/v2/home?season_id=S02",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    payload = json.loads(body)
    assert payload["meta"]["freshness"] == "partial"
    assert payload["data"]["last_accepted_beat"]["excerpt"] is None
    assert "latest accepted artifact could not be read" in " ".join(
        payload["data"]["partial_reasons"]
    ).lower()
    assert str(escaped) not in body.decode("utf-8")
    assert "this must not be disclosed" not in body.decode("utf-8")


def test_v2_prepare_projects_versions_without_private_or_model_activity(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    before = fixture.database.connection.total_changes

    status, _, body = _call(
        app,
        "/api/v2/prepare?season_id=S02",
        headers={"HTTP_COOKIE": cookie},
    )

    assert status.startswith("200")
    data = json.loads(body)["data"]
    assert data["state"] == "ready"
    assert data["workspace_version"] == 5
    assert data["selected_step"] == "character_cards"
    assert [step["label"] for step in data["steps"]] == [
        "Season idea", "Opening", "Character cards", "Model assignment",
        "Preflight", "Private preparation", "Schedule preview", "Green review",
    ]
    assert data["steps"][2]["detail"] == "3 of 4 approved"
    mara = next(card for card in data["cards"] if card["character_id"] == "mara")
    assert mara["version"] == 4
    assert mara["status"] == "DRAFT"
    assert mara["approved_truth"]["version"] == 3
    assert mara["prior_versions"] == [3]
    assert data["model_assignment"]["assignments"] == {}
    assert data["private_artifacts"] == []
    assert data["model_assignment"]["automatic_selection"] is False
    assert data["model_calls_performed"] == 0
    assert data["production_state_unchanged"] is True
    serialized = body.decode("utf-8")
    for forbidden in (
        "candidate-12b-a", "candidate-8b-b", "candidate-12b-director",
        "role_sheet", "orientation_text", str(fixture.paths.roots.private),
    ):
        assert forbidden not in serialized
    assert fixture.database.connection.total_changes == before

    status, _, private_body = _call(
        app,
        "/api/v2/prepare?season_id=S02&step=private_preparation",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    private_data = json.loads(private_body)["data"]
    assert len(private_data["private_artifacts"]) == 8
    assert all("content" not in artifact for artifact in private_data["private_artifacts"])
    assert "Protect Mara's private interpretation" not in private_body.decode("utf-8")


def test_v2_prepare_private_artifact_disclosure_is_deliberate_and_provenanced(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    before = fixture.database.connection.total_changes
    status, _, body = _call(
        app,
        "/api/v2/prepare/private-artifact?season_id=S02&character_id=mara&artifact_kind=role_sheet",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    disclosure = json.loads(body)["data"]
    assert disclosure["artifact_kind"] == "role_sheet"
    assert disclosure["source_character_card_version"] == 4
    assert disclosure["content"]["objectives"] == [
        "Protect Mara's private interpretation of the weather library."
    ]
    assert disclosure["immutable_read"] is True
    assert "content_json" not in body.decode("utf-8")
    assert str(fixture.paths.roots.private) not in body.decode("utf-8")
    assert fixture.database.connection.total_changes == before


def test_v2_prepare_completes_manual_rehearsal_without_arming_or_calling_models(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    csrf = _csrf(app, cookie)
    connection = fixture.database.connection
    season_before = tuple(connection.execute(
        "SELECT status, version FROM seasons WHERE season_id = 'S02'"
    ).fetchone())
    schedule_before = connection.execute(
        "SELECT COUNT(*) FROM schedule_slots WHERE season_id = 'S02'"
    ).fetchone()[0]
    calls_before = connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0]

    sequence = [
        ("approve-mara", "approve_card", 5, {"character_id": "mara"}),
        ("approve-models", "approve_model_assignment", 6, {}),
        ("preflight", "record_preflight", 7, {}),
        ("private-prep", "record_private_preparation", 8, {}),
        ("schedule-preview", "record_schedule_preview", 9, {}),
        ("green-review", "record_green_review", 10, {}),
    ]
    final_response = None
    for request_id, action, expected_version, extra in sequence:
        status, _, body = _prepare_action(
            app, cookie, csrf, request_id=request_id, action=action,
            expected_version=expected_version, **extra,
        )
        assert status.startswith("200"), body.decode("utf-8")
        final_response = json.loads(body)

    assert final_response["workspace_version"] == 11
    assert final_response["detail"] == {
        "command_submitted": False,
        "ready": True,
        "season_armed": False,
    }
    status, _, body = _call(
        app,
        "/api/v2/prepare?season_id=S02&step=green_review",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    data = json.loads(body)["data"]
    assert [step["status"] for step in data["steps"]] == [
        "approved", "approved", "approved", "approved",
        "complete", "complete", "complete", "ready",
    ]
    assert data["latest_receipts"]["model_assignment"]["detail"]["automatic_selection"] is False
    assert data["latest_receipts"]["preflight"]["detail"]["model_probe"] == "not_run"
    assert data["latest_receipts"]["schedule_preview"]["detail"]["persisted_schedule_changed"] is False
    assert data["latest_receipts"]["green_review"]["detail"]["season_armed"] is False
    assert tuple(connection.execute(
        "SELECT status, version FROM seasons WHERE season_id = 'S02'"
    ).fetchone()) == season_before
    assert connection.execute(
        "SELECT COUNT(*) FROM schedule_slots WHERE season_id = 'S02'"
    ).fetchone()[0] == schedule_before
    assert connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0] == calls_before

    replay_status, _, replay_body = _prepare_action(
        app, cookie, csrf, request_id="green-review", action="record_green_review",
        expected_version=10,
    )
    assert replay_status.startswith("200")
    assert json.loads(replay_body) == final_response


def test_v2_prepare_versioned_opening_revision_invalidates_dependents(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    csrf = _csrf(app, cookie)
    status, _, body = _prepare_action(
        app, cookie, csrf, request_id="revise-opening", action="revise_opening",
        expected_version=5,
    )
    assert status.startswith("200"), body.decode("utf-8")
    assert json.loads(body)["detail"] == {
        "invalidated_from": "character_cards",
        "opening_version": 4,
    }

    status, _, body = _call(
        app,
        "/api/v2/prepare?season_id=S02&step=opening",
        headers={"HTTP_COOKIE": cookie},
    )
    data = json.loads(body)["data"]
    assert data["opening_version"] == 4
    assert all(card["status"] in {"DRAFT", "STALE_APPROVED"} for card in data["cards"])
    assert set(data["latest_receipts"]) == {"idea", "opening"}
    assert data["invalidations"][0]["invalidated_steps"] == [
        "character_cards", "model_assignment", "preflight", "private_preparation",
        "schedule_preview", "green_review",
    ]
    assert fixture.database.connection.execute(
        "SELECT COUNT(*) FROM season_opening_versions WHERE season_id = 'S02'"
    ).fetchone()[0] == 4


def test_v2_prepare_card_revision_preserves_approved_truth_and_invalidates_dependents(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    csrf = _csrf(app, cookie)
    status, _, body = _prepare_action(
        app, cookie, csrf, request_id="revise-tavi", action="save_card_revision",
        expected_version=5, character_id="tavi", card={
            "pronouns": "they / them",
            "public_brief": "Circulation clerk who can identify borrowed weather by touch.",
            "occupation_skills": ["Catalog systems", "Pattern recall"],
            "voice_anchors": ["Quiet confidence", "One exact question"],
            "habits": ["Warms their hands on fog cards"],
        },
    )
    assert status.startswith("200"), body.decode("utf-8")
    assert json.loads(body)["detail"] == {
        "card_version": 4,
        "character_id": "tavi",
        "status": "DRAFT",
    }
    status, _, body = _call(
        app, "/api/v2/prepare?season_id=S02&character_id=tavi",
        headers={"HTTP_COOKIE": cookie},
    )
    data = json.loads(body)["data"]
    tavi = next(card for card in data["cards"] if card["character_id"] == "tavi")
    assert tavi["version"] == 4
    assert tavi["approved_truth"]["version"] == 3
    assert tavi["prior_versions"] == [3]
    assert data["invalidations"][0]["source_step"] == "character_cards"
    assert data["invalidations"][0]["invalidated_steps"] == [
        "model_assignment", "preflight", "private_preparation",
        "schedule_preview", "green_review",
    ]


def test_v2_prepare_actions_require_csrf_and_cannot_target_s01_or_production(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    payload = json.dumps({
        "request_id": "bad-boundary", "season_id": "S02",
        "action": "approve_card", "expected_version": 5, "character_id": "mara",
    }).encode("utf-8")
    status, _, _ = _call(
        app, "/api/v2/prepare/action", method="POST", body=payload,
        headers={"HTTP_COOKIE": cookie, "CONTENT_TYPE": "application/json"},
    )
    assert status.startswith("400")

    csrf = _csrf(app, cookie)
    s01_payload = json.dumps({
        "request_id": "s01-boundary", "season_id": "S01",
        "action": "record_green_review", "expected_version": 1,
    }).encode("utf-8")
    status, _, body = _call(
        app, "/api/v2/prepare/action", method="POST", body=s01_payload,
        headers={"HTTP_COOKIE": cookie, "HTTP_X_CSRF_TOKEN": csrf, "CONTENT_TYPE": "application/json"},
    )
    assert status.startswith("400")
    assert "cannot target S01" in body.decode("utf-8")
    live_s01_payload = json.dumps({
        "request_id": "live-s01-boundary", "season_id": "S01", "action": "skip",
        "snapshot_hash": "not-a-real-review", "expected_season_version": 1,
        "expected_run_version": 1, "expected_recovery_version": 1,
    }).encode("utf-8")
    status, _, body = _call(
        app, "/api/v2/live/action", method="POST", body=live_s01_payload,
        headers={"HTTP_COOKIE": cookie, "HTTP_X_CSRF_TOKEN": csrf, "CONTENT_TYPE": "application/json"},
    )
    assert status.startswith("400")
    assert "cannot target S01" in body.decode("utf-8")

    production = DashboardApplication(
        DashboardConfig(
            paths=fixture.paths,
            username="owner",
            password_hash=hash_password("secret", salt=b"0123456789abcdef"),
            enable_v2=True,
            environment="production",
        ),
        clock=VirtualClock(fixture.now),
    )
    status, headers, _ = _call(
        production, "/login", method="POST",
        body=urlencode({"username": "owner", "password": "secret"}).encode(),
        headers={"CONTENT_TYPE": "application/x-www-form-urlencoded"},
    )
    prod_cookie = headers["Set-Cookie"].split(";", 1)[0]
    prod_csrf = _csrf(production, prod_cookie)
    status, _, body = _prepare_action(
        production, prod_cookie, prod_csrf, request_id="prod-boundary",
        action="approve_card", expected_version=5, character_id="mara",
    )
    assert status.startswith("400")
    assert "sandbox-only" in body.decode("utf-8")
    status, _, body = _call(
        production, "/api/v2/live/impact-review?season_id=S02&action=retry",
        headers={"HTTP_COOKIE": prod_cookie},
    )
    assert status.startswith("400")
    assert "sandbox-only" in body.decode("utf-8")


def test_v2_diagnostics_distinguishes_call_stages_without_private_leakage(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    before = fixture.database.connection.total_changes
    status, _, body = _call(
        app,
        "/api/v2/diagnostics/calls?season_id=S02",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    payload = json.loads(body)
    data = payload["data"]
    assert data["state"] == "ready"
    assert data["excluded_private_attempt_count"] == 1
    assert all(not call["purpose"].startswith("diary:") for call in data["calls"])
    assert {call["status"] for call in data["calls"]} >= {"ACCEPTED", "COMPLETED", "RETRYABLE_FAILURE"}
    serialized = body.decode("utf-8")
    assert "Keep this attempt private" not in serialized
    assert "WELLNESS_SIGNAL" not in serialized
    assert str(fixture.paths.roots.private) not in serialized
    assert fixture.database.connection.total_changes == before

    call_id = "S02-run-02:director:r4:a1"
    status, _, body = _call(
        app,
        f"/api/v2/diagnostics/calls/{call_id}?season_id=S02",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    detail = json.loads(body)["data"]["selected_call"]
    assert detail["response_format_mode"] == "NATIVE_SCHEMA"
    assert [stage["stage"] for stage in detail["stages"]] == [
        "raw", "parsed", "validated", "accepted", "rendered"
    ]
    assert [stage["state"] for stage in detail["stages"]] == [
        "available", "available", "failed", "absent", "absent"
    ]
    assert detail["validator_code"] == "schema_failure.state_changes"
    assert detail["provenance"]["schema_version_id"] == "director-beat-v4"
    assert detail["review_href"] is None
    assert fixture.database.connection.total_changes == before


def test_v2_diagnostics_raw_disclosure_is_deliberate_contained_and_read_only(tmp_path):
    fixture, app, cookie = _authenticated_fixture(tmp_path)
    before = fixture.database.connection.total_changes
    status, _, body = _call(
        app,
        "/api/v2/diagnostics/call-raw?season_id=S02&"
        "call_id=S02-run-02%3Adirector%3Ar4%3Aa1",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    disclosure = json.loads(body)["data"]
    assert disclosure["immutable_read"] is True
    assert "archive lights dim" in disclosure["content"]
    assert "wellness" not in disclosure["content"].lower()
    assert fixture.database.connection.total_changes == before

    status, _, body = _call(
        app,
        "/api/v2/diagnostics/call-raw?season_id=S02&"
        "call_id=S02%3Adiary%3Atavi%3Aday%3A1%3Aslot%3A2%3Aa1",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("404")
    assert "Keep this attempt private" not in body.decode("utf-8")


def test_v2_diagnostics_filters_and_exact_review_return_are_stored(tmp_path):
    _, app, cookie = _authenticated_fixture(tmp_path)
    status, _, body = _call(
        app,
        "/api/v2/diagnostics/calls?season_id=S02&character_id=mara&status=ACCEPTED&attempt=1",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    data = json.loads(body)["data"]
    assert [call["call_id"] for call in data["calls"]] == ["S02-run-01:mara:r1:a1"]
    detail = data["selected_call"]
    assert detail["review_href"].endswith(
        "season_id=S02&day=1&run_id=S02-run-01&tab=script&turn_id=S02-run-01%3Ar1%3Amara"
    )
    assert detail["stages"][-1]["content"].startswith("I stamp the thunder")

    status, _, body = _call(
        app,
        "/v2/diagnostics?season_id=S02",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    page = body.decode("utf-8")
    assert "Explain one call without changing anything." in page
    assert "data-diagnostics-reader" in page
    assert "/api/recover" not in page
    assert "/api/publish" not in page


def test_v2_assets_encode_polling_and_exception_states(tmp_path):
    _, app, cookie = _authenticated_fixture(tmp_path)
    status, _, body = _call(app, "/assets/dashboard.js", headers={"HTTP_COOKIE": cookie})
    assert status.startswith("200")
    script = body.decode("utf-8")
    assert "window.setInterval(() => refresh(), 60000);" in script
    assert "stale_readable" in script
    assert "disconnected" in script
    assert "last snapshot retained" in script.lower()
    probe = script.split("async function probeReview()", 1)[1].split(
        "async function refreshReviewOperationalContext", 1
    )[0]
    assert "replaceChildren" not in probe
    assert "window.localStorage.setItem" in script
    assert 'window.addEventListener("pagehide", saveReviewPosition);' in script
    assert "disclosedDiaryIds" in script
    assert ".innerHTML" not in script

    status, _, body = _call(app, "/assets/dashboard.css", headers={"HTTP_COOKIE": cookie})
    assert status.startswith("200")
    stylesheet = body.decode("utf-8")
    assert "@media (max-width: 919px)" in stylesheet
    assert "overflow-x: hidden" in stylesheet
    assert "#e7e1d5" in stylesheet
    assert "#26302d" in stylesheet
    assert ".v2-review-layout" in stylesheet
    assert ".v2-transcript" in stylesheet
    assert "white-space: pre-wrap" in stylesheet


def test_dashboard_environment_is_explicit_and_strict(tmp_path):
    with pytest.raises(ValueError, match="sandbox or production"):
        DashboardConfig(
            paths=ServicePaths.from_root(tmp_path / "data"),
            password_hash="unused",
            environment="staging",
        )
