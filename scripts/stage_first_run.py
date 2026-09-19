#!/usr/bin/env python3
"""Stage an approved opening and model manifest into a draft season database.

This is intentionally a preflight-only bridge. It never greenlights a season,
generates role sheets, starts a scene, or starts the dashboard.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from improv_troupe.application import (
    CommandBus,
    CreateSeason,
    PreflightSeason,
    ReviseOpening,
    SceneModelManifest,
    ServicePaths,
    validate_model_manifest,
)
from improv_troupe.config import AppConfig
from improv_troupe.domain import CastMember, OpeningSnapshot
from improv_troupe.infrastructure import SQLiteDatabase
from improv_troupe.llm.client import make_client


def _request_id(prefix: str, payload: object) -> str:
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return f"stage:{prefix}:{digest}"


async def _probe_backends(
    manifest: SceneModelManifest,
    *,
    config: AppConfig,
) -> dict[str, list[str]]:
    """List models on every selected backend and fail on missing assignments."""

    bindings = [manifest.orchestrator, *manifest.actors.values()]
    model_by_backend: dict[str, set[str]] = {}
    for binding in bindings:
        model_by_backend.setdefault(binding.backend, set()).add(binding.model)

    inventory: dict[str, list[str]] = {}
    for handle, required in model_by_backend.items():
        backend = config.backend(handle)
        models = await make_client(
            kind=backend.kind,
            base_url=backend.base_url,
            api_key=backend.api_key,
        ).list_models()
        inventory[handle] = sorted(models)
        missing = sorted(required - set(models))
        if missing:
            raise RuntimeError(
                f"backend {handle!r} is missing selected model(s): {', '.join(missing)}"
            )
    return inventory


def _load_inputs(
    approved_path: Path,
    manifest_path: Path,
) -> tuple[dict[str, Any], OpeningSnapshot, tuple[CastMember, ...], dict[str, Any]]:
    approved = json.loads(approved_path.read_text(encoding="utf-8"))
    if approved.get("status") != "APPROVED_FOR_PREFLIGHT":
        raise ValueError("approved opening must have status APPROVED_FOR_PREFLIGHT")
    if approved.get("approval", {}).get("greenlit") is not False:
        raise ValueError("approved opening must not be greenlit")

    opening = OpeningSnapshot.model_validate(approved["opening"])
    cast_ids = list(approved.get("cast_ids", []))
    if len(cast_ids) != len(opening.cast) or len(set(cast_ids)) != len(cast_ids):
        raise ValueError("approved opening cast_ids must uniquely cover the opening cast")
    cast = tuple(
        CastMember(character_id=character_id, name=name)
        for character_id, name in zip(cast_ids, opening.cast, strict=True)
    )
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return approved, opening, cast, manifest_data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-opening", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    args = parser.parse_args()

    approved_path = args.approved_opening.resolve()
    manifest_path = args.manifest.resolve()
    config = AppConfig.load(args.config)
    approved, opening, cast, manifest_data = _load_inputs(approved_path, manifest_path)
    manifest = SceneModelManifest.model_validate(manifest_data)
    actor_ids = [member.character_id for member in cast]
    validate_model_manifest(manifest, actor_ids=actor_ids, config=config)
    inventory = asyncio.run(_probe_backends(manifest, config=config))

    paths = ServicePaths.from_root(args.data_root)
    paths.prepare()
    database = SQLiteDatabase(paths.database_path)
    try:
        database.migrate()
        integrity = database.connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")

        bus = CommandBus(database)
        season_id = str(approved["season_id"])
        created = bus.execute(
            CreateSeason(
                request_id=_request_id(f"{season_id}:create", approved),
                season_id=season_id,
                season_number=1,
                title="Aether",
            )
        )
        revised = bus.execute(
            ReviseOpening(
                request_id=_request_id(f"{season_id}:opening", approved["opening"]),
                season_id=season_id,
                opening=opening,
                cast=cast,
            )
        )
        checks = {
            "sqlite_integrity": True,
            "persistent_roots": all(
                path.exists() for path in (paths.roots.state, paths.roots.private, paths.roots.public)
            ),
            "model_manifest": True,
            "backend_reachability": True,
        }
        preflight = bus.execute(
            PreflightSeason(
                request_id=_request_id(
                    f"{season_id}:preflight", {"opening": approved["opening"], "manifest": manifest_data}
                ),
                season_id=season_id,
                checks=checks,
                model_manifest=manifest_data,
            )
        )
        payload = {
            "status": "PREFLIGHT_PASSED_NOT_GREEN",
            "season_id": season_id,
            "data_root": str(paths.data_root),
            "database": str(paths.database_path),
            "checks": checks,
            "backend_inventory": inventory,
            "commands": {
                "create": created.payload,
                "opening": revised.payload,
                "preflight": preflight.payload,
            },
            "next": "creator must explicitly send green after private dashboard review",
        }
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
