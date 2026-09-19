"""Bind each Actor in a plan to a concrete (backend, model) — the "support both" rule.

Resolution order per actor:
  1. Concrete: casting.backend + casting.model, if the backend exists.
  2. Hint:     casting.model_hint / size_class, matched against models advertised
               by the configured backends (from backends.yaml `models:` lists, or a
               live discovery map passed in).
  3. Fail with an actionable message.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import AppConfig
from .domain import Actor, ProductionPlan
from .engine.orchestrator import ActorRuntime
from .llm.client import ChatClient, make_client


class CastingError(Exception):
    """Raised when an actor cannot be bound to any available model."""


@dataclass
class Binding:
    actor_name: str
    backend: str
    model: str
    how: str  # "concrete" | "hint" | "fallback"


def resolve_bindings(
    plan: ProductionPlan,
    config: AppConfig,
    discovered: dict[str, list[str]] | None = None,
) -> list[Binding]:
    """Work out which backend+model plays each actor. Pure/no network."""
    available = _available_models(config, discovered)
    bindings: list[Binding] = []
    for actor in plan.cast:
        bindings.append(_resolve_one(actor, config, available))
    return bindings


def _resolve_one(
    actor: Actor, config: AppConfig, available: dict[str, list[str]]
) -> Binding:
    cast = actor.casting

    # 1. Concrete binding wins when the backend is known.
    if cast.backend and cast.model:
        if cast.backend not in config.backends:
            raise CastingError(
                f"{actor.name}: plan names backend {cast.backend!r} which is not in "
                f"backends.yaml ({', '.join(config.backends) or 'none'})."
            )
        return Binding(actor.name, cast.backend, cast.model, "concrete")

    # 2. Match a hinted model across whatever backends advertise it.
    if cast.model_hint:
        for handle, models in available.items():
            if _has_model(models, cast.model_hint):
                return Binding(actor.name, handle, cast.model_hint, "hint")

    # 3. Fall back to the default backend's first advertised model.
    default = config.default_backend
    if default and available.get(default):
        return Binding(actor.name, default, available[default][0], "fallback")

    raise CastingError(
        f"{actor.name}: could not bind to a model. Give casting.backend+model in the "
        f"plan, list models under backends in backends.yaml, or set default_backend. "
        f"(hint was {cast.model_hint!r}, size_class {cast.size_class!r})"
    )


def _available_models(
    config: AppConfig, discovered: dict[str, list[str]] | None
) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for handle, backend in config.backends.items():
        models = list(backend.models)
        if discovered and discovered.get(handle):
            models = discovered[handle]
        out[handle] = models
    return out


def _has_model(models: list[str], wanted: str) -> bool:
    w = wanted.lower()
    return any(w == m.lower() or w in m.lower() for m in models)


def build_runtimes(
    plan: ProductionPlan,
    config: AppConfig,
    bindings: list[Binding],
    client_factory=None,
) -> list[ActorRuntime]:
    """Turn bindings into live ActorRuntimes. `client_factory(backend_handle)`
    lets tests/dry-run inject a fake client; defaults to a real LLMClient."""
    if client_factory is None:
        client_factory = _default_client_factory(config)

    by_name = {a.name: a for a in plan.cast}
    runtimes: list[ActorRuntime] = []
    clients: dict[str, ChatClient] = {}
    for b in bindings:
        client = clients.setdefault(b.backend, client_factory(b.backend))
        runtimes.append(ActorRuntime(actor=by_name[b.actor_name], client=client, model=b.model))
    return runtimes


def _default_client_factory(config: AppConfig):
    def factory(handle: str) -> ChatClient:
        backend = config.backend(handle)
        return make_client(
            kind=backend.kind,
            base_url=backend.base_url,
            api_key=backend.api_key,
            timeout=backend.timeout_seconds,
        )

    return factory
