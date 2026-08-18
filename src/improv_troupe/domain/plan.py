"""The ProductionPlan schema — the contract between any planner and the app.

A plan is produced by *some* planner (a Claude desktop skill, a local agent, or a
hand-written file) and consumed by the performance engine. Keep this stable and
versioned: everything downstream depends on it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0"

SizeClass = Literal["tiny", "small", "medium", "large"]
TurnStrategy = Literal["round_robin", "random"]


class Scene(BaseModel):
    """Where we are and how we got here."""

    setting: str = Field(..., description="Physical/temporal setting of the scene.")
    premise: str = Field(..., description="The situation the characters are in.")
    tone: str = Field("", description="Emotional register, e.g. 'tense, darkly funny'.")
    genre: str = Field("", description="e.g. 'dramedy', 'noir', 'sci-fi'.")
    opening_beat: str = Field(
        ...,
        description="The first thing that happens; seeds the transcript as a stage direction.",
    )


class Constraints(BaseModel):
    """Guardrails and shape for the performance."""

    content: list[str] = Field(
        default_factory=list, description="Content rules, e.g. 'keep it PG-13'."
    )
    max_turns: int = Field(20, ge=1, le=500, description="Hard cap on spoken turns.")
    turn_length: str = Field(
        "1-4 sentences, plus an optional [stage direction]",
        description="Guidance given to each actor about how long a turn should be.",
    )
    objective: str = Field("", description="Dramatic goal to steer toward (optional).")
    end_condition: str = Field(
        "", description="Human-readable note on how the scene should resolve (advisory)."
    )


class Casting(BaseModel):
    """How a character binds to an actual model.

    Supports BOTH styles:
      * concrete  -> set `backend` (a handle in backends.yaml) and `model`.
      * portable  -> leave those empty and give hints; the app resolves at import.
    Concrete wins when present and resolvable; otherwise hints are used.
    """

    backend: Optional[str] = Field(
        None, description="Concrete backend handle from backends.yaml (optional)."
    )
    model: Optional[str] = Field(
        None, description="Concrete model id on that backend (optional)."
    )
    model_hint: Optional[str] = Field(
        None, description="Suggested model id if concrete binding is absent."
    )
    size_class: Optional[SizeClass] = Field(
        None, description="Rough size preference used to pick a model."
    )
    tags: list[str] = Field(
        default_factory=list, description="Free-form casting tags, e.g. ['fast']."
    )


class SamplingParams(BaseModel):
    """Per-actor generation settings. Extra keys pass through to the backend."""

    model_config = ConfigDict(extra="allow")

    temperature: float = Field(0.9, ge=0.0, le=2.0)
    top_p: float = Field(0.95, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(300, ge=1)


class Actor(BaseModel):
    """A cast member: a character plus the model that plays them."""

    name: str = Field(..., description="Character name; used as the script label.")
    character_brief: str = Field(
        ..., description="Who they are: background, wants, attitude, manner."
    )
    voice_notes: str = Field("", description="How they talk: rhythm, tics, vocabulary.")
    casting: Casting = Field(default_factory=Casting)
    params: SamplingParams = Field(default_factory=SamplingParams)


class Direction(BaseModel):
    """How turns are scheduled."""

    turn_strategy: TurnStrategy = "round_robin"
    first_speaker: Optional[str] = Field(
        None, description="Name of the actor who opens; defaults to first in cast."
    )
    seed: Optional[int] = Field(None, description="RNG seed for reproducible runs.")


class Meta(BaseModel):
    """Provenance. Extra keys allowed."""

    model_config = ConfigDict(extra="allow")

    created_by: str = ""
    created_at: Optional[datetime] = None


class ProductionPlan(BaseModel):
    """Everything the performance engine needs to run a scene."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    title: str
    logline: str = ""
    scene: Scene
    constraints: Constraints = Field(default_factory=Constraints)
    cast: list[Actor] = Field(..., min_length=1)
    direction: Direction = Field(default_factory=Direction)
    meta: Meta = Field(default_factory=Meta)

    @model_validator(mode="after")
    def _validate_cross_references(self) -> "ProductionPlan":
        names = [a.name for a in self.cast]
        if len(set(names)) != len(names):
            raise ValueError("cast member names must be unique")
        first = self.direction.first_speaker
        if first is not None and first not in names:
            raise ValueError(
                f"direction.first_speaker {first!r} is not one of the cast: {names}"
            )
        return self

    @property
    def cast_names(self) -> list[str]:
        return [a.name for a in self.cast]
