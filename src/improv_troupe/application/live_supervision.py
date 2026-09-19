"""Consequence-first owner controls for dashboard v2 Live."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..clock import Clock, SystemClock
from ..domain import SeasonStatus
from ..infrastructure import SQLiteDatabase
from .commands import CommandBus, CommandError, ControlSeason, ResolveRecovery


class LiveSupervisionError(CommandError):
    """Raised when a reviewed Live action is stale or invalid."""


class LiveSupervisionService:
    """Review and execute version-bound creator controls with durable receipts."""

    def __init__(self, database: SQLiteDatabase, *, clock: Clock | None = None) -> None:
        self.database = database
        self.clock = clock or SystemClock()

    def review(self, *, season_id: str, action: str) -> dict[str, Any]:
        if action not in {"pause", "resume", "retry", "skip", "private_close"}:
            raise LiveSupervisionError("unknown Live action")
        snapshot = self._snapshot(season_id=season_id, action=action)
        consequences, confirmation, executable = self._consequences(snapshot, action)
        return {
            "action": action,
            "title": {
                "pause": "Pause after current durable checkpoint",
                "resume": "Resume durable queue processing",
                "retry": "Retry the failed run before later work",
                "skip": "Skip this run and preserve the gap",
                "private_close": "Review a private season close",
            }[action],
            "consequences": consequences,
            "typed_confirmation": confirmation,
            "executable": executable,
            "private_close_href": (
                f"/v2/seasons?season_id={season_id}&mode=private-close" if action == "private_close" else None
            ),
            "snapshot": snapshot,
            "snapshot_hash": _snapshot_hash(snapshot),
            "reviewed_at": self.clock.now().isoformat(),
        }

    def perform(
        self,
        *,
        request_id: str,
        season_id: str,
        action: str,
        snapshot_hash: str,
        expected_season_version: int,
        expected_run_version: int | None,
        expected_recovery_version: int | None,
        typed_confirmation: str | None,
    ) -> dict[str, Any]:
        if not request_id.strip():
            raise LiveSupervisionError("request_id is required")
        if action == "private_close":
            raise LiveSupervisionError("private close is reviewed in Seasons; Recovery cannot submit it")
        with self.database.transaction():
            bus = CommandBus(self.database, clock=self.clock)
            command = self._command(
                request_id=request_id, season_id=season_id, action=action,
                expected_season_version=expected_season_version,
                expected_run_version=expected_run_version,
                expected_recovery_version=expected_recovery_version,
                snapshot_hash=snapshot_hash,
            )
            if bus.requests.get(request_id) is not None:
                result = bus.execute(command)
                return self._receipt(
                    request_id=request_id, action=action, snapshot_hash=snapshot_hash,
                    expected_season_version=expected_season_version,
                    expected_run_version=expected_run_version,
                    expected_recovery_version=expected_recovery_version,
                    replayed=result.replayed, payload=result.payload,
                )
            review = self.review(season_id=season_id, action=action)
            snapshot = dict(review["snapshot"])
            if snapshot_hash != review["snapshot_hash"]:
                raise LiveSupervisionError("impact review is stale; reopen it before confirming")
            if expected_season_version != int(snapshot["season_version"]):
                raise LiveSupervisionError("season changed after impact review")
            if expected_run_version != snapshot["run_version"]:
                raise LiveSupervisionError("run changed after impact review")
            if expected_recovery_version != snapshot["recovery_version"]:
                raise LiveSupervisionError("recovery changed after impact review")
            required = review["typed_confirmation"]
            if required is not None and typed_confirmation != required:
                raise LiveSupervisionError("typed confirmation does not match the reviewed action")

            result = bus.execute(command)
            return self._receipt(
                request_id=request_id, action=action, snapshot_hash=snapshot_hash,
                expected_season_version=expected_season_version,
                expected_run_version=expected_run_version,
                expected_recovery_version=expected_recovery_version,
                replayed=result.replayed, payload=result.payload,
            )

    def _command(
        self, *, request_id: str, season_id: str, action: str,
        expected_season_version: int, expected_run_version: int | None,
        expected_recovery_version: int | None, snapshot_hash: str,
    ) -> ControlSeason | ResolveRecovery:
        if action in {"pause", "resume"}:
            target = SeasonStatus.PAUSED if action == "pause" else SeasonStatus.RUNNING
            return ControlSeason(
                request_id=request_id, season_id=season_id, target=target,
                expected_version=expected_season_version, review_snapshot_hash=snapshot_hash,
            )
        if action not in {"retry", "skip"}:
            raise LiveSupervisionError("unknown executable Live action")
        recovery = self.database.connection.execute(
            "SELECT run_id FROM recovery_requests WHERE season_id = ? ORDER BY created_at DESC LIMIT 1",
            (season_id,),
        ).fetchone()
        run_id = str(recovery["run_id"]) if recovery is not None else ""
        return ResolveRecovery(
            request_id=request_id, season_id=season_id, run_id=run_id, decision=action,
            expected_season_version=expected_season_version,
            expected_run_version=expected_run_version,
            expected_recovery_version=expected_recovery_version,
            review_snapshot_hash=snapshot_hash,
        )

    def _receipt(
        self, *, request_id: str, action: str, snapshot_hash: str,
        expected_season_version: int, expected_run_version: int | None,
        expected_recovery_version: int | None, replayed: bool, payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
                "receipt_id": request_id,
                "action": action,
                "replayed": replayed,
                "review_snapshot_hash": snapshot_hash,
                "reviewed_versions": {
                    "season": expected_season_version,
                    "run": expected_run_version,
                    "recovery": expected_recovery_version,
                },
                "result": payload,
                "created_at": self.clock.now().isoformat(),
            }

    def _snapshot(self, *, season_id: str, action: str) -> dict[str, Any]:
        season = self.database.connection.execute(
            "SELECT season_id, status, version FROM seasons WHERE season_id = ?", (season_id,)
        ).fetchone()
        if season is None:
            raise LiveSupervisionError("selected season does not exist")
        status = str(season["status"])
        allowed = {
            "pause": {"RUNNING"}, "resume": {"PAUSED"},
            "retry": {"RECOVERY_REQUIRED"}, "skip": {"RECOVERY_REQUIRED"},
            "private_close": {"RECOVERY_REQUIRED"},
        }[action]
        if status not in allowed:
            raise LiveSupervisionError(f"{action} is not valid while the season is {status}")
        recovery = None
        run = None
        if action in {"retry", "skip", "private_close"}:
            recovery = self.database.connection.execute(
                "SELECT * FROM recovery_requests WHERE season_id = ? AND status IN "
                "('RECOVERY_REQUIRED','WAITING_FOR_MODEL') ORDER BY created_at DESC LIMIT 1",
                (season_id,),
            ).fetchone()
            if recovery is None:
                raise LiveSupervisionError("no active recovery is stored")
            run = self.database.connection.execute(
                "SELECT run_id, status, version, turn_count FROM runs WHERE run_id = ?",
                (str(recovery["run_id"]),),
            ).fetchone()
            if run is None or str(run["status"]) != "RECOVERY_REQUIRED":
                raise LiveSupervisionError("the recovery run is no longer actionable")
        elif action in {"pause", "resume"}:
            run = self.database.connection.execute(
                "SELECT run_id, status, version, turn_count FROM runs WHERE season_id = ? "
                "AND status IN ('RUNNING','WAITING_FOR_MODEL') ORDER BY run_id LIMIT 1",
                (season_id,),
            ).fetchone()
        last = self.database.connection.execute(
            "SELECT t.turn_id, t.accepted_sequence, t.accepted_at FROM turns t JOIN runs r "
            "ON r.run_id = t.run_id WHERE r.season_id = ? AND t.disposition IN "
            "('ACCEPT','ACCEPT_AFTER_CORRECTION','NARRATION_ACCEPT','NEUTRAL_INTERRUPTION') "
            "ORDER BY t.accepted_at DESC, t.rowid DESC LIMIT 1",
            (season_id,),
        ).fetchone()
        queued = int(self.database.connection.execute(
            "SELECT COUNT(*) FROM work_items WHERE status = 'QUEUED' "
            "AND json_extract(payload_json, '$.season_id') = ?", (season_id,)
        ).fetchone()[0])
        return {
            "season_id": season_id,
            "season_status": status,
            "season_version": int(season["version"]),
            "run_id": str(run["run_id"]) if run is not None else None,
            "run_status": str(run["status"]) if run is not None else None,
            "run_version": int(run["version"]) if run is not None else None,
            "recovery_id": str(recovery["recovery_id"]) if recovery is not None else None,
            "recovery_status": str(recovery["status"]) if recovery is not None else None,
            "recovery_version": int(recovery["version"]) if recovery is not None else None,
            "accepted_anchor": str(last["turn_id"]) if last is not None else None,
            "accepted_sequence": int(last["accepted_sequence"]) if last is not None and last["accepted_sequence"] is not None else None,
            "queued_work_count": queued,
        }

    @staticmethod
    def _consequences(snapshot: dict[str, Any], action: str) -> tuple[list[str], str | None, bool]:
        run_id = str(snapshot.get("run_id") or "the active run")
        if action == "pause":
            return (["The current durable checkpoint remains accepted.", "No new queued work will begin until you resume.", "Closing this dashboard does not pause the worker."], None, True)
        if action == "resume":
            return (["Due durable work may be claimed again.", "Accepted story records are unchanged.", "The queue keeps its stored ordering."], None, True)
        if action == "retry":
            return ([f"{run_id} returns to QUEUED.", "A new attempt is inserted ahead of later queue work.", "The failed call and accepted causal anchor remain preserved."], None, True)
        if action == "skip":
            return ([f"{run_id} becomes SKIPPED and will not be regenerated.", "The gap remains visible in review.", "Later queued work may proceed; accepted material is unchanged."], f"SKIP {run_id}", True)
        return (["No recovery decision is submitted here.", "The private close review will explain diary, handoff, and publication consequences.", "The season remains in recovery until that later review is explicitly completed."], None, False)


def _snapshot_hash(snapshot: dict[str, Any]) -> str:
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = ["LiveSupervisionError", "LiveSupervisionService"]
