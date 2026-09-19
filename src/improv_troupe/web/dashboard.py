"""Small authenticated WSGI dashboard for the private Mac/operator view.

This intentionally uses only the Python standard library.  It is a durable
operator surface, not the public art website: default API payloads contain
operational state, while diary text is available only after owner login.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from http.cookies import SimpleCookie
from typing import Callable, Iterable, Literal
from urllib.parse import parse_qs, unquote
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from ..application import (
    CommandBus,
    CommandError,
    PublicationService,
    PreparationError,
    PreparationService,
    LiveSupervisionError,
    LiveSupervisionService,
    SeasonsError,
    SeasonsService,
    ResolveRecovery,
    ServicePaths,
    read_service_status,
)
from ..clock import Clock, SystemClock
from ..infrastructure import RecordRepository, SeasonRepository, SQLiteDatabase
from ..llm.structured import StructuredOutputError, parse_diary_output
from .dashboard_contracts import DashboardError, DashboardNotFound
from .dashboard_read_models import DashboardReadModels
from .dashboard_views import legacy_dashboard_html, login_html, static_asset, v2_dashboard_html


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Create a portable scrypt password record without storing the password."""
    if not password:
        raise ValueError("password cannot be empty")
    salt = salt or secrets.token_bytes(16)
    n, r, p = 2**14, 8, 1
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    return "scrypt${n}${r}${p}${salt}${digest}".format(
        n=n,
        r=r,
        p=p,
        salt=base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
        digest=base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
    )


def _verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_text, digest_text = encoded.split("$", 5)
        if scheme != "scrypt":
            return False
        salt = _b64decode(salt_text)
        expected = _b64decode(digest_text)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError, OverflowError):
        return False


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass
class DashboardAuth:
    """In-memory owner sessions with an explicit CSRF token."""

    username: str
    password_hash: str
    clock: Clock = field(default_factory=SystemClock)
    session_hours: int = 12
    sessions: dict[str, tuple[str, str, float]] = field(default_factory=dict)

    def login(self, username: str, password: str) -> tuple[str, str] | None:
        if not hmac.compare_digest(username, self.username) or not _verify_password(
            password, self.password_hash
        ):
            return None
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        self.sessions[token] = (username, csrf, time.time() + self.session_hours * 3600)
        return token, csrf

    def session(self, token: str | None) -> tuple[str, str] | None:
        if not token:
            return None
        value = self.sessions.get(token)
        if value is None:
            return None
        username, csrf, expires = value
        if time.time() >= expires:
            self.sessions.pop(token, None)
            return None
        return username, csrf

    def logout(self, token: str | None) -> None:
        if token:
            self.sessions.pop(token, None)


@dataclass(frozen=True)
class DashboardConfig:
    paths: ServicePaths
    username: str = "owner"
    password_hash: str = ""
    secure_cookie: bool = False
    enable_v2: bool = False
    environment: Literal["sandbox", "production"] = "sandbox"

    def __post_init__(self) -> None:
        if self.environment not in {"sandbox", "production"}:
            raise ValueError("dashboard environment must be sandbox or production")


class DashboardApplication:
    """WSGI application for the authenticated private operator dashboard."""

    def __init__(
        self,
        config: DashboardConfig,
        *,
        clock: Clock | None = None,
        auth: DashboardAuth | None = None,
    ):
        if not config.password_hash and auth is None:
            raise ValueError("dashboard password_hash is required")
        self.config = config
        self.clock = clock or SystemClock()
        self.paths = config.paths
        self.paths.prepare()
        self.database = SQLiteDatabase(self.paths.database_path)
        self.database.migrate()
        self.auth = auth or DashboardAuth(config.username, config.password_hash, clock=self.clock)

    def __call__(self, environ, start_response):
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        try:
            if path == "/healthz":
                return self._response(start_response, 200, {"status": "ok"})
            if path.startswith("/assets/") and method == "GET":
                return self._asset(start_response, path.removeprefix("/assets/"))
            if path == "/login":
                return self._login(environ, start_response, method)
            token = self._cookie(environ, "improv_session")
            session = self.auth.session(token)
            if session is None:
                return self._unauthorized(start_response)
            if method == "POST":
                self._require_csrf(environ, session[1])
            if path == "/logout" and method == "POST":
                self.auth.logout(token)
                return self._response(
                    start_response,
                    303,
                    b"",
                    headers=[("Location", "/login")],
                )
            if path == "/":
                # The v2 shell is the live operator surface once the
                # implementation seam is enabled.  Keep the legacy renderer
                # available only for an explicit rollback configuration.
                return self._dashboard(environ, start_response, session[1])
            v2_page = path.removeprefix("/v2/") if path.startswith("/v2/") else None
            if (
                v2_page in {"home", "prepare", "live", "review", "diagnostics", "seasons"}
                and method == "GET"
                and self.config.enable_v2
            ):
                return self._v2_page(environ, start_response, str(v2_page), csrf=session[1])
            if path == "/api/v2/context" and method == "GET" and self.config.enable_v2:
                return self._api_v2_context(environ, start_response)
            if path == "/api/v2/home" and method == "GET" and self.config.enable_v2:
                return self._api_v2_home(environ, start_response)
            if path == "/api/v2/prepare" and method == "GET" and self.config.enable_v2:
                return self._api_v2_prepare(environ, start_response)
            if (
                path == "/api/v2/prepare/private-artifact"
                and method == "GET"
                and self.config.enable_v2
            ):
                return self._api_v2_prepare_private_artifact(environ, start_response)
            if path == "/api/v2/prepare/action" and method == "POST" and self.config.enable_v2:
                return self._api_v2_prepare_action(environ, start_response)
            if path == "/api/v2/live" and method == "GET" and self.config.enable_v2:
                return self._api_v2_live(environ, start_response)
            if path == "/api/v2/live/transcript" and method == "GET" and self.config.enable_v2:
                return self._api_v2_live_transcript(environ, start_response)
            if path == "/api/v2/live/impact-review" and method == "GET" and self.config.enable_v2:
                return self._api_v2_live_impact_review(environ, start_response)
            if path == "/api/v2/live/action" and method == "POST" and self.config.enable_v2:
                return self._api_v2_live_action(environ, start_response)
            if path == "/api/v2/seasons" and method == "GET" and self.config.enable_v2:
                return self._api_v2_seasons(environ, start_response)
            if path == "/api/v2/seasons/private-close" and method == "POST" and self.config.enable_v2:
                return self._api_v2_private_close(environ, start_response)
            if path == "/api/v2/seasons/publication-preview" and method == "POST" and self.config.enable_v2:
                return self._api_v2_publication_preview(environ, start_response)
            if path == "/api/v2/seasons/publish" and method == "POST" and self.config.enable_v2:
                return self._api_v2_publish_season(environ, start_response)
            if path == "/api/v2/review/day" and method == "GET" and self.config.enable_v2:
                return self._api_v2_review_day(environ, start_response)
            if (
                path == "/api/v2/review/diary-attempt"
                and method == "GET"
                and self.config.enable_v2
            ):
                return self._api_v2_diary_attempt(environ, start_response)
            if path == "/api/v2/diagnostics/calls" and method == "GET" and self.config.enable_v2:
                return self._api_v2_diagnostics(environ, start_response)
            if (
                path.startswith("/api/v2/diagnostics/calls/")
                and method == "GET"
                and self.config.enable_v2
            ):
                call_id = unquote(path.removeprefix("/api/v2/diagnostics/calls/"))
                return self._api_v2_diagnostics(environ, start_response, call_id=call_id)
            if (
                path == "/api/v2/diagnostics/call-raw"
                and method == "GET"
                and self.config.enable_v2
            ):
                return self._api_v2_call_raw(environ, start_response)
            if path == "/api/status" and method == "GET":
                return self._api_status(start_response)
            if path == "/api/diaries" and method == "GET":
                return self._api_diaries(environ, start_response)
            if path == "/api/day-review" and method == "GET":
                return self._api_day_review(environ, start_response)
            if path == "/api/recover" and method == "POST":
                return self._api_recover(environ, start_response)
            if path == "/api/publish" and method == "POST":
                return self._api_publish(environ, start_response)
            return self._response(start_response, 404, {"error": "not found"})
        except DashboardNotFound as exc:
            return self._response(start_response, 404, {"error": str(exc)})
        except (DashboardError, PreparationError, LiveSupervisionError, SeasonsError, CommandError) as exc:
            return self._response(start_response, 400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - keep HTTP boundary from leaking tracebacks
            return self._response(start_response, 500, {"error": type(exc).__name__})

    def _login(self, environ, start_response, method: str):
        if method == "GET":
            return self._response(start_response, 200, login_html(), content_type="text/html")
        if method != "POST":
            return self._response(start_response, 405, {"error": "method not allowed"})
        fields = self._body_fields(environ)
        result = self.auth.login(fields.get("username", ""), fields.get("password", ""))
        if result is None:
            return self._response(start_response, 401, {"error": "invalid credentials"})
        token, csrf = result
        cookie = f"improv_session={token}; HttpOnly; SameSite=Strict; Path=/"
        if self.config.secure_cookie:
            cookie += "; Secure"
        destination = "/v2/home" if self.config.enable_v2 else "/"
        return self._response(
            start_response,
            303,
            b"",
            headers=[
                ("Location", destination),
                ("Set-Cookie", cookie),
                ("X-CSRF-Token", csrf),
            ],
        )

    def _dashboard(self, environ, start_response, csrf: str):
        if self.config.enable_v2:
            return self._v2_page(environ, start_response, "home", csrf=csrf)
        return self._response(
            start_response,
            200,
            legacy_dashboard_html(csrf),
            content_type="text/html",
        )

    def _v2_page(self, environ, start_response, page: str, *, csrf: str):
        season_id = self._query_season_id(environ)
        context = self._v2_reads().context(season_id)
        return self._response(
            start_response,
            200,
            v2_dashboard_html(
                page=page,
                environment=self.config.environment,
                context=context.data,
                csrf=csrf,
            ),
            content_type="text/html",
        )

    def _api_v2_context(self, environ, start_response):
        payload = self._v2_reads().context(self._query_season_id(environ))
        return self._response(start_response, 200, payload.model_dump(mode="json"))

    def _api_v2_home(self, environ, start_response):
        payload = self._v2_reads().home(self._query_season_id(environ))
        return self._response(start_response, 200, payload.model_dump(mode="json"))

    def _api_v2_prepare(self, environ, start_response):
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=False)
        step = str(query["step"][0]) if query.get("step") else None
        character_id = str(query["character_id"][0]) if query.get("character_id") else None
        payload = self._v2_reads().prepare(
            self._query_season_id(environ), step=step, character_id=character_id
        )
        return self._response(start_response, 200, payload.model_dump(mode="json"))

    def _api_v2_prepare_action(self, environ, start_response):
        if self.config.environment != "sandbox":
            raise DashboardError("preparation rehearsal actions are sandbox-only")
        body = self._json_body(environ)
        season_id = str(body.get("season_id") or "")
        if not season_id or season_id == "S01":
            raise DashboardError("preparation rehearsal cannot target S01")
        request_id = str(body.get("request_id") or "")
        action = str(body.get("action") or "")
        try:
            expected_version = int(body.get("expected_version"))
        except (TypeError, ValueError) as exc:
            raise DashboardError("expected_version is required") from exc
        if not request_id or not action:
            raise DashboardError("request_id and action are required")
        card = body.get("card")
        if card is not None and not isinstance(card, dict):
            raise DashboardError("card must be an object")
        result = PreparationService(self.database, self.clock.now()).perform(
            request_id=request_id, season_id=season_id, action=action,
            expected_version=expected_version,
            character_id=(str(body["character_id"]) if body.get("character_id") else None),
            card=card if isinstance(card, dict) else None,
        )
        return self._response(start_response, 200, result)

    def _api_v2_prepare_private_artifact(self, environ, start_response):
        if self.config.environment != "sandbox":
            raise DashboardError("preparation rehearsal disclosures are sandbox-only")
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=False)
        season_id = str((query.get("season_id") or [""])[0])
        character_id = str((query.get("character_id") or [""])[0])
        artifact_kind = str((query.get("artifact_kind") or [""])[0])
        if not season_id or not character_id or not artifact_kind:
            raise DashboardError("season_id, character_id, and artifact_kind are required")
        if season_id == "S01":
            raise DashboardError("preparation rehearsal cannot target S01")
        payload = self._v2_reads().private_preparation_artifact(
            season_id, character_id=character_id, artifact_kind=artifact_kind
        )
        return self._response(start_response, 200, payload.model_dump(mode="json"))

    def _api_v2_live(self, environ, start_response):
        payload = self._v2_reads().live(self._query_season_id(environ))
        return self._response(start_response, 200, payload.model_dump(mode="json"))

    def _api_v2_live_transcript(self, environ, start_response):
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=False)
        season_id = str((query.get("season_id") or [""])[0])
        run_id = str((query.get("run_id") or [""])[0])
        if not season_id or not run_id:
            raise DashboardError("season_id and run_id are required")
        payload = self._v2_reads().live_transcript(season_id, run_id=run_id)
        return self._response(start_response, 200, payload.model_dump(mode="json"))

    def _api_v2_live_impact_review(self, environ, start_response):
        if self.config.environment != "sandbox":
            raise DashboardError("DASH-05 Live actions are sandbox-only")
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=False)
        season_id = str((query.get("season_id") or [""])[0])
        action = str((query.get("action") or [""])[0])
        if not season_id or season_id == "S01":
            raise DashboardError("DASH-05 rehearsal cannot target S01")
        result = LiveSupervisionService(self.database, clock=self.clock).review(
            season_id=season_id, action=action
        )
        return self._response(start_response, 200, result)

    def _api_v2_live_action(self, environ, start_response):
        if self.config.environment != "sandbox":
            raise DashboardError("DASH-05 Live actions are sandbox-only")
        body = self._json_body(environ)
        season_id = str(body.get("season_id") or "")
        if not season_id or season_id == "S01":
            raise DashboardError("DASH-05 rehearsal cannot target S01")
        def optional_int(name: str) -> int | None:
            value = body.get(name)
            if value is None:
                return None
            try:
                return int(value)
            except (TypeError, ValueError) as exc:
                raise DashboardError(f"{name} must be an integer or null") from exc
        try:
            season_version = int(body.get("expected_season_version"))
        except (TypeError, ValueError) as exc:
            raise DashboardError("expected_season_version is required") from exc
        result = LiveSupervisionService(self.database, clock=self.clock).perform(
            request_id=str(body.get("request_id") or ""), season_id=season_id,
            action=str(body.get("action") or ""),
            snapshot_hash=str(body.get("snapshot_hash") or ""),
            expected_season_version=season_version,
            expected_run_version=optional_int("expected_run_version"),
            expected_recovery_version=optional_int("expected_recovery_version"),
            typed_confirmation=(str(body["typed_confirmation"]) if body.get("typed_confirmation") is not None else None),
        )
        return self._response(start_response, 200, result)

    def _api_v2_seasons(self, environ, start_response):
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=False)
        season_id = self._query_season_id(environ)
        if not season_id:
            raise DashboardError("season_id is required")
        mode = str((query.get("mode") or ["private-close"])[0])
        service = SeasonsService(self.database, self.paths.roots, self.clock)
        if mode == "publication":
            payload = service.publication_preview(season_id=season_id, diary_decisions={})
            payload["mode"] = "publication"
        elif mode == "private-close":
            payload = service.private_close_review(season_id=season_id)
            payload["mode"] = "private-close"
        else:
            raise DashboardError("mode must be private-close or publication")
        return self._response(start_response, 200, payload)

    def _api_v2_private_close(self, environ, start_response):
        body = self._json_body(environ)
        self._require_v2_sandbox_season(body)
        service = SeasonsService(self.database, self.paths.roots, self.clock)
        try:
            expected = int(body.get("expected_season_version"))
        except (TypeError, ValueError) as exc:
            raise DashboardError("expected_season_version is required") from exc
        result = service.private_close(
            request_id=str(body.get("request_id") or ""), season_id=str(body.get("season_id") or ""),
            snapshot_hash=str(body.get("snapshot_hash") or ""), expected_season_version=expected,
            typed_confirmation=str(body.get("typed_confirmation") or ""),
        )
        return self._response(start_response, 200, result)

    def _api_v2_publication_preview(self, environ, start_response):
        body = self._json_body(environ)
        self._require_v2_sandbox_season(body)
        decisions = body.get("diary_decisions") or {}
        if not isinstance(decisions, dict):
            raise DashboardError("diary_decisions must be an object")
        payload = SeasonsService(self.database, self.paths.roots, self.clock).publication_preview(
            season_id=str(body.get("season_id") or ""),
            diary_decisions={str(key): str(value) for key, value in decisions.items()},
        )
        return self._response(start_response, 200, payload)

    def _api_v2_publish_season(self, environ, start_response):
        body = self._json_body(environ)
        self._require_v2_sandbox_season(body)
        decisions = body.get("diary_decisions") or {}
        if not isinstance(decisions, dict):
            raise DashboardError("diary_decisions must be an object")
        try:
            expected = int(body.get("expected_season_version"))
        except (TypeError, ValueError) as exc:
            raise DashboardError("expected_season_version is required") from exc
        result = SeasonsService(self.database, self.paths.roots, self.clock).publish(
            request_id=str(body.get("request_id") or ""), season_id=str(body.get("season_id") or ""),
            snapshot_hash=str(body.get("snapshot_hash") or ""), expected_season_version=expected,
            typed_confirmation=str(body.get("typed_confirmation") or ""),
            diary_decisions={str(key): str(value) for key, value in decisions.items()},
            wellness_confirmed=bool(body.get("wellness_confirmed")),
            privacy_reviewed=bool(body.get("privacy_reviewed")),
            consent_confirmed=bool(body.get("consent_confirmed")),
        )
        return self._response(start_response, 200, result)

    def _require_v2_sandbox_season(self, body: dict[str, object]) -> None:
        if self.config.environment != "sandbox":
            raise DashboardError("DASH-06 Seasons actions are sandbox-only")
        season_id = str(body.get("season_id") or "")
        if not season_id or season_id == "S01":
            raise DashboardError("DASH-06 rehearsal cannot target S01")

    def _api_v2_review_day(self, environ, start_response):
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=False)
        day_value = (query.get("day") or [None])[0]
        day_number = self._day_number(day_value) if day_value is not None else None
        run_id = (query.get("run_id") or [None])[0]
        payload = self._v2_reads().review_day(
            self._query_season_id(environ),
            day_number=day_number,
            run_id=str(run_id) if run_id else None,
        )
        return self._response(start_response, 200, payload.model_dump(mode="json"))

    def _api_v2_diary_attempt(self, environ, start_response):
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=False)
        season_id = (query.get("season_id") or [None])[0]
        diary_id = (query.get("diary_id") or [None])[0]
        if not season_id or not diary_id:
            raise DashboardError("season_id and diary_id are required")
        payload = self._v2_reads().diary_attempt(
            str(season_id), diary_id=str(diary_id)
        )
        return self._response(start_response, 200, payload.model_dump(mode="json"))

    def _api_v2_diagnostics(self, environ, start_response, *, call_id: str | None = None):
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=False)
        attempt_value = (query.get("attempt") or [None])[0]
        attempt = None
        if attempt_value is not None:
            try:
                attempt = int(attempt_value)
            except (TypeError, ValueError) as exc:
                raise DashboardError("attempt must be a positive integer") from exc
            if attempt < 1:
                raise DashboardError("attempt must be a positive integer")
        value = lambda name: str(query[name][0]) if query.get(name) else None
        payload = self._v2_reads().diagnostics(
            self._query_season_id(environ), call_id=call_id or value("call_id"),
            run_id=value("run_id"), character_id=value("character_id"),
            purpose=value("purpose"), status=value("status"), attempt=attempt,
            error=value("error"),
        )
        return self._response(start_response, 200, payload.model_dump(mode="json"))

    def _api_v2_call_raw(self, environ, start_response):
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=False)
        season_id = (query.get("season_id") or [None])[0]
        call_id = (query.get("call_id") or [None])[0]
        if not season_id or not call_id:
            raise DashboardError("season_id and call_id are required")
        payload = self._v2_reads().call_raw(str(season_id), call_id=str(call_id))
        return self._response(start_response, 200, payload.model_dump(mode="json"))

    def _v2_reads(self) -> DashboardReadModels:
        return DashboardReadModels(
            self.database,
            paths=self.paths,
            environment=self.config.environment,
            now=self.clock.now(),
        )

    @staticmethod
    def _query_season_id(environ) -> str | None:
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=False)
        value = (query.get("season_id") or [None])[0]
        return str(value) if value else None

    def _asset(self, start_response, name: str):
        asset = static_asset(name)
        if asset is None:
            return self._response(start_response, 404, {"error": "not found"})
        content, content_type = asset
        return self._response(start_response, 200, content, content_type=content_type)

    def _api_status(self, start_response):
        return self._response(
            start_response,
            200,
            read_service_status(self.database, paths=self.paths, now=self.clock.now()),
        )

    def _api_diaries(self, environ, start_response):
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=False)
        season_id = (query.get("season_id") or [None])[0]
        if not season_id:
            raise DashboardError("season_id is required")
        day_number = (query.get("day") or [None])[0]
        parsed_day = self._day_number(day_number) if day_number is not None else None
        records = RecordRepository(self.database)
        rows = records.list_diaries(
            season_id=season_id,
            day_number=parsed_day,
        )
        diaries = [self._diary_review_item(row) for row in rows]
        return self._response(start_response, 200, {"season_id": season_id, "diaries": diaries})

    def _api_day_review(self, environ, start_response):
        """Return one creator-only day of durable script and diary review material."""
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=False)
        season_id = (query.get("season_id") or [None])[0]
        if not season_id:
            raise DashboardError("season_id is required")
        day_value = (query.get("day") or [None])[0]
        if day_value is None:
            raise DashboardError("day is required")
        day_number = self._day_number(day_value)
        season = self._season_for_review(season_id)
        connection = self.database.connection
        day = connection.execute(
            "SELECT original_date, cutoff_at, closed FROM days WHERE season_id = ? AND day_number = ?",
            (season_id, day_number),
        ).fetchone()
        cast_names = {
            str(row["character_id"]): str(row["name"])
            for row in connection.execute(
                "SELECT character_id, name FROM cast_members WHERE season_id = ?",
                (season_id,),
            )
        }
        run_rows = connection.execute(
            "SELECT r.run_id, r.status, r.turn_count, r.completion_reason, r.delay, "
            "s.slot_number, s.run_number, s.scheduled_local "
            "FROM runs r JOIN schedule_slots s ON s.slot_id = r.slot_id "
            "WHERE r.season_id = ? AND s.day_number = ? ORDER BY s.slot_number",
            (season_id, day_number),
        ).fetchall()
        runs = []
        script_sections: list[str] = []
        for row in run_rows:
            script = self._run_review_script(str(row["run_id"]), cast_names)
            runs.append(
                {
                    "run_id": str(row["run_id"]),
                    "run_number": int(row["run_number"]),
                    "slot_number": int(row["slot_number"]),
                    "status": str(row["status"]),
                    "turn_count": int(row["turn_count"]),
                    "completion_reason": row["completion_reason"],
                    "delay": row["delay"],
                    "scheduled_local": str(row["scheduled_local"]),
                    "script_available": bool(script),
                }
            )
            if script:
                script_sections.append(
                    f"RUN {row['run_number']} · SLOT {row['slot_number']} · {row['status']}\n\n{script}"
                )

        opening = season.opening
        opening_section = ""
        if opening is not None:
            rules = "; ".join(opening.world_rules) if opening.world_rules else "(none stated)"
            opening_section = (
                f"Set: {opening.set}\nSetting: {opening.setting}\n"
                f"Cast: {', '.join(opening.cast)}\nWorld rules: {rules}"
            )
        shared_script = "\n\n".join(
            part for part in (opening_section, *script_sections) if part
        )
        records = RecordRepository(self.database)
        diaries = [
            self._diary_review_item(row)
            for row in records.list_diaries(season_id=season_id, day_number=day_number)
        ]
        return self._response(
            start_response,
            200,
            {
                "season_id": season_id,
                "day_number": day_number,
                "original_date": str(day["original_date"]) if day is not None else None,
                "cutoff_at": day["cutoff_at"] if day is not None else None,
                "closed": bool(day["closed"]) if day is not None else False,
                "runs": runs,
                "shared_script": shared_script or None,
                "diaries": diaries,
            },
        )

    def _season_for_review(self, season_id: str):
        exists = self.database.connection.execute(
            "SELECT 1 FROM seasons WHERE season_id = ?", (season_id,)
        ).fetchone()
        if exists is None:
            raise DashboardError(f"unknown season: {season_id}")
        return SeasonRepository(self.database).get(season_id)

    @staticmethod
    def _day_number(value: str) -> int:
        try:
            day_number = int(value)
        except (TypeError, ValueError) as exc:
            raise DashboardError("day must be an integer from 1 through 7") from exc
        if day_number not in range(1, 8):
            raise DashboardError("day must be an integer from 1 through 7")
        return day_number

    def _diary_review_item(self, row) -> dict[str, object]:
        """Expose accepted diary text or its owner-only private model output.

        A wellness-marked diary intentionally has no accepted ``content_path``.
        The owner's review surface may still inspect the attempt without changing
        its PRIVATE status or making it eligible for publication.
        """
        item: dict[str, object] = {
            "diary_id": str(row["diary_id"]),
            "character_id": str(row["character_id"]),
            "day_number": int(row["day_number"]),
            "chosen_slot_number": row["chosen_slot_number"],
            "status": str(row["status"]),
            "late": bool(row["late"]),
            "word_count": row["word_count"],
            "content": None,
            "raw_output": None,
            "review_source": "NO_CONTENT",
            "wellness_flag": False,
            "model_attempt": None,
            "model_call_status": None,
        }
        if row["content_path"]:
            item["content"] = self._private_text(str(row["content_path"]))
            item["review_source"] = "ACCEPTED_DIARY"
            return item

        model_call = self.database.connection.execute(
            "SELECT attempt, status, output_path FROM model_calls "
            "WHERE run_id IS NULL AND purpose LIKE ? AND output_path IS NOT NULL "
            "ORDER BY attempt DESC, ended_at DESC LIMIT 1",
            (
                f"diary:{row['season_id']}:{row['character_id']}:day:{row['day_number']}:slot:%",
            ),
        ).fetchone()
        if model_call is None:
            return item

        raw_output = self._private_text(str(model_call["output_path"]))
        item["raw_output"] = raw_output
        item["model_attempt"] = int(model_call["attempt"])
        item["model_call_status"] = str(model_call["status"])
        try:
            envelope = parse_diary_output(raw_output)
        except StructuredOutputError:
            item["content"] = raw_output
            item["wellness_flag"] = "<WELLNESS_SIGNAL>" in raw_output
            item["review_source"] = "PRIVATE_MODEL_OUTPUT"
            return item

        item["content"] = envelope.text.strip() or raw_output
        item["wellness_flag"] = bool(envelope.wellness_signal)
        item["review_source"] = (
            "PRIVATE_WELLNESS_OUTPUT" if envelope.wellness_signal else "PRIVATE_MODEL_OUTPUT"
        )
        return item

    def _run_review_script(self, run_id: str, cast_names: dict[str, str]) -> str:
        sections: list[str] = []
        rows = self.database.connection.execute(
            "SELECT character_id, disposition, content_path FROM turns "
            "WHERE run_id = ? ORDER BY round_number, turn_id",
            (run_id,),
        ).fetchall()
        for row in rows:
            if not row["content_path"]:
                continue
            content = self._private_text(str(row["content_path"]))
            disposition = str(row["disposition"])
            if disposition in {"NARRATION_ACCEPT", "NEUTRAL_INTERRUPTION"}:
                sections.append(content)
            elif disposition in {"ACCEPT", "ACCEPT_AFTER_CORRECTION"}:
                speaker = cast_names.get(str(row["character_id"]), str(row["character_id"]))
                sections.append(f"{speaker}: {content}")
        return "\n\n".join(sections)

    def _api_recover(self, environ, start_response):
        body = self._json_body(environ)
        required = ("season_id", "run_id", "decision")
        if any(not body.get(key) for key in required):
            raise DashboardError("season_id, run_id, and decision are required")
        decision = str(body["decision"])
        if decision not in {"retry", "skip", "end"}:
            raise DashboardError("decision must be retry, skip, or end")
        result = CommandBus(self.database).execute(
            ResolveRecovery(
                request_id=str(body.get("request_id") or secrets.token_urlsafe(18)),
                season_id=str(body["season_id"]),
                run_id=str(body["run_id"]),
                decision=decision,
            )
        )
        return self._response(start_response, 200, result.payload)

    def _api_publish(self, environ, start_response):
        body = self._json_body(environ)
        season_id = str(body.get("season_id") or "")
        if not season_id:
            raise DashboardError("season_id is required")
        service = PublicationService(database=self.database, roots=self.paths.roots, clock=self.clock)
        decisions = body.get("diary_decisions") or {}
        if not isinstance(decisions, dict):
            raise DashboardError("diary_decisions must be an object")
        publication_id = body.get("publication_id")
        if publication_id:
            if not decisions:
                raise DashboardError("publication revision requires diary_decisions")
            result = None
            for diary_id, decision in decisions.items():
                result = service.review_diary(
                    publication_id=str(publication_id),
                    diary_id=str(diary_id),
                    decision=str(decision),
                )
            assert result is not None
            result = service.publish(publication_id=str(publication_id))
        else:
            if not all(
                bool(body.get(key))
                for key in ("wellness_confirmed", "privacy_reviewed", "consent_confirmed")
            ):
                raise DashboardError("all three publication confirmations are required")
            review = service.begin_review(
                season_id=season_id,
                wellness_confirmed=True,
                privacy_reviewed=True,
                consent_confirmed=True,
                diary_decisions={str(key): str(value) for key, value in decisions.items()},
            )
            if review.status != "CLEARED":
                return self._response(
                    start_response,
                    409,
                    {
                        "publication_id": review.publication_id,
                        "status": review.status,
                        "eligible_diary_ids": list(review.eligible_diary_ids),
                    },
                )
            result = service.publish(publication_id=review.publication_id)
        return self._response(start_response, 200, _publication_payload(result))

    def _private_text(self, raw_path: str) -> str:
        path = os.path.abspath(os.path.expanduser(raw_path))
        private = os.path.abspath(str(self.paths.roots.private))
        try:
            within_private = os.path.commonpath((path, private)) == private
        except ValueError:
            within_private = False
        if not within_private:
            raise DashboardError("private artifact path escaped configured root")
        return open(path, encoding="utf-8").read()

    def _require_csrf(self, environ, expected: str) -> None:
        supplied = str(environ.get("HTTP_X_CSRF_TOKEN", ""))
        if not supplied:
            supplied = self._body_fields(environ).get("csrf_token", "")
        if not hmac.compare_digest(supplied, expected):
            raise DashboardError("invalid CSRF token")

    @staticmethod
    def _cookie(environ, name: str) -> str | None:
        cookie = SimpleCookie()
        cookie.load(str(environ.get("HTTP_COOKIE", "")))
        morsel = cookie.get(name)
        return morsel.value if morsel is not None else None

    @staticmethod
    def _body_bytes(environ) -> bytes:
        try:
            length = int(environ.get("CONTENT_LENGTH") or "0")
        except ValueError as exc:
            raise DashboardError("invalid content length") from exc
        if length > 1_000_000:
            raise DashboardError("request body is too large")
        return environ["wsgi.input"].read(length)

    def _json_body(self, environ) -> dict[str, object]:
        try:
            body = json.loads(self._body_bytes(environ) or b"{}")
        except (TypeError, ValueError) as exc:
            raise DashboardError("request body must be JSON") from exc
        if not isinstance(body, dict):
            raise DashboardError("request body must be an object")
        return body

    def _body_fields(self, environ) -> dict[str, str]:
        body = self._body_bytes(environ).decode("utf-8")
        return {key: values[-1] for key, values in parse_qs(body).items() if values}

    @staticmethod
    def _response(
        start_response,
        status: int,
        payload: object,
        *,
        headers: list[tuple[str, str]] | None = None,
        content_type: str = "application/json",
    ):
        if isinstance(payload, bytes):
            content = payload
        elif content_type == "text/html":
            content = str(payload).encode("utf-8")
        else:
            content = (json.dumps(payload, sort_keys=True, default=str) + "\n").encode("utf-8")
        response_headers = [
            ("Content-Type", f"{content_type}; charset=utf-8"),
            ("Content-Length", str(len(content))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
            ("X-Frame-Options", "DENY"),
            ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
            (
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'self'",
            ),
        ]
        response_headers.extend(headers or [])
        start_response(f"{status} {HTTPStatus(status).phrase}", response_headers)
        return [content]

    def _unauthorized(self, start_response):
        return self._response(
            start_response,
            401,
            {"error": "login required"},
            headers=[("WWW-Authenticate", 'Session realm="improv"')],
        )


def _publication_payload(result) -> dict[str, object]:
    return {
        "publication_id": result.publication_id,
        "version": result.version,
        "status": result.status,
        "eligible_diary_ids": list(result.eligible_diary_ids),
        "output_path": result.output_path,
        "manifest_sha256": result.manifest_sha256,
    }


class QuietWSGIRequestHandler(WSGIRequestHandler):
    """Keep dashboard requests out of the service's normal stdout log."""

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        return


def serve_dashboard(
    app: DashboardApplication,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> WSGIServer:
    """Serve the dashboard until the caller shuts down the returned server."""
    return make_server(host, port, app, server_class=WSGIServer, handler_class=QuietWSGIRequestHandler)


__all__ = [
    "DashboardApplication",
    "DashboardAuth",
    "DashboardConfig",
    "DashboardError",
    "hash_password",
    "serve_dashboard",
]
