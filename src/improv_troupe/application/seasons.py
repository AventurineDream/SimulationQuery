"""Sandbox-safe private close and separate publication review controls."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..clock import Clock, SystemClock
from ..domain import SeasonStatus, transition_season
from ..infrastructure import DataRoots, EventRepository, OptimisticConcurrencyError, SeasonRepository, SQLiteDatabase
from .publication import PublicationError, PublicationService


class SeasonsError(RuntimeError):
    """Raised when an operator review is stale, unsafe, or incomplete."""


@dataclass
class SeasonsService:
    """Make close/release decisions versioned, explicit, and replay-safe."""

    database: SQLiteDatabase
    roots: DataRoots
    clock: Clock = field(default_factory=SystemClock)

    def __post_init__(self) -> None:
        self.roots.prepare()
        self.seasons = SeasonRepository(self.database)
        self.events = EventRepository(self.database)

    def private_close_review(self, *, season_id: str) -> dict[str, Any]:
        snapshot = self._closure_snapshot(season_id)
        return {
            "mode": "private_close",
            "executable": snapshot["season_status"] in {"ARMED", "RUNNING", "PAUSED", "RECOVERY_REQUIRED"},
            "typed_confirmation": f"end {season_id} privately",
            "snapshot": snapshot,
            "snapshot_hash": _hash(snapshot),
            "effects": {
                "will": [
                    "stop later scheduled attempts",
                    "preserve all private evidence",
                    "record a closure receipt and verified handoff",
                    "record terminal PRIVATE_COMPLETE state",
                ],
                "will_not": ["publish", "expose", "delete", "rewrite", "or clear evidence"],
            },
        }

    def private_close(
        self,
        *,
        request_id: str,
        season_id: str,
        snapshot_hash: str,
        expected_season_version: int,
        typed_confirmation: str,
    ) -> dict[str, Any]:
        if not request_id:
            raise SeasonsError("private close requires a request id")
        fingerprint = _hash({
            "action": "private_close", "season_id": season_id, "snapshot_hash": snapshot_hash,
            "expected_season_version": expected_season_version, "typed_confirmation": typed_confirmation,
        })
        with self.database.transaction() as connection:
            replay = self._replay(request_id, "private_close", fingerprint)
            if replay is not None:
                return replay
            review = self.private_close_review(season_id=season_id)
            snapshot = review["snapshot"]
            if typed_confirmation != review["typed_confirmation"]:
                raise SeasonsError("typed private-close confirmation does not match")
            if snapshot_hash != review["snapshot_hash"]:
                raise SeasonsError("private-close snapshot is stale; reopen the review")
            if expected_season_version != int(snapshot["season_version"]):
                raise SeasonsError("season changed after private-close review")
            if not review["executable"]:
                raise SeasonsError("private close is not valid from the current season state")
            active_leases = int(snapshot["work"]["active_leases"])
            if active_leases:
                raise SeasonsError("private close waits for active leased work to settle")
            now = self.clock.now().isoformat()
            self._store_closure_snapshot(snapshot_hash, snapshot, now)
            season = self.seasons.get(season_id)
            closing = transition_season(season, SeasonStatus.CLOSING)
            try:
                self.seasons.update(closing, expected_version=season.version, now=self.clock.now())
            except OptimisticConcurrencyError as exc:
                raise SeasonsError("season changed while private-close review was open") from exc
            connection.execute(
                "UPDATE runs SET status = 'INTERRUPTED', completion_reason = 'private_close_stopped', "
                "version = version + 1 WHERE season_id = ? AND status = 'QUEUED'",
                (season_id,),
            )
            connection.execute(
                "UPDATE work_items SET status = 'CANCELLED_PRIVATE_CLOSE', completed_at = ?, "
                "lease_owner = NULL, lease_until = NULL WHERE status = 'QUEUED' "
                "AND json_extract(payload_json, '$.season_id') = ?",
                (now, season_id),
            )
            completed = transition_season(closing, SeasonStatus.PRIVATE_COMPLETE)
            try:
                self.seasons.update(completed, expected_version=closing.version, now=self.clock.now())
            except OptimisticConcurrencyError as exc:
                raise SeasonsError("season changed while private close was completing") from exc
            archive_after = _tree_hash(self.roots.private)
            if archive_after != str(snapshot["private_archive_sha256"]):
                raise SeasonsError("private archive changed during private close")
            receipt_id = f"{season_id}:private-close:{request_id}"
            handoff_id = f"{season_id}:handoff:{request_id}"
            unresolved = self._unresolved(season_id)
            connection.execute(
                "INSERT INTO closure_receipts(receipt_id, request_id, season_id, snapshot_hash, "
                "season_version_before, season_version_after, private_archive_sha256_before, "
                "private_archive_sha256_after, handoff_id, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PRIVATE_COMPLETE', ?)",
                (receipt_id, request_id, season_id, snapshot_hash, expected_season_version,
                 completed.version, snapshot["private_archive_sha256"], archive_after, handoff_id, now),
            )
            connection.execute(
                "INSERT INTO closure_handoffs(handoff_id, season_id, receipt_id, status, detail_json, verified_at) "
                "VALUES (?, ?, ?, 'VERIFIED', ?, ?)",
                (handoff_id, season_id, receipt_id, json.dumps({"unresolved": unresolved}, sort_keys=True), now),
            )
            self.events.append(
                event_id=f"private-close:{request_id}", natural_key=f"private-close:{request_id}",
                aggregate_type="season", aggregate_id=season_id, event_type="SeasonPrivateComplete",
                payload={"receipt_id": receipt_id, "handoff_id": handoff_id, "unresolved": unresolved},
            )
            response = {
                "receipt_id": receipt_id, "season_id": season_id, "status": "PRIVATE_COMPLETE",
                "season_version": completed.version, "snapshot_hash": snapshot_hash,
                "handoff": {"handoff_id": handoff_id, "status": "VERIFIED"},
                "unresolved": unresolved, "private_archive_sha256": archive_after,
                "replayed": False,
            }
            self._store_action(request_id, "private_close", fingerprint, response, now)
            return response

    def publication_preview(self, *, season_id: str, diary_decisions: dict[str, str]) -> dict[str, Any]:
        season = self.seasons.get(season_id)
        if season.status is not SeasonStatus.PRIVATE_COMPLETE:
            raise SeasonsError("publication review requires PRIVATE_COMPLETE")
        closure = self.database.connection.execute(
            "SELECT * FROM closure_receipts WHERE season_id = ? AND status = 'PRIVATE_COMPLETE' "
            "ORDER BY created_at DESC LIMIT 1", (season_id,)
        ).fetchone()
        if closure is None:
            raise SeasonsError("publication review requires a verified private-close receipt")
        diary_rows = self.database.connection.execute(
            "SELECT diary_id, day_number, character_id, status, content_path FROM diaries WHERE season_id = ? "
            "ORDER BY day_number, character_id", (season_id,)
        ).fetchall()
        known = {str(row["diary_id"]) for row in diary_rows}
        if set(diary_decisions) - known:
            raise SeasonsError("publication preview names an unknown diary")
        allowed: list[dict[str, Any]] = []
        excluded: list[dict[str, str]] = []
        resolved_decisions: dict[str, str] = {}
        for row in diary_rows:
            diary_id = str(row["diary_id"])
            status = str(row["status"])
            decision = str(diary_decisions.get(diary_id, "PRIVATE"))
            if decision not in {"CLEARED", "PRIVATE"}:
                raise SeasonsError("diary decisions must be CLEARED or PRIVATE")
            if decision == "CLEARED" and status not in {"WRITTEN", "LATE"}:
                raise SeasonsError(f"{diary_id} cannot enter a public projection")
            resolved_decisions[diary_id] = decision
            if decision == "CLEARED":
                content_path = row["content_path"]
                if not content_path:
                    raise SeasonsError(f"cleared diary has no private content: {diary_id}")
                try:
                    source = Path(str(content_path)).expanduser().resolve(strict=True)
                    content = source.read_bytes()
                except OSError as exc:
                    raise SeasonsError(f"cleared diary is not readable: {diary_id}") from exc
                try:
                    source.relative_to(self.roots.private)
                except ValueError as exc:
                    raise SeasonsError(f"diary source is outside private archive: {diary_id}") from exc
                relative = f"diaries/day-{int(row['day_number']):02d}/{row['character_id']}.md"
                allowed.append({
                    "diary_id": diary_id, "day_number": int(row["day_number"]),
                    "character_id": str(row["character_id"]), "path": relative,
                    "sha256": hashlib.sha256(content).hexdigest(), "content": content.decode("utf-8"),
                })
            else:
                excluded.append({"diary_id": diary_id, "reason": f"{status.lower()} or private by creator decision"})
        version = int(self.database.connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM publications WHERE season_id = ?", (season_id,)
        ).fetchone()[0])
        pending_calls = int(self.database.connection.execute(
            "SELECT COUNT(*) FROM model_calls WHERE status IN ('PENDING', 'STREAMING', 'VALIDATING', 'WAITING_FOR_MODEL', 'MANUAL_REVIEW') "
            "AND (run_id IN (SELECT run_id FROM runs WHERE season_id = ?) OR purpose LIKE ? OR purpose LIKE ? OR purpose LIKE ?)",
            (season_id, f"diary:{season_id}:%", f"next-day-direction:{season_id}:%", f"orientation:{season_id}:%"),
        ).fetchone()[0])
        manifest = {
            "season_id": season_id, "publication_version": version,
            "diaries": [{key: item[key] for key in ("diary_id", "day_number", "character_id", "path", "sha256")} for item in allowed],
        }
        snapshot = {
            "season_id": season_id, "season_version": season.version,
            "closure_receipt_id": str(closure["receipt_id"]),
            "closure_snapshot_hash": str(closure["snapshot_hash"]),
            "private_archive_sha256": _tree_hash(self.roots.private),
            "projection_version": version, "manifest": manifest,
            "eligible_diary_ids": [item["diary_id"] for item in allowed],
            "resolved_diary_decisions": resolved_decisions,
            "pending_model_calls": pending_calls,
            "publication_eligible": pending_calls == 0,
            "excluded": excluded,
        }
        return {"snapshot": snapshot, "snapshot_hash": _hash(snapshot), "preview": {"manifest": manifest, "diaries": allowed, "excluded": excluded}}

    def publish(
        self,
        *,
        request_id: str, season_id: str, snapshot_hash: str, expected_season_version: int,
        typed_confirmation: str, diary_decisions: dict[str, str],
        wellness_confirmed: bool, privacy_reviewed: bool, consent_confirmed: bool,
    ) -> dict[str, Any]:
        if not request_id:
            raise SeasonsError("publication requires a request id")
        fingerprint = _hash({
            "action": "publish", "season_id": season_id, "snapshot_hash": snapshot_hash,
            "expected_season_version": expected_season_version, "typed_confirmation": typed_confirmation,
            "diary_decisions": diary_decisions, "wellness_confirmed": wellness_confirmed,
            "privacy_reviewed": privacy_reviewed, "consent_confirmed": consent_confirmed,
        })
        with self.database.transaction():
            replay = self._replay(request_id, "publish", fingerprint)
            if replay is not None:
                return replay
            preview = self.publication_preview(season_id=season_id, diary_decisions=diary_decisions)
            snapshot = preview["snapshot"]
            if typed_confirmation != f"publish {season_id}":
                raise SeasonsError("typed publication confirmation does not match")
            if snapshot_hash != preview["snapshot_hash"]:
                raise SeasonsError("publication preview is stale; reopen the review")
            if expected_season_version != int(snapshot["season_version"]):
                raise SeasonsError("season changed after publication preview")
            if not all((wellness_confirmed, privacy_reviewed, consent_confirmed)):
                raise SeasonsError("wellness, privacy, and consent confirmations are required")
            private_before = str(snapshot["private_archive_sha256"])
            service = PublicationService(database=self.database, roots=self.roots, clock=self.clock)
            try:
                review = service.begin_review(
                    season_id=season_id, wellness_confirmed=True, privacy_reviewed=True,
                    consent_confirmed=True, diary_decisions=snapshot["resolved_diary_decisions"],
                )
                if review.status != "CLEARED":
                    raise SeasonsError("publication review still has unresolved diary decisions")
                result = service.publish(publication_id=review.publication_id)
            except PublicationError as exc:
                raise SeasonsError(str(exc)) from exc
            private_after = _tree_hash(self.roots.private)
            if private_after != private_before:
                raise SeasonsError("publication changed the private archive")
            manifest_path = Path(str(result.output_path)) / "manifest.json"
            actual_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if actual_manifest != snapshot["manifest"]:
                raise SeasonsError("generated publication does not match its reviewed preview")
            now = self.clock.now().isoformat()
            response = {
                "receipt_id": f"{season_id}:publication:{request_id}", "season_id": season_id,
                "publication_id": result.publication_id, "status": result.status,
                "version": result.version, "snapshot_hash": snapshot_hash,
                "manifest_sha256": result.manifest_sha256, "private_archive_sha256": private_after,
                "eligible_diary_ids": list(result.eligible_diary_ids), "replayed": False,
            }
            self._store_action(request_id, "publish", fingerprint, response, now)
            return response

    def _closure_snapshot(self, season_id: str) -> dict[str, Any]:
        season = self.seasons.get(season_id)
        runs = self.database.connection.execute(
            "SELECT status, COUNT(*) AS count FROM runs WHERE season_id = ? GROUP BY status", (season_id,)
        ).fetchall()
        calls = self.database.connection.execute(
            "SELECT status, COUNT(*) AS count FROM model_calls WHERE run_id IN "
            "(SELECT run_id FROM runs WHERE season_id = ?)", (season_id,)
        ).fetchall()
        diaries = self.database.connection.execute(
            "SELECT status, COUNT(*) AS count FROM diaries WHERE season_id = ? GROUP BY status", (season_id,)
        ).fetchall()
        cast = int(self.database.connection.execute("SELECT COUNT(*) FROM cast_members WHERE season_id = ?", (season_id,)).fetchone()[0])
        notifications = int(self.database.connection.execute("SELECT COUNT(*) FROM notifications WHERE season_id = ? AND read_at IS NULL", (season_id,)).fetchone()[0])
        work = self.database.connection.execute(
            "SELECT SUM(status = 'QUEUED') AS queued, SUM(status = 'LEASED') AS leased "
            "FROM work_items WHERE json_extract(payload_json, '$.season_id') = ?", (season_id,)
        ).fetchone()
        accepted = self.database.connection.execute(
            "SELECT COUNT(*) FROM turns t JOIN runs r ON r.run_id = t.run_id WHERE r.season_id = ?", (season_id,)
        ).fetchone()[0]
        integrity = str(self.database.connection.execute("PRAGMA integrity_check").fetchone()[0])
        return {
            "season_id": season_id, "season_status": season.status.value, "season_version": season.version,
            "runs": {str(row["status"]): int(row["count"]) for row in runs},
            "model_calls": {str(row["status"]): int(row["count"]) for row in calls},
            "diaries": {str(row["status"]): int(row["count"]) for row in diaries},
            "accepted_story_records": int(accepted), "cast_count": cast, "unread_notifications": notifications,
            "work": {"queued": int(work["queued"] or 0), "active_leases": int(work["leased"] or 0)},
            "database_integrity": "ok" if integrity == "ok" else "not_ok",
            "archive_reachable": self.roots.private.is_dir() and os.access(self.roots.private, os.R_OK),
            "artifact_outbox_pending": int(self.database.connection.execute("SELECT COUNT(*) FROM artifact_outbox WHERE status = 'PENDING'").fetchone()[0]),
            "private_archive_sha256": _tree_hash(self.roots.private),
            "unresolved": self._unresolved(season_id),
        }

    def _unresolved(self, season_id: str) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        for row in self.database.connection.execute(
            "SELECT run_id, status FROM runs WHERE season_id = ? AND status NOT IN ('COMPLETED', 'SKIPPED') ORDER BY run_id", (season_id,)
        ):
            items.append({"kind": "run", "id": str(row["run_id"]), "status": str(row["status"])})
        for row in self.database.connection.execute(
            "SELECT diary_id, status FROM diaries WHERE season_id = ? AND status IN ('EXPECTED', 'MISSING', 'PRIVATE') ORDER BY diary_id", (season_id,)
        ):
            items.append({"kind": "diary", "id": str(row["diary_id"]), "status": str(row["status"])})
        return items

    def _store_closure_snapshot(self, snapshot_hash: str, snapshot: dict[str, Any], now: str) -> None:
        self.database.connection.execute(
            "INSERT OR IGNORE INTO closure_snapshots(snapshot_hash, season_id, season_version, payload_json, private_archive_sha256, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (snapshot_hash, snapshot["season_id"], snapshot["season_version"], json.dumps(snapshot, sort_keys=True), snapshot["private_archive_sha256"], now),
        )

    def _replay(self, request_id: str, action: str, fingerprint: str) -> dict[str, Any] | None:
        row = self.database.connection.execute(
            "SELECT action, fingerprint, response_json FROM seasons_action_receipts WHERE request_id = ?", (request_id,)
        ).fetchone()
        if row is None:
            return None
        if str(row["action"]) != action or str(row["fingerprint"]) != fingerprint:
            raise SeasonsError("request id was already used for different intent")
        response = json.loads(str(row["response_json"]))
        response["replayed"] = True
        return response

    def _store_action(self, request_id: str, action: str, fingerprint: str, response: dict[str, Any], now: str) -> None:
        self.database.connection.execute(
            "INSERT INTO seasons_action_receipts(request_id, action, fingerprint, response_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (request_id, action, fingerprint, json.dumps(response, sort_keys=True), now),
        )


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.is_dir():
        return digest.hexdigest()
    for path in sorted((candidate for candidate in root.rglob("*") if candidate.is_file()), key=lambda item: str(item.relative_to(root))):
        relative = str(path.relative_to(root)).encode("utf-8")
        digest.update(relative + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


__all__ = ["SeasonsError", "SeasonsService"]
