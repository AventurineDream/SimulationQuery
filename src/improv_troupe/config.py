"""Backend registry: maps logical handles to real endpoints (backends.yaml).

Plans reference backends by *handle* (or by casting hints), never by raw URL, so a
plan authored on one machine stays portable to another. This file is where the
network topology of your two machines actually lives.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

BackendKind = Literal["lmstudio", "ollama", "openai"]


class BackendConfig(BaseModel):
    """One OpenAI-compatible endpoint (LM Studio, Ollama, or generic)."""

    model_config = ConfigDict(extra="forbid")

    base_url: str = Field(..., description="e.g. http://machine-a:11434/v1")
    kind: BackendKind = "openai"
    api_key: str = Field("not-needed", description="LM Studio/Ollama ignore this.")
    # Optional models this backend is expected to serve; used to resolve casting
    # hints without a live network round-trip when set.
    models: list[str] = Field(default_factory=list)


class AppConfig(BaseModel):
    """The whole backends.yaml."""

    model_config = ConfigDict(extra="forbid")

    backends: dict[str, BackendConfig]
    default_backend: Optional[str] = None

    @classmethod
    def load(cls, path: str | Path) -> "AppConfig":
        path = Path(path)
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)

    def backend(self, handle: str) -> BackendConfig:
        try:
            return self.backends[handle]
        except KeyError:
            known = ", ".join(sorted(self.backends)) or "(none)"
            raise KeyError(f"unknown backend {handle!r}; known handles: {known}") from None
