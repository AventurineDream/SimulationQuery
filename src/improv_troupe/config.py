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
    """One configured endpoint; Ollama uses its native API when selected."""

    model_config = ConfigDict(extra="forbid")

    base_url: str = Field(..., description="e.g. http://machine-a:11434/v1")
    kind: BackendKind = "openai"
    api_key: str = Field("not-needed", description="LM Studio/Ollama ignore this.")
    timeout_seconds: float = Field(
        300.0,
        gt=0,
        le=1800,
        description="HTTP connect/read timeout for model discovery and streaming calls.",
    )
    # Optional models this backend is expected to serve; used to resolve casting
    # hints without a live network round-trip when set.
    models: list[str] = Field(default_factory=list)


class ServiceSettings(BaseModel):
    """Deployment-neutral settings for the always-on Linux service.

    Proxmox may host this process in either a VM or an LXC container.  The
    application only needs a persistent data root; service managers and model
    endpoints remain outside this small settings object.
    """

    model_config = ConfigDict(extra="forbid")

    data_root: Path = Path("/var/lib/improv-troupe")
    poll_interval_seconds: float = Field(5.0, gt=0, le=300)
    recovery_wait_seconds: float = Field(
        14_400.0,
        ge=0,
        le=604_800,
        description=(
            "Delay before a model failure becomes eligible for creator-controlled "
            "recovery; zero removes the delay without enabling automatic retries."
        ),
    )
    auto_retry_timeouts: bool = Field(
        False,
        description="Automatically requeue only transport timeout interruptions before manual recovery.",
    )
    timeout_retry_max_attempts: int = Field(
        3,
        ge=1,
        le=10,
        description="Maximum total worker attempts for a timed-out scene before creator recovery.",
    )
    worker_id: str = Field("improv-worker", min_length=1)


class AppConfig(BaseModel):
    """The whole backends.yaml."""

    model_config = ConfigDict(extra="forbid")

    backends: dict[str, BackendConfig] = Field(default_factory=dict)
    default_backend: Optional[str] = None
    service: ServiceSettings = Field(default_factory=ServiceSettings)

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
