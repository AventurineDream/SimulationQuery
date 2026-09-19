"""Versioned, sandbox-oriented manual preparation rehearsal ledger."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from ..infrastructure import SQLiteDatabase


class PreparationError(RuntimeError):
    """Reject stale, out-of-order, or unsupported rehearsal actions."""


STEPS = (
    "idea",
    "opening",
    "character_cards",
    "model_assignment",
    "preflight",
    "private_preparation",
    "schedule_preview",
    "green_review",
)


@dataclass
class PreparationService:
    database: SQLiteDatabase
    now: datetime

    def perform(
        self,
        *,
        request_id: str,
        season_id: str,
        action: str,
        expected_version: int,
        character_id: str | None = None,
        card: dict[str, object] | None = None,
    ) -> dict[str, object]:
        replay = self.database.connection.execute(
            "SELECT response_json FROM preparation_actions WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if replay is not None:
            return json.loads(str(replay["response_json"]))
        workspace = self._workspace(season_id)
        if int(workspace["version"]) != expected_version:
            raise PreparationError("preparation workspace changed; reload before continuing")
        handlers = {
            "save_card_revision": lambda connection, version: self._save_card(
                connection, season_id, character_id, card or {}, version
            ),
            "approve_card": lambda connection, version: self._approve_card(
                connection, season_id, character_id, version
            ),
            "approve_model_assignment": lambda connection, version: self._approve_assignment(
                connection, season_id, version
            ),
            "record_preflight": lambda connection, version: self._record_step(
                connection, season_id, "preflight", version,
                prerequisite="model_assignment",
                detail={"database": "passed", "paths": "passed", "bindings": "stored_only", "model_probe": "not_run"},
            ),
            "record_private_preparation": lambda connection, version: self._record_step(
                connection, season_id, "private_preparation", version,
                prerequisite="preflight",
                detail=self._private_preparation_detail(connection, season_id),
            ),
            "record_schedule_preview": lambda connection, version: self._record_step(
                connection, season_id, "schedule_preview", version,
                prerequisite="private_preparation",
                detail={"days": 7, "slots": 21, "timezone": "America/Los_Angeles", "persisted_schedule_changed": False},
            ),
            "record_green_review": lambda connection, version: self._record_step(
                connection, season_id, "green_review", version,
                prerequisite="schedule_preview",
                detail={"ready": True, "season_armed": False, "command_submitted": False},
            ),
            "revise_opening": lambda connection, version: self._revise_opening(
                connection, season_id, workspace, version
            ),
        }
        handler = handlers.get(action)
        if handler is None:
            raise PreparationError("unsupported preparation action")
        next_version = expected_version + 1
        with self.database.transaction() as connection:
            detail = handler(connection, next_version)
            connection.execute(
                "UPDATE preparation_workspaces SET version = ?, updated_at = ? WHERE season_id = ?",
                (next_version, self.now.isoformat(), season_id),
            )
            response: dict[str, object] = {
                "request_id": request_id,
                "season_id": season_id,
                "action": action,
                "workspace_version": next_version,
                "detail": detail,
                "immutable_receipt": True,
            }
            connection.execute(
                "INSERT INTO preparation_actions(request_id, season_id, action, response_json, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (request_id, season_id, action, json.dumps(response, sort_keys=True), self.now.isoformat()),
            )
        return response

    def _workspace(self, season_id: str):
        row = self.database.connection.execute(
            "SELECT * FROM preparation_workspaces WHERE season_id = ?", (season_id,)
        ).fetchone()
        if row is None:
            raise PreparationError("no preparation rehearsal is stored for this season")
        return row

    def _latest_card(self, connection, season_id: str, character_id: str):
        return connection.execute(
            "SELECT * FROM character_card_versions WHERE season_id = ? AND character_id = ? "
            "ORDER BY version DESC LIMIT 1", (season_id, character_id)
        ).fetchone()

    def _save_card(self, connection, season_id: str, character_id: str | None, card: dict[str, object], workspace_version: int):
        if not character_id:
            raise PreparationError("character_id is required")
        latest = self._latest_card(connection, season_id, character_id)
        if latest is None:
            raise PreparationError("character card does not belong to this rehearsal")
        required = ("pronouns", "public_brief", "occupation_skills", "voice_anchors", "habits")
        if any(key not in card for key in required):
            raise PreparationError("character card revision is incomplete")
        if not str(card["pronouns"]).strip() or not str(card["public_brief"]).strip():
            raise PreparationError("character card text fields cannot be empty")
        for key in ("occupation_skills", "voice_anchors", "habits"):
            values = card[key]
            if (
                not isinstance(values, list)
                or not values
                or any(not isinstance(item, str) or not item.strip() for item in values)
            ):
                raise PreparationError(f"{key.replace('_', ' ')} must contain text entries")
        version = int(latest["version"]) + 1
        connection.execute(
            "INSERT INTO character_card_versions(season_id, character_id, version, status, name, "
            "pronouns, public_brief, occupation_skills_json, voice_anchors_json, habits_json, "
            "derived_opening_version, created_at) VALUES (?, ?, ?, 'DRAFT', ?, ?, ?, ?, ?, ?, ?, ?)",
            (season_id, character_id, version, str(latest["name"]), str(card["pronouns"]),
             str(card["public_brief"]), json.dumps(card["occupation_skills"]),
             json.dumps(card["voice_anchors"]), json.dumps(card["habits"]),
             int(self._workspace(season_id)["opening_version"]), self.now.isoformat()),
        )
        connection.execute(
            "UPDATE private_preparation_versions SET status = 'STALE' "
            "WHERE season_id = ? AND character_id = ? AND status = 'READY'",
            (season_id, character_id),
        )
        self._invalidate(connection, season_id, "character_cards", version, workspace_version,
                         "A character-card revision invalidates later preparation evidence.")
        return {"character_id": character_id, "card_version": version, "status": "DRAFT"}

    def _approve_card(self, connection, season_id: str, character_id: str | None, workspace_version: int):
        if not character_id:
            raise PreparationError("character_id is required")
        latest = self._latest_card(connection, season_id, character_id)
        if latest is None or str(latest["status"]) not in {"DRAFT", "STALE_APPROVED"}:
            raise PreparationError("latest character card is not awaiting approval")
        connection.execute(
            "UPDATE character_card_versions SET status = 'APPROVED', approved_at = ? "
            "WHERE season_id = ? AND character_id = ? AND version = ?",
            (self.now.isoformat(), season_id, character_id, int(latest["version"])),
        )
        remaining = int(connection.execute(
            "SELECT COUNT(*) FROM cast_members c WHERE c.season_id = ? AND NOT EXISTS ("
            "SELECT 1 FROM character_card_versions cc WHERE cc.season_id = c.season_id "
            "AND cc.character_id = c.character_id AND cc.status = 'APPROVED' AND cc.version = ("
            "SELECT MAX(version) FROM character_card_versions WHERE season_id = c.season_id "
            "AND character_id = c.character_id))", (season_id,)
        ).fetchone()[0])
        if remaining == 0:
            self._receipt(connection, season_id, "character_cards", workspace_version, "APPROVED", {"all_cards_approved": True})
        return {"character_id": character_id, "card_version": int(latest["version"]), "remaining": remaining}

    def _approve_assignment(self, connection, season_id: str, workspace_version: int):
        if not self._step_complete(connection, season_id, "character_cards"):
            raise PreparationError("all character cards must be approved first")
        row = connection.execute(
            "SELECT * FROM model_assignment_versions WHERE season_id = ? ORDER BY version DESC LIMIT 1",
            (season_id,),
        ).fetchone()
        if row is None:
            raise PreparationError("no model assignment evidence is stored")
        connection.execute(
            "UPDATE model_assignment_versions SET status = 'APPROVED', approved_at = ? "
            "WHERE season_id = ? AND version = ?",
            (self.now.isoformat(), season_id, int(row["version"])),
        )
        self._receipt(connection, season_id, "model_assignment", workspace_version, "APPROVED",
                      {"manifest_name": str(row["manifest_name"]), "automatic_selection": False})
        return {"manifest_version": int(row["version"]), "automatic_selection": False}

    def _record_step(self, connection, season_id: str, step: str, workspace_version: int, *, prerequisite: str, detail: dict[str, object]):
        if not self._step_complete(connection, season_id, prerequisite):
            raise PreparationError(f"{prerequisite.replace('_', ' ')} must be complete first")
        self._receipt(connection, season_id, step, workspace_version, "READY" if step == "green_review" else "COMPLETE", detail)
        return detail

    def _private_preparation_detail(self, connection, season_id: str) -> dict[str, object]:
        card_rows = connection.execute(
            "SELECT cc.character_id, cc.version FROM character_card_versions cc "
            "WHERE cc.season_id = ? AND cc.status = 'APPROVED' AND cc.version = ("
            "SELECT MAX(version) FROM character_card_versions latest "
            "WHERE latest.season_id = cc.season_id AND latest.character_id = cc.character_id)",
            (season_id,),
        ).fetchall()
        cast_count = int(connection.execute(
            "SELECT COUNT(*) FROM cast_members WHERE season_id = ?", (season_id,)
        ).fetchone()[0])
        if len(card_rows) != cast_count:
            raise PreparationError("all latest character cards must be approved")
        provenance: dict[str, dict[str, int]] = {}
        for card_row in card_rows:
            character_id = str(card_row["character_id"])
            card_version = int(card_row["version"])
            artifacts = connection.execute(
                "SELECT artifact_kind, version, source_character_card_version, status "
                "FROM private_preparation_versions WHERE season_id = ? AND character_id = ? "
                "AND version = (SELECT MAX(version) FROM private_preparation_versions latest "
                "WHERE latest.season_id = ? AND latest.character_id = ? "
                "AND latest.artifact_kind = private_preparation_versions.artifact_kind)",
                (season_id, character_id, season_id, character_id),
            ).fetchall()
            by_kind = {str(row["artifact_kind"]): row for row in artifacts}
            if set(by_kind) != {"role_sheet", "orientation"}:
                raise PreparationError(f"private preparation artifacts are incomplete for {character_id}")
            if any(
                str(row["status"]) != "READY"
                or int(row["source_character_card_version"]) != card_version
                for row in by_kind.values()
            ):
                raise PreparationError(f"private preparation artifacts are stale for {character_id}")
            provenance[character_id] = {
                "character_card_version": card_version,
                "role_sheet_version": int(by_kind["role_sheet"]["version"]),
                "orientation_version": int(by_kind["orientation"]["version"]),
            }
        return {"artifacts": provenance, "model_calls": 0, "private_content_disclosed": False}

    def _revise_opening(self, connection, season_id: str, workspace, workspace_version: int):
        current = int(workspace["opening_version"])
        source = connection.execute(
            "SELECT * FROM season_opening_versions WHERE season_id = ? AND version = ?",
            (season_id, current),
        ).fetchone()
        if source is None:
            raise PreparationError("approved opening version is unavailable")
        version = current + 1
        connection.execute(
            "INSERT INTO season_opening_versions(season_id, version, set_text, setting, cast_json, world_rules_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (season_id, version, str(source["set_text"]), str(source["setting"]),
             str(source["cast_json"]), str(source["world_rules_json"]), self.now.isoformat()),
        )
        connection.execute(
            "UPDATE preparation_workspaces SET opening_version = ? WHERE season_id = ?",
            (version, season_id),
        )
        connection.execute(
            "UPDATE character_card_versions SET status = 'STALE_APPROVED' "
            "WHERE season_id = ? AND status = 'APPROVED'", (season_id,)
        )
        connection.execute(
            "UPDATE private_preparation_versions SET status = 'STALE' "
            "WHERE season_id = ? AND status = 'READY'", (season_id,)
        )
        self._invalidate(connection, season_id, "opening", version, workspace_version,
                         "Opening revision requires character cards and all dependent evidence to be reviewed again.")
        return {"opening_version": version, "invalidated_from": "character_cards"}

    def _invalidate(self, connection, season_id: str, source_step: str, source_version: int, workspace_version: int, reason: str):
        start = STEPS.index(source_step) + 1
        invalidated = list(STEPS[start:])
        connection.execute(
            "DELETE FROM preparation_receipts WHERE season_id = ? AND step IN (" + ",".join("?" for _ in invalidated) + ")",
            (season_id, *invalidated),
        )
        event_id = f"{season_id}:invalidation:{workspace_version}:{source_step}"
        connection.execute(
            "INSERT INTO preparation_invalidation_events(event_id, season_id, source_step, source_version, "
            "invalidated_steps_json, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event_id, season_id, source_step, source_version, json.dumps(invalidated), reason, self.now.isoformat()),
        )

    def _receipt(self, connection, season_id: str, step: str, workspace_version: int, status: str, detail: dict[str, object]):
        receipt_id = f"{season_id}:prepare:{step}:v{workspace_version}"
        connection.execute(
            "INSERT INTO preparation_receipts(receipt_id, season_id, step, workspace_version, status, detail_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (receipt_id, season_id, step, workspace_version, status, json.dumps(detail, sort_keys=True), self.now.isoformat()),
        )

    @staticmethod
    def _step_complete(connection, season_id: str, step: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM preparation_receipts WHERE season_id = ? AND step = ? "
            "AND status IN ('APPROVED', 'COMPLETE', 'READY') ORDER BY workspace_version DESC LIMIT 1",
            (season_id, step),
        ).fetchone() is not None


__all__ = ["PreparationError", "PreparationService", "STEPS"]
