"""Build live scene runners from private season model manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..clock import Clock
from ..config import AppConfig
from ..infrastructure import DataRoots, SeasonRepository, SQLiteDatabase
from ..llm.client import ChatClient, make_client
from .model_calls import ModelCallExecutor
from .scene_runner import SceneActor, SceneRunner
from .wellness import WellnessService


class LiveRuntimeConfigurationError(ValueError):
    """Raised when a private model manifest cannot build a safe scene runtime."""


class ModelBinding(BaseModel):
    """One backend handle and model identifier selected for a role."""

    model_config = ConfigDict(extra="forbid")

    backend: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    prompt_profile: str = "general"
    params: dict[str, object] = Field(
        default_factory=dict,
        description="Default generation parameters passed to this binding.",
    )

    @model_validator(mode="after")
    def _valid_prompt_profile(self) -> "ModelBinding":
        if self.prompt_profile not in {"general", "thrasher", "peach"}:
            raise ValueError("prompt_profile must be general, thrasher, or peach")
        return self


class SceneModelManifest(BaseModel):
    """Private model assignment for one season.

    ``actor_default`` deliberately supports four independent character
    sessions sharing one 8B-class model.  An explicit ``actors`` mapping can
    assign two or three different actor models when the creator chooses them.
    """

    model_config = ConfigDict(extra="forbid")

    orchestrator: ModelBinding
    actor_default: ModelBinding | None = None
    actors: dict[str, ModelBinding] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _requires_actor_assignment(self) -> "SceneModelManifest":
        if self.actor_default is None and not self.actors:
            raise ValueError("manifest requires actor_default or at least one actors binding")
        return self

    def actor_binding(self, character_id: str) -> ModelBinding:
        binding = self.actors.get(character_id) or self.actor_default
        if binding is None:
            raise LiveRuntimeConfigurationError(
                f"no actor model binding for character {character_id!r}"
            )
        return binding


class EpisodeSpineBeat(BaseModel):
    """One enforceable dramatic transition in a bounded rehearsal episode."""

    model_config = ConfigDict(extra="forbid")

    dramatic_job: str = Field(..., min_length=1)
    required_lore_entry_ids: tuple[str, ...] = ()
    required_story_terms: tuple[str, ...] = ()
    forbidden_story_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class _RunNarrativeContext:
    """Durable shared and actor-local context carried into one scheduled run."""

    day_number: int
    slot_number: int
    run_number: int
    scheduled_local: str
    previous_shared_outcome: str | None
    prior_accepted_canon: tuple[str, ...]
    private_day_direction: str | None
    actor_memories: dict[str, tuple[str, ...]]


def validate_model_manifest(
    manifest: SceneModelManifest,
    *,
    actor_ids: list[str],
    config: AppConfig,
) -> None:
    """Validate role coverage and backend handles without making a model call."""
    missing = [character_id for character_id in actor_ids if _binding_for(manifest, character_id) is None]
    if missing:
        raise LiveRuntimeConfigurationError(
            "manifest is missing actor bindings: " + ", ".join(sorted(missing))
        )
    bindings = [manifest.orchestrator] + [manifest.actor_binding(character_id) for character_id in actor_ids]
    unknown = sorted({binding.backend for binding in bindings if binding.backend not in config.backends})
    if unknown:
        raise LiveRuntimeConfigurationError(
            "manifest names unknown backend handle(s): " + ", ".join(unknown)
        )


@dataclass
class LiveSceneFactory:
    """Resolve one durable run into a checkpointed, model-backed scene."""

    database: SQLiteDatabase
    roots: DataRoots
    config: AppConfig
    clock: Clock
    client_factory: Callable[[str], ChatClient] | None = None
    strict_rehearsal_acceptance: bool = False
    sessions_per_day: int = 3
    episode_phases: tuple[str, ...] = ()
    episode_spine: Mapping[str, EpisodeSpineBeat] = field(default_factory=dict)
    clients: dict[str, ChatClient] = field(default_factory=dict)
    seasons: SeasonRepository = field(init=False)

    def __post_init__(self) -> None:
        self.seasons = SeasonRepository(self.database)

    def __call__(self, payload: Mapping[str, object]) -> SceneRunner:
        season_id = str(payload["season_id"])
        run_id = str(payload["run_id"])
        manifest, role_sheets = self._validated_inputs(season_id)
        season = self.seasons.get(season_id)
        narrative = self._run_narrative_context(season_id=season_id, run_id=run_id)
        assert season.opening is not None
        assert season.private_plan is not None

        actor_sheets = {actor.actor_id: actor for actor in season.actors}
        casting = {assignment.character_id: assignment.actor_id for assignment in season.casting}
        actors = []
        for member in season.cast:
            actor_id = casting.get(member.character_id)
            binding_id = actor_id or member.character_id
            actors.append(
                SceneActor(
                    character_id=member.character_id,
                    name=member.name,
                    role_sheet=role_sheets[member.character_id],
                    executor=self._executor(manifest.actor_binding(binding_id)),
                    known_memory=narrative.actor_memories.get(member.character_id, ()),
                    actor_sheet=actor_sheets.get(actor_id) if actor_id else None,
                    character_card=next(
                        (card for card in season.character_cards if card.character_id == member.character_id),
                        None,
                    ),
                    prompt_profile=manifest.actor_binding(binding_id).prompt_profile,
                )
            )
        wellness = WellnessService(
            database=self.database,
            season_id=season_id,
            clock=self.clock,
            audit_root=self.roots.private,
            auto_tap_out=season.auto_tap_out,
        )
        episode_phase = (
            self.episode_phases[narrative.run_number - 1]
            if narrative.run_number <= len(self.episode_phases)
            else "open_play"
        )
        spine = self.episode_spine.get(episode_phase)
        return SceneRunner(
            run_id=run_id,
            opening=season.opening,
            private_plan=season.private_plan,
            actors=tuple(actors),
            orchestrator=self._executor(manifest.orchestrator),
            wellness=wellness,
            day_number=narrative.day_number,
            slot_number=narrative.slot_number,
            scheduled_local=narrative.scheduled_local,
            previous_shared_outcome=narrative.previous_shared_outcome,
            prior_accepted_canon=narrative.prior_accepted_canon,
            private_day_direction=narrative.private_day_direction,
            enforce_narrative_acceptance=self.strict_rehearsal_acceptance,
            two_pass_directing=self.strict_rehearsal_acceptance,
            max_actor_turns=len(actors) * 4,
            sessions_per_day=self.sessions_per_day,
            episode_phase=episode_phase,
            phase_directive=spine.dramatic_job if spine else "",
            required_lore_entry_ids=(spine.required_lore_entry_ids if spine else ()),
            required_story_terms=(spine.required_story_terms if spine else ()),
            forbidden_story_terms=(spine.forbidden_story_terms if spine else ()),
            world_books=tuple(season.world_books),
        )

    def validate_season(self, season_id: str) -> None:
        """Validate a live season's private runtime inputs without calling a model."""
        self._validated_inputs(season_id)

    def _validated_inputs(self, season_id: str):
        season = self.seasons.get(season_id)
        if season.opening is None:
            raise LiveRuntimeConfigurationError(f"season {season_id} has no approved opening")
        if season.private_plan is None:
            raise LiveRuntimeConfigurationError(f"season {season_id} has no private plan")

        manifest = SceneModelManifest.model_validate(season.model_manifest)
        binding_ids = (
            [assignment.actor_id for assignment in season.casting]
            if season.casting
            else [member.character_id for member in season.cast]
        )
        validate_model_manifest(manifest, actor_ids=binding_ids, config=self.config)
        character_ids = [member.character_id for member in season.cast]
        role_sheets = {
            sheet.character_id: sheet for sheet in season.private_plan.role_sheets
        }
        missing_sheets = [
            character_id for character_id in character_ids if character_id not in role_sheets
        ]
        if missing_sheets:
            raise LiveRuntimeConfigurationError(
                "private plan is missing role sheets: " + ", ".join(sorted(missing_sheets))
            )
        return manifest, role_sheets

    def _executor(self, binding: ModelBinding) -> ModelCallExecutor:
        client = self.clients.get(binding.backend)
        if client is None:
            client = self._client(binding.backend)
            self.clients[binding.backend] = client
        return ModelCallExecutor(
            database=self.database,
            client=client,
            clock=self.clock,
            audit_root=self.roots.private,
            backend=binding.backend,
            model=binding.model,
            prompt_profile=binding.prompt_profile,
            default_params=dict(binding.params),
        )

    def _client(self, handle: str) -> ChatClient:
        if self.client_factory is not None:
            return self.client_factory(handle)
        backend = self.config.backend(handle)
        return make_client(
            kind=backend.kind,
            base_url=backend.base_url,
            api_key=backend.api_key,
            timeout=backend.timeout_seconds,
        )

    def _run_narrative_context(
        self, *, season_id: str, run_id: str
    ) -> _RunNarrativeContext:
        row = self.database.connection.execute(
            "SELECT s.day_number, s.slot_number, s.run_number, s.scheduled_local "
            "FROM runs r JOIN schedule_slots s ON s.slot_id = r.slot_id "
            "WHERE r.run_id = ? AND r.season_id = ?",
            (run_id, season_id),
        ).fetchone()
        if row is None:
            raise LiveRuntimeConfigurationError(
                f"run {run_id!r} has no schedule metadata in season {season_id}"
            )
        run_number = int(row["run_number"])
        canon, memories = self._prior_run_state(
            season_id=season_id,
            before_run_number=run_number,
        )
        day_number = int(row["day_number"])
        return _RunNarrativeContext(
            day_number=day_number,
            slot_number=int(row["slot_number"]),
            run_number=run_number,
            scheduled_local=str(row["scheduled_local"]),
            previous_shared_outcome=self._previous_shared_outcome(
                season_id=season_id,
                before_run_number=run_number,
            ),
            prior_accepted_canon=canon,
            private_day_direction=self._private_day_direction(
                season_id=season_id,
                target_day_number=day_number,
            ),
            actor_memories=memories,
        )

    def _prior_run_state(
        self, *, season_id: str, before_run_number: int
    ) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
        rows = self.database.connection.execute(
            "SELECT e.event_type, e.payload_json FROM domain_events e "
            "JOIN runs r ON r.run_id = e.aggregate_id "
            "JOIN schedule_slots s ON s.slot_id = r.slot_id "
            "WHERE e.aggregate_type = 'run' AND r.season_id = ? "
            "AND s.run_number < ? "
            "AND e.event_type IN ('OrchestratorRoundAccepted', 'TurnAccepted') "
            "ORDER BY s.run_number, e.created_at, e.event_id",
            (season_id, before_run_number),
        ).fetchall()
        canon: list[str] = []
        seen_canon: set[str] = set()
        memories: dict[str, list[str]] = {}
        for row in rows:
            payload = _event_payload(row["payload_json"])
            if str(row["event_type"]) == "OrchestratorRoundAccepted":
                for value in payload.get("canon_updates", []):
                    claim = str(value).strip()
                    if claim and claim not in seen_canon:
                        seen_canon.add(claim)
                        canon.append(claim)
                continue
            character_id = str(payload.get("character_id", ""))
            if not character_id:
                continue
            actor_values = memories.setdefault(character_id, [])
            for value in payload.get("memory_notes", []):
                note = str(value).strip()
                if note and note not in actor_values:
                    actor_values.append(note)
        return tuple(canon), {
            character_id: tuple(values) for character_id, values in memories.items()
        }

    def _previous_shared_outcome(
        self, *, season_id: str, before_run_number: int
    ) -> str | None:
        row = self.database.connection.execute(
            "SELECT t.content_path FROM turns t "
            "JOIN runs r ON r.run_id = t.run_id "
            "JOIN schedule_slots s ON s.slot_id = r.slot_id "
            "WHERE r.season_id = ? AND s.run_number < ? "
            "AND t.character_id = '__orchestrator__' "
            "AND t.disposition = 'NARRATION_ACCEPT' "
            "ORDER BY s.run_number DESC, t.round_number DESC LIMIT 1",
            (season_id, before_run_number),
        ).fetchone()
        if row is None or not row["content_path"]:
            return None
        return self._read_private_artifact(
            row["content_path"], label="previous shared outcome"
        )

    def _private_day_direction(
        self, *, season_id: str, target_day_number: int
    ) -> str | None:
        if target_day_number <= 1:
            return None
        rows = self.database.connection.execute(
            "SELECT payload_json FROM domain_events "
            "WHERE aggregate_type = 'season' AND aggregate_id = ? "
            "AND event_type = 'NextDayDirectionCreated' "
            "ORDER BY created_at, event_id",
            (season_id,),
        ).fetchall()
        for row in reversed(rows):
            payload = _event_payload(row["payload_json"])
            if int(payload.get("target_day_number", 0)) != target_day_number:
                continue
            path = payload.get("content_path")
            if not path:
                raise LiveRuntimeConfigurationError(
                    f"day {target_day_number} direction has no private artifact"
                )
            return self._read_private_artifact(
                path, label=f"day {target_day_number} private direction"
            )
        return None

    def _read_private_artifact(self, value: object, *, label: str) -> str:
        private_root = self.roots.private.resolve()
        path = Path(str(value)).resolve()
        if path != private_root and private_root not in path.parents:
            raise LiveRuntimeConfigurationError(
                f"{label} points outside the private data root"
            )
        if not path.is_file():
            raise LiveRuntimeConfigurationError(f"{label} artifact is missing: {path}")
        return path.read_text(encoding="utf-8").strip()


def _binding_for(manifest: SceneModelManifest, character_id: str) -> ModelBinding | None:
    return manifest.actors.get(character_id) or manifest.actor_default


def _event_payload(value: object) -> dict[str, object]:
    try:
        payload = json.loads(str(value))
    except (TypeError, ValueError) as exc:
        raise LiveRuntimeConfigurationError("durable narrative event has invalid JSON") from exc
    if not isinstance(payload, dict):
        raise LiveRuntimeConfigurationError("durable narrative event payload is not an object")
    return payload


__all__ = [
    "EpisodeSpineBeat",
    "LiveRuntimeConfigurationError",
    "LiveSceneFactory",
    "ModelBinding",
    "SceneModelManifest",
    "validate_model_manifest",
]
