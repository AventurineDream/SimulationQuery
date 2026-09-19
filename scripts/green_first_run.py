#!/usr/bin/env python3
"""Green S01, generate private planning, and orient the first-run cast.

This is the post-dashboard-review bridge for the first live season.  It is
deliberately separate from ``stage_first_run.py``: staging stops before green,
while this command records the creator's approval, creates the private plan,
arms the 21-slot schedule, and runs orientation.  It does not drain the scene
queue or execute a performance.

The command is safe to replay against the Linux service database.  Completed
role-sheet artifacts and accepted orientation events are reused, and the
season command layer provides request-id replay for the durable transitions.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from improv_troupe.application import (
    CommandBus,
    ControlSeason,
    GreenSeason,
    ModelBinding,
    ModelCallExecutor,
    OrientationActor,
    OrientationService,
    SceneModelManifest,
    ServicePaths,
    TransitionSeason,
    WellnessService,
    validate_model_manifest,
)
from improv_troupe.application.commands import CommandResult
from improv_troupe.clock import SystemClock
from improv_troupe.config import AppConfig
from improv_troupe.domain import (
    CastMember,
    HiddenSeasonPlan,
    OpeningSnapshot,
    RoleSheet,
    SeasonStatus,
)
from improv_troupe.infrastructure import SQLiteDatabase, SeasonRepository
from improv_troupe.llm.adapter import NormalizedCallStatus
from improv_troupe.llm.audit import AuditWriter
from improv_troupe.llm.client import Message, make_client


def _request_id(prefix: str, payload: object) -> str:
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return f"green:{prefix}:{digest}"


def _load_inputs(
    approved_path: Path,
    manifest_path: Path,
) -> tuple[OpeningSnapshot, tuple[CastMember, ...], dict[str, Any]]:
    approved = json.loads(approved_path.read_text(encoding="utf-8"))
    if approved.get("status") != "APPROVED_FOR_PREFLIGHT":
        raise ValueError("approved opening must have status APPROVED_FOR_PREFLIGHT")
    if approved.get("approval", {}).get("greenlit") is not False:
        raise ValueError("approved opening record must remain the pre-green record")

    opening = OpeningSnapshot.model_validate(approved["opening"])
    cast_ids = list(approved.get("cast_ids", []))
    if len(cast_ids) != len(opening.cast) or len(set(cast_ids)) != len(cast_ids):
        raise ValueError("approved opening cast_ids must uniquely cover the opening cast")
    cast = tuple(
        CastMember(character_id=character_id, name=name)
        for character_id, name in zip(cast_ids, opening.cast, strict=True)
    )
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest_data, dict) or not manifest_data:
        raise ValueError("model manifest must be a non-empty JSON object")
    return opening, cast, manifest_data


def _json_object(raw: str) -> dict[str, Any]:
    """Accept a JSON object even if a model wraps it in a markdown fence."""

    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("model response did not contain a JSON object") from None
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError("model response contained invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("model response must be a JSON object")
    return value


def _role_sheet(raw: str, *, character_id: str) -> RoleSheet:
    data = _json_object(raw)
    if isinstance(data.get("role_sheet"), dict):
        data = dict(data["role_sheet"])
    data.pop("kind", None)
    data["character_id"] = character_id
    for field in ("objectives", "boundaries", "knowledge", "relationships", "secrets"):
        value = data.get(field, [])
        if isinstance(value, dict):
            value = [f"{key}: {item}" for key, item in value.items()]
        elif isinstance(value, str):
            # A model sometimes echoes the requested item count.  Leave that
            # field empty so the repair attempt below is forced to replace it
            # with actual content rather than silently treating a count as a
            # character boundary or fact.
            value = [] if value.strip().isdigit() else [value]
        elif not isinstance(value, list):
            value = []
        data[field] = value
    sheet = RoleSheet.model_validate(data)
    if sheet.character_id != character_id:
        raise ValueError(f"role sheet returned the wrong character id: {sheet.character_id}")
    required = ("objectives", "boundaries", "knowledge", "relationships", "secrets")
    missing = [field for field in required if not getattr(sheet, field)]
    if missing:
        raise ValueError("role sheet fields need actual entries: " + ", ".join(missing))
    return sheet


def _plan_seed(raw: str) -> HiddenSeasonPlan:
    data = _json_object(raw)
    if isinstance(data.get("private_plan"), dict):
        data = dict(data["private_plan"])
    data.pop("kind", None)
    data["role_sheets"] = []
    return HiddenSeasonPlan.model_validate(data)


def _plan_messages(opening: OpeningSnapshot, cast: tuple[CastMember, ...]) -> list[Message]:
    payload = {
        "opening": opening.creator_view(),
        "cast": [member.model_dump(mode="json") for member in cast],
        "instruction": (
            "Create a compact private season-plan seed for the Dungeon Master. Shape possible "
            "conditions and tensions, but do not dictate any actor's thoughts, dialogue, "
            "choices, relationships, discoveries, or ending. Nothing here is a required plot "
            "outcome. Keep the TV-14 limits and the speculative nature of the science."
        ),
        "return_shape": {
            "premise": "one short paragraph",
            "planned_tensions": ["2 to 4 conditional tension seeds"],
            "hidden_mysteries": ["0 to 3 unresolved questions, never solutions"],
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You are the private orchestrator and Dungeon Master for AI Improv Troupe. "
                "Return only one JSON object with the requested fields."
            ),
        },
        {"role": "user", "content": json.dumps(payload, sort_keys=True)},
    ]


def _role_sheet_messages(
    opening: OpeningSnapshot,
    cast: tuple[CastMember, ...],
    member: CastMember,
) -> list[Message]:
    payload = {
        "opening": opening.creator_view(),
        "cast": [other.model_dump(mode="json") for other in cast],
        "character": member.model_dump(mode="json"),
        "instruction": (
            "Generate only this character's private role sheet. Give them playable objectives, "
            "clear TV-14 boundaries, plausible knowledge limits, starting relationship dynamics, "
            "secrets or uncertainties, a play style, and voice guidance. Secrets are seeds, not "
            "facts that must be revealed. Preserve actor agency: do not script dialogue, fixed "
            "choices, guaranteed discoveries, a predetermined mission outcome, or another "
            "actor's private thoughts. Keep the science speculative and non-actionable."
        ),
        "return_shape": {
            "character_id": member.character_id,
            "objectives": ["complete objective sentence", "another complete objective sentence"],
            "boundaries": ["complete TV-14 boundary statement"],
            "knowledge": ["complete plausible knowledge statement"],
            "relationships": ["complete starting dynamic sentence for each other cast member"],
            "secrets": ["complete private uncertainty or motive statement"],
            "play_style": "one sentence",
            "voice_guidance": "one or two sentences",
            "version": 1,
        },
        "format_warning": (
            "Every array must contain actual complete strings. Never return a count such as "
            "'2' or '3', and never return a relationship object/map."
        ),
    }
    return [
        {
            "role": "system",
            "content": (
                "You are the private orchestrator and Dungeon Master. Return only one JSON "
                "object with exactly the role-sheet fields requested."
            ),
        },
        {"role": "user", "content": json.dumps(payload, sort_keys=True)},
    ]


def _executor(
    database: SQLiteDatabase,
    paths: ServicePaths,
    config: AppConfig,
    binding: ModelBinding,
) -> ModelCallExecutor:
    backend = config.backend(binding.backend)
    return ModelCallExecutor(
        database=database,
        client=make_client(
            kind=backend.kind, base_url=backend.base_url, api_key=backend.api_key
        ),
        clock=SystemClock(),
        audit_root=paths.roots.private,
        backend=binding.backend,
        model=binding.model,
        default_params=dict(binding.params),
    )


def _orientation_executor(
    database: SQLiteDatabase,
    paths: ServicePaths,
    config: AppConfig,
    binding: ModelBinding,
) -> ModelCallExecutor:
    """Use deterministic low-variance settings for the consent envelope only."""

    executor = _executor(database, paths, config, binding)
    executor.default_params = {
        **dict(binding.params),
        "temperature": 0.0,
        "max_tokens": 256,
    }
    return executor


async def _call_text(
    executor: ModelCallExecutor,
    *,
    call_id_prefix: str,
    purpose: str,
    messages: list[Message],
    max_tokens: int,
    schema_name: str | None = None,
) -> dict[str, Any]:
    attempt = executor.calls.next_attempt(run_id=None, purpose=purpose)
    result = await executor.execute(
        call_id=f"{call_id_prefix}:a{attempt}",
        run_id=None,
        purpose=purpose,
        attempt=attempt,
        messages=messages,
        params={"temperature": 0.35, "max_tokens": max_tokens},
        schema_name=schema_name,
        tagged_format_instructions=("Return one JSON object and no surrounding prose." if schema_name else None),
    )
    if result.status is not NormalizedCallStatus.COMPLETED:
        raise RuntimeError(
            f"{purpose} model call failed with {result.status.value}"
            + (f" ({result.error_type})" if result.error_type else "")
        )
    return result.text


async def _call_json(
    executor: ModelCallExecutor,
    *,
    call_id_prefix: str,
    purpose: str,
    messages: list[Message],
    max_tokens: int,
    schema_name: str,
) -> dict[str, Any]:
    return _json_object(
        await _call_text(
            executor,
            call_id_prefix=call_id_prefix,
            purpose=purpose,
            messages=messages,
            max_tokens=max_tokens,
            schema_name=schema_name,
        )
    )


def _artifact_path(season_id: str, kind: str, name: str) -> Path:
    return Path("seasons") / season_id / kind / "v1" / name


async def _build_private_plan(
    *,
    database: SQLiteDatabase,
    paths: ServicePaths,
    config: AppConfig,
    opening: OpeningSnapshot,
    cast: tuple[CastMember, ...],
    manifest: SceneModelManifest,
    season_id: str,
) -> HiddenSeasonPlan:
    existing = SeasonRepository(database).get(season_id).private_plan
    if existing is not None:
        return existing

    writer = AuditWriter(paths.roots.private)
    orchestrator = _executor(database, paths, config, manifest.orchestrator)

    plan_path = _artifact_path(season_id, "private-plan", "seed.json")
    plan_target = paths.roots.private / plan_path
    if plan_target.exists():
        seed = HiddenSeasonPlan.model_validate_json(plan_target.read_text(encoding="utf-8"))
    else:
        seed = _plan_seed(
            json.dumps(
                await _call_json(
                    orchestrator,
                    call_id_prefix=f"{season_id}:private-plan",
                    purpose=f"private-plan:{season_id}",
                    messages=_plan_messages(opening, cast),
                    max_tokens=700,
                    schema_name="private_plan",
                )
            )
        )
        writer.write_text(plan_path, seed.model_dump_json(indent=2))

    sheets: list[RoleSheet] = []
    for member in cast:
        sheet_path = _artifact_path(season_id, "role-sheets", f"{member.character_id}.json")
        target = paths.roots.private / sheet_path
        if target.exists():
            sheet = RoleSheet.model_validate_json(target.read_text(encoding="utf-8"))
        else:
            messages = _role_sheet_messages(opening, cast, member)
            purpose = f"role-sheet:{season_id}:{member.character_id}"
            call_id_prefix = f"{season_id}:role-sheet:{member.character_id}"
            raw = await _call_text(
                orchestrator,
                call_id_prefix=call_id_prefix,
                purpose=purpose,
                messages=messages,
                max_tokens=640,
                schema_name="role_sheet",
            )
            try:
                sheet = _role_sheet(raw, character_id=member.character_id)
            except ValueError as first_error:
                repair_messages = [
                    *messages,
                    {
                        "role": "user",
                        "content": (
                            "The previous object was invalid: "
                            f"{first_error}. Return a corrected object now. Every required "
                            "array must contain actual complete string entries; do not use "
                            "counts, maps, or placeholders."
                        ),
                    },
                ]
                repaired = await _call_text(
                    orchestrator,
                    call_id_prefix=call_id_prefix,
                    purpose=purpose,
                    messages=repair_messages,
                    max_tokens=640,
                    schema_name="role_sheet",
                )
                sheet = _role_sheet(repaired, character_id=member.character_id)
            writer.write_text(sheet_path, sheet.model_dump_json(indent=2))
        if sheet.character_id != member.character_id:
            raise ValueError(f"private role sheet does not match {member.character_id}")
        sheets.append(sheet)

    return seed.model_copy(update={"role_sheets": sheets})


def _record_role_sheet_versions(
    database: SQLiteDatabase,
    *,
    season_id: str,
    sheets: list[RoleSheet],
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with database.transaction() as connection:
        for sheet in sheets:
            content = json.dumps(sheet.model_dump(mode="json"), sort_keys=True)
            existing = connection.execute(
                "SELECT content_json FROM role_sheet_versions "
                "WHERE season_id = ? AND character_id = ? AND version = ?",
                (season_id, sheet.character_id, sheet.version),
            ).fetchone()
            if existing is not None:
                if existing["content_json"] != content:
                    raise ValueError(
                        f"role sheet version already exists with different content: {sheet.character_id}"
                    )
                continue
            connection.execute(
                "INSERT INTO role_sheet_versions "
                "(season_id, character_id, version, content_json, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (season_id, sheet.character_id, sheet.version, content, now),
            )


def _orientation_already_accepted(database: SQLiteDatabase, season_id: str, character_id: str) -> bool:
    row = database.connection.execute(
        "SELECT 1 FROM domain_events WHERE natural_key = ? AND event_type = 'OrientationAccepted'",
        (f"{season_id}:orientation:{character_id}:accepted",),
    ).fetchone()
    return row is not None


async def _run_orientation(
    *,
    database: SQLiteDatabase,
    paths: ServicePaths,
    config: AppConfig,
    manifest: SceneModelManifest,
    cast: tuple[CastMember, ...],
    season_id: str,
) -> list[dict[str, object]]:
    season = SeasonRepository(database).get(season_id)
    wellness = WellnessService(
        database=database,
        season_id=season_id,
        clock=SystemClock(),
        audit_root=paths.roots.private,
        auto_tap_out=season.auto_tap_out,
    )
    service = OrientationService(
        season_id=season_id,
        wellness=wellness,
        auto_tap_out=season.auto_tap_out,
    )
    results: list[dict[str, object]] = []
    for member in cast:
        if _orientation_already_accepted(database, season_id, member.character_id):
            results.append(
                {"character_id": member.character_id, "status": "ACCEPTED", "replayed": True}
            )
            continue
        binding = manifest.actor_binding(member.character_id)
        result = await service.orient(
            OrientationActor(
                character_id=member.character_id,
                name=member.name,
                executor=_orientation_executor(database, paths, config, binding),
            )
        )
        results.append(
            {
                "character_id": result.character_id,
                "status": result.status,
                "accepted": result.accepted,
                "signal_number": result.signal_number,
                "tapped_out": result.tapped_out,
                "reason": result.reason,
            }
        )
    return results


def _green_at(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--green-at must include a timezone offset")
    return parsed


async def _run(args: argparse.Namespace) -> dict[str, object]:
    approved_path = args.approved_opening.resolve()
    manifest_path = args.manifest.resolve()
    config = AppConfig.load(args.config)
    opening, cast, manifest_data = _load_inputs(approved_path, manifest_path)
    manifest = SceneModelManifest.model_validate(manifest_data)
    actor_ids = [member.character_id for member in cast]
    validate_model_manifest(manifest, actor_ids=actor_ids, config=config)

    paths = ServicePaths.from_root(args.data_root)
    paths.prepare()
    database = SQLiteDatabase(paths.database_path)
    try:
        database.migrate()
        integrity = database.connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")

        season_id = args.season
        seasons = SeasonRepository(database)
        season = seasons.get(season_id)
        if not season.preflight_passed:
            raise RuntimeError("green requires a successful preflight")
        if season.opening != opening:
            raise RuntimeError("approved opening does not match the staged season")
        if season.model_manifest != manifest_data:
            raise RuntimeError("model manifest differs from the staged preflight manifest")

        bus = CommandBus(database)
        if season.status is SeasonStatus.DRAFT:
            bus.execute(
                TransitionSeason(
                    request_id=_request_id(f"{season_id}:awaiting-green", opening.model_dump()),
                    season_id=season_id,
                    target=SeasonStatus.AWAITING_GREEN,
                )
            )
            season = seasons.get(season_id)
        if season.status not in {SeasonStatus.AWAITING_GREEN, SeasonStatus.ARMED}:
            raise RuntimeError(f"season is {season.status.value}; cannot apply green")

        private_plan = await _build_private_plan(
            database=database,
            paths=paths,
            config=config,
            opening=opening,
            cast=cast,
            manifest=manifest,
            season_id=season_id,
        )
        _record_role_sheet_versions(database, season_id=season_id, sheets=private_plan.role_sheets)
        green_payload: dict[str, object]
        if season.status is SeasonStatus.AWAITING_GREEN:
            green_at = _green_at(args.green_at)
            green_cast = tuple(
                member.model_copy(update={"role_sheet_version": sheet.version})
                for member, sheet in zip(cast, private_plan.role_sheets, strict=True)
            )
            result: CommandResult = bus.execute(
                GreenSeason(
                    request_id=_request_id(
                        f"{season_id}:green",
                        {"opening": opening.model_dump(), "green_at": green_at.isoformat()},
                    ),
                    season_id=season_id,
                    green_at=green_at,
                    opening=opening,
                    cast=green_cast,
                    private_plan=private_plan,
                )
            )
            green_payload = result.payload
        else:
            green_payload = {
                "season_id": season_id,
                "status": season.status.value,
                "already_green": True,
                "first_run_at": season.schedule[0].scheduled_utc.isoformat()
                if season.schedule
                else None,
                "run_count": len(season.schedule),
            }

        cast_for_orientation = tuple(seasons.get(season_id).cast)
        orientation = await _run_orientation(
            database=database,
            paths=paths,
            config=config,
            manifest=manifest,
            cast=cast_for_orientation,
            season_id=season_id,
        )
        all_accepted = all(bool(item.get("accepted", item.get("status") == "ACCEPTED")) for item in orientation)
        current = seasons.get(season_id)
        if not all_accepted and current.status is SeasonStatus.ARMED:
            bus.execute(
                ControlSeason(
                    request_id=_request_id(f"{season_id}:orientation-review", orientation),
                    season_id=season_id,
                    target=SeasonStatus.PAUSED,
                )
            )

        summary = {
            "season_id": season_id,
            "status": "GREEN_ORIENTATION_ACCEPTED" if all_accepted else "GREEN_ORIENTATION_REVIEW_REQUIRED",
            "green": green_payload,
            "orientation": orientation,
            "scene_started": False,
            "private_plan": {
                "version": private_plan.version,
                "role_sheet_ids": [sheet.character_id for sheet in private_plan.role_sheets],
            },
        }
        writer = AuditWriter(paths.roots.private)
        summary_path = _artifact_path(season_id, "orientation", "summary.json")
        summary_target = paths.roots.private / summary_path
        if not summary_target.exists():
            writer.write_text(summary_path, json.dumps(summary, indent=2, sort_keys=True))
        return summary
    finally:
        database.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-opening", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--season", default="S01")
    parser.add_argument(
        "--green-at",
        help="timezone-aware ISO timestamp; defaults to the current UTC instant",
    )
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(_run(args)), indent=2, sort_keys=True, default=str))
        return 0
    except Exception as exc:  # noqa: BLE001 - operator command reports a concise failure
        print(f"green first run failed: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
