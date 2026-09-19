import io
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from improv_troupe.application import ServicePaths
from improv_troupe.clock import VirtualClock
from improv_troupe.domain import (
    CastMember,
    Diary,
    DiaryStatus,
    OpeningSnapshot,
    ScheduleSlot,
    Season,
    SeasonStatus,
)
from improv_troupe.infrastructure import (
    DataRoots,
    ModelCallRepository,
    RecordRepository,
    ScheduleRepository,
    SQLiteDatabase,
    SeasonRepository,
)
from improv_troupe.web.dashboard import DashboardApplication, DashboardConfig, hash_password


def _call(app, path, *, method="GET", body=b"", headers=None):
    captured = {}
    request_headers = {
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
    for key, value in (headers or {}).items():
        request_headers[key] = value

    def start_response(status, response_headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = response_headers

    content = b"".join(app(request_headers, start_response))
    return captured["status"], dict(captured["headers"]), content


def test_dashboard_requires_login_and_exposes_status_and_diaries_after_login(tmp_path):
    roots = DataRoots.from_root(tmp_path / "data")
    roots.prepare()
    database = SQLiteDatabase(roots.state / "improv.sqlite3")
    database.migrate()
    SeasonRepository(database).create(Season(season_id="S01", season_number=1))
    diary_path = roots.private / "seasons" / "S01" / "day-01" / "diary" / "mara.md"
    diary_path.parent.mkdir(parents=True)
    diary_path.write_text("I saw the blue door.", encoding="utf-8")
    RecordRepository(database).insert_diary(
        Diary(
            diary_id="S01:day:1:diary:mara",
            season_id="S01",
            character_id="mara",
            day_number=1,
            status=DiaryStatus.WRITTEN,
            word_count=5,
            content_path=str(diary_path),
        )
    )
    app = DashboardApplication(
        DashboardConfig(
            paths=ServicePaths.from_root(roots.root),
            username="owner",
            password_hash=hash_password("secret", salt=b"0123456789abcdef"),
            enable_v2=False,
        ),
        clock=VirtualClock(datetime(2026, 8, 21, 20, tzinfo=timezone.utc)),
    )

    status, _, _ = _call(app, "/api/status")
    assert status.startswith("401")
    status, _, _ = _call(app, "/v2/home")
    assert status.startswith("401")
    status, _, _ = _call(app, "/api/v2/context")
    assert status.startswith("401")
    status, headers, _ = _call(
        app,
        "/login",
        method="POST",
        body=urlencode({"username": "owner", "password": "secret"}).encode(),
        headers={"CONTENT_TYPE": "application/x-www-form-urlencoded"},
    )
    assert status.startswith("303")
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    csrf = headers["X-CSRF-Token"]

    status, page_headers, body = _call(app, "/", headers={"HTTP_COOKIE": cookie})
    assert status.startswith("200")
    page = body.decode("utf-8")
    assert "Simulation Query" in page
    assert 'id="metric-state"' in page
    assert "Operator attention" in page
    assert "Diary desk" in page
    assert "End-of-day review" in page
    assert "Publication gate" in page
    assert 'href="/assets/dashboard-legacy.css"' in page
    assert 'src="/assets/dashboard-legacy.js"' in page
    assert "<style>" not in page
    assert "<script>" not in page
    assert f'name="csrf_token" value="{csrf}"' in page
    assert page_headers["X-Content-Type-Options"] == "nosniff"
    assert page_headers["X-Frame-Options"] == "DENY"
    assert "script-src 'self'" in page_headers["Content-Security-Policy"]

    status, asset_headers, body = _call(app, "/assets/dashboard-legacy.js")
    assert status.startswith("200")
    assert asset_headers["Content-Type"] == "text/javascript; charset=utf-8"
    script = body.decode("utf-8")
    assert 'window.setInterval(() => refresh(), 60000);' in script
    assert "data-detail-key" in script
    status, asset_headers, _ = _call(app, "/assets/dashboard-legacy.css")
    assert status.startswith("200")
    assert asset_headers["Content-Type"] == "text/css; charset=utf-8"
    status, _, _ = _call(app, "/assets/../dashboard.py")
    assert status.startswith("404")

    v2_app = DashboardApplication(
        DashboardConfig(
            paths=ServicePaths.from_root(roots.root),
            username="owner",
            password_hash=hash_password("secret", salt=b"0123456789abcdef"),
            enable_v2=True,
        ),
        clock=VirtualClock(datetime(2026, 8, 21, 20, tzinfo=timezone.utc)),
    )
    status, v2_headers, _ = _call(
        v2_app,
        "/login",
        method="POST",
        body=urlencode({"username": "owner", "password": "secret"}).encode(),
        headers={"CONTENT_TYPE": "application/x-www-form-urlencoded"},
    )
    assert status.startswith("303")
    assert v2_headers["Location"] == "/v2/home"
    v2_cookie = v2_headers["Set-Cookie"].split(";", 1)[0]

    status, _, body = _call(v2_app, "/", headers={"HTTP_COOKIE": v2_cookie})
    assert status.startswith("200")
    v2_page = body.decode("utf-8")
    assert "Keep the troupe in view." in v2_page
    assert "Last accepted beat" in v2_page
    assert "Evidence, not inference" in v2_page
    assert 'data-selected-season="S01"' in v2_page
    assert 'href="/assets/dashboard.css"' in v2_page
    assert 'src="/assets/dashboard.js"' in v2_page
    assert "/api/recover" not in v2_page
    assert "/api/publish" not in v2_page
    assert "WELLNESS_SIGNAL" not in v2_page

    status, _, body = _call(v2_app, "/api/v2/context", headers={"HTTP_COOKIE": v2_cookie})
    assert status.startswith("200")
    context = json.loads(body)
    assert context["meta"]["environment"] == "sandbox"
    assert context["data"]["selected_season_id"] == "S01"
    assert context["data"]["navigation"][3]["href"] == "/v2/review?season_id=S01"

    status, _, body = _call(v2_app, "/api/v2/home", headers={"HTTP_COOKIE": v2_cookie})
    assert status.startswith("200")
    home = json.loads(body)
    assert home["data"]["state"] == "ready"
    assert home["data"]["day_completion"]["complete"] is False
    assert home["data"]["worker"]["label"] == "No active lease observed"

    status, _, body = _call(app, "/api/status", headers={"HTTP_COOKIE": cookie})
    assert status.startswith("200")
    payload = json.loads(body)
    assert payload["database"].endswith("improv.sqlite3")
    assert payload["seasons"][0]["diary_counts"] == {"WRITTEN": 1}
    assert payload["seasons"][0]["cast"] == []
    assert "model_manifest" not in body.decode("utf-8")

    status, _, body = _call(
        app,
        "/api/diaries?season_id=S01&day=1",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    assert json.loads(body)["diaries"][0]["content"] == "I saw the blue door."

    status, _, _ = _call(
        app,
        "/logout",
        method="POST",
        body=b"{}",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("400")
    status, _, _ = _call(
        app,
        "/logout",
        method="POST",
        body=b"{}",
        headers={"HTTP_COOKIE": cookie, "HTTP_X_CSRF_TOKEN": csrf},
    )
    assert status.startswith("303")


def test_dashboard_v2_seam_is_disabled_by_default(tmp_path):
    paths = ServicePaths.from_root(tmp_path / "data")
    app = DashboardApplication(
        DashboardConfig(
            paths=paths,
            username="owner",
            password_hash=hash_password("secret", salt=b"0123456789abcdef"),
        )
    )

    status, headers, _ = _call(
        app,
        "/login",
        method="POST",
        body=urlencode({"username": "owner", "password": "secret"}).encode(),
        headers={"CONTENT_TYPE": "application/x-www-form-urlencoded"},
    )
    assert status.startswith("303")
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    status, _, _ = _call(app, "/v2/home", headers={"HTTP_COOKIE": cookie})
    assert status.startswith("404")


def test_dashboard_day_review_keeps_shared_script_and_private_wellness_attempt_owner_only(tmp_path):
    roots = DataRoots.from_root(tmp_path / "data")
    roots.prepare()
    database = SQLiteDatabase(roots.state / "improv.sqlite3")
    database.migrate()
    pacific = ZoneInfo("America/Los_Angeles")
    local_slot = datetime(2026, 8, 21, 6, tzinfo=pacific)
    SeasonRepository(database).create(
        Season(
            season_id="S01",
            season_number=1,
            title="Aether",
            status=SeasonStatus.RUNNING,
            opening=OpeningSnapshot(
                set="Signal room",
                setting="A closed radio station before dawn.",
                cast=["Mara", "Nox"],
                world_rules=["Nothing is recorded twice."],
            ),
            cast=[
                CastMember(character_id="mara", name="Mara"),
                CastMember(character_id="nox", name="Nox"),
            ],
        )
    )
    ScheduleRepository(database).add(
        ScheduleSlot(
            slot_id="S01-run-01",
            season_id="S01",
            day_number=1,
            slot_number=1,
            run_number=1,
            scheduled_local=local_slot,
            scheduled_utc=local_slot.astimezone(timezone.utc),
            utc_offset="-07:00",
        )
    )
    records = RecordRepository(database)
    records.insert_run(
        run_id="S01-run-01",
        season_id="S01",
        slot_id="S01-run-01",
        status="COMPLETED",
    )
    narration_path = roots.private / "runs" / "S01-run-01" / "narration.md"
    turn_path = roots.private / "runs" / "S01-run-01" / "mara.md"
    narration_path.parent.mkdir(parents=True)
    narration_path.write_text("The receiver wakes with a low blue hum.", encoding="utf-8")
    turn_path.write_text("I answer the signal before it learns my name.", encoding="utf-8")
    records.insert_turn(
        turn_id="S01-run-01:stage:1",
        run_id="S01-run-01",
        round_number=1,
        character_id="stage",
        disposition="NARRATION_ACCEPT",
        content_path=str(narration_path),
    )
    records.insert_turn(
        turn_id="S01-run-01:r1:mara",
        run_id="S01-run-01",
        round_number=1,
        character_id="mara",
        disposition="ACCEPT",
        content_path=str(turn_path),
    )
    accepted_diary_path = roots.private / "seasons" / "S01" / "day-01" / "diary" / "mara.md"
    accepted_diary_path.parent.mkdir(parents=True)
    accepted_diary_path.write_text("The radio remembered my name.", encoding="utf-8")
    records.insert_diary(
        Diary(
            diary_id="S01:day:1:diary:mara",
            season_id="S01",
            character_id="mara",
            day_number=1,
            chosen_slot_number=1,
            status=DiaryStatus.WRITTEN,
            word_count=5,
            content_path=str(accepted_diary_path),
        )
    )
    records.insert_diary(
        Diary(
            diary_id="S01:day:1:diary:nox",
            season_id="S01",
            character_id="nox",
            day_number=1,
            chosen_slot_number=1,
            status=DiaryStatus.PRIVATE,
        )
    )
    records.insert_day(season_id="S01", day_number=1, original_date="2026-08-21")
    records.update_day(
        season_id="S01",
        day_number=1,
        cutoff_at="2026-08-21T15:00:00+00:00",
        closed=True,
    )
    flagged_output_path = roots.private / "model-calls" / "S01-nox-diary-a1" / "output.md"
    flagged_output_path.parent.mkdir(parents=True)
    flagged_output_path.write_text(
            "<DIARY_SLOT>1</DIARY_SLOT><WRITE_NOW>true</WRITE_NOW>"
            "<DIARY_TEXT>The blue hum felt too close to my ribs.</DIARY_TEXT>"
            "<EVIDENCE_REFS>1</EVIDENCE_REFS>"
            "<WELLNESS_SIGNAL>Please slow the scene down.</WELLNESS_SIGNAL>",
        encoding="utf-8",
    )
    calls = ModelCallRepository(database)
    calls.create(
        call_id="S01:diary:nox:day:1:slot:1:a1",
        run_id=None,
        purpose="diary:S01:nox:day:1:slot:1",
        attempt=1,
        status="STREAMING",
        started_at="2026-08-21T13:00:00+00:00",
    )
    calls.finish(
        call_id="S01:diary:nox:day:1:slot:1:a1",
        status="ACCEPTED",
        ended_at="2026-08-21T13:00:01+00:00",
        latency_ms=1000,
        output_path=str(flagged_output_path),
    )
    app = DashboardApplication(
        DashboardConfig(
            paths=ServicePaths.from_root(roots.root),
            username="owner",
            password_hash=hash_password("secret", salt=b"0123456789abcdef"),
        ),
        clock=VirtualClock(datetime(2026, 8, 21, 20, tzinfo=timezone.utc)),
    )

    status, _, _ = _call(app, "/api/day-review?season_id=S01&day=1")
    assert status.startswith("401")
    status, headers, _ = _call(
        app,
        "/login",
        method="POST",
        body=urlencode({"username": "owner", "password": "secret"}).encode(),
        headers={"CONTENT_TYPE": "application/x-www-form-urlencoded"},
    )
    assert status.startswith("303")
    cookie = headers["Set-Cookie"].split(";", 1)[0]

    status, _, body = _call(
        app,
        "/api/day-review?season_id=S01&day=1",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    review = json.loads(body)
    assert review["closed"] is True
    assert review["runs"] == [
        {
            "completion_reason": None,
            "delay": None,
            "run_id": "S01-run-01",
            "run_number": 1,
            "scheduled_local": "2026-08-21T06:00:00-07:00",
            "script_available": True,
            "slot_number": 1,
            "status": "COMPLETED",
            "turn_count": 0,
        }
    ]
    assert "Signal room" in review["shared_script"]
    assert "The receiver wakes with a low blue hum." in review["shared_script"]
    assert "Mara: I answer the signal before it learns my name." in review["shared_script"]
    assert "private_plan" not in body.decode("utf-8")
    by_character = {diary["character_id"]: diary for diary in review["diaries"]}
    assert by_character["mara"]["content"] == "The radio remembered my name."
    assert by_character["mara"]["review_source"] == "ACCEPTED_DIARY"
    assert by_character["nox"]["status"] == "PRIVATE"
    assert by_character["nox"]["review_source"] == "PRIVATE_WELLNESS_OUTPUT"
    assert by_character["nox"]["wellness_flag"] is True
    assert by_character["nox"]["content"] == "The blue hum felt too close to my ribs."
    assert "Please slow the scene down." in by_character["nox"]["raw_output"]

    status, _, body = _call(
        app,
        "/api/diaries?season_id=S01&day=1",
        headers={"HTTP_COOKIE": cookie},
    )
    assert status.startswith("200")
    diary_payload = json.loads(body)
    nox = next(diary for diary in diary_payload["diaries"] if diary["character_id"] == "nox")
    assert nox["review_source"] == "PRIVATE_WELLNESS_OUTPUT"
    assert nox["wellness_flag"] is True
