"""Async chat clients for OpenAI-compatible and native Ollama backends.

Works against any `/v1`-style endpoint: LM Studio, Ollama, vLLM, etc. The engine
depends only on the small `ChatClient` protocol below, so tests and `--dry-run`
can swap in a fake without touching the network.
"""

from __future__ import annotations

import json
from typing import AsyncIterator, Protocol, TypedDict, runtime_checkable

import httpx


class Message(TypedDict):
    role: str  # "system" | "user" | "assistant"
    content: str


@runtime_checkable
class ChatClient(Protocol):
    """Minimal surface the engine needs from any backend."""

    async def stream_chat(
        self, model: str, messages: list[Message], **params: object
    ) -> AsyncIterator[str]:
        """Yield content tokens as they arrive."""
        ...

    async def list_models(self) -> list[str]:
        """Return model ids currently available on this backend."""
        ...


class LLMClient:
    """Concrete OpenAI-compatible client backed by httpx."""

    def __init__(self, base_url: str, api_key: str = "not-needed", timeout: float = 300.0):
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._timeout = timeout

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self.base_url}/models", headers=self._headers)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return [m["id"] for m in data if "id" in m]

    async def stream_chat(
        self, model: str, messages: list[Message], **params: object
    ) -> AsyncIterator[str]:
        payload: dict[str, object] = {
            "model": model,
            "messages": messages,
            "stream": True,
            **{k: v for k, v in params.items() if v is not None},
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers,
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    token = _parse_sse_line(line)
                    if token:
                        yield token


class OllamaClient:
    """Ollama's native API, including provider-constrained JSON schemas."""

    def __init__(self, base_url: str, api_key: str = "not-needed", timeout: float = 300.0):
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.base_url = _ollama_api_url(base_url)
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._timeout = timeout

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self.base_url}/tags", headers=self._headers)
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", []) if "name" in m]

    async def stream_chat(
        self, model: str, messages: list[Message], **params: object
    ) -> AsyncIterator[str]:
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": _ollama_options(params),
        }
        think = _ollama_think(params)
        if think is not None:
            payload["think"] = think
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/chat", headers=self._headers, json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    token = _parse_ollama_line(line)
                    if token:
                        yield token

    async def stream_structured_chat(
        self,
        model: str,
        messages: list[Message],
        *,
        schema_name: str,
        **params: object,
    ) -> AsyncIterator[str]:
        from .structured import schema_for

        payload = {
            "model": model,
            "messages": [
                *messages,
                {
                    "role": "system",
                    "content": (
                        "Return only a single JSON object that conforms exactly to the "
                        "provided response schema. Do not use XML-style tags, Markdown, "
                        "or prose outside the JSON object."
                    ),
                },
            ],
            "format": schema_for(schema_name),
            "stream": False,
            "options": _ollama_options(params),
        }
        # Schema-constrained calls need their answer in ``message.content``.
        # Thinking-capable models otherwise may finish a JSON grammar turn in
        # ``message.thinking`` and leave the validated content blank.
        payload["think"] = _ollama_think(params, default=False)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat", headers=self._headers, json=payload
            )
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content")
            if not isinstance(content, str):
                raise ValueError("Ollama structured response did not contain message.content")
            yield content


def make_client(
    *, kind: str, base_url: str, api_key: str = "not-needed", timeout: float = 300.0
) -> ChatClient:
    """Select the narrowest correct transport for a configured backend."""

    if kind == "ollama":
        return OllamaClient(base_url=base_url, api_key=api_key, timeout=timeout)
    return LLMClient(base_url=base_url, api_key=api_key, timeout=timeout)


def _parse_sse_line(line: str) -> str:
    """Extract the content delta from one Server-Sent-Events line."""
    line = line.strip()
    if not line or not line.startswith("data:"):
        return ""
    data = line[len("data:") :].strip()
    if data == "[DONE]":
        return ""
    try:
        chunk = json.loads(data)
    except json.JSONDecodeError:
        return ""
    choices = chunk.get("choices") or [{}]
    delta = choices[0].get("delta") or {}
    return delta.get("content") or ""


def _ollama_api_url(base_url: str) -> str:
    """Normalize a configured Ollama root or legacy ``/v1`` URL to ``/api``."""

    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    if normalized.endswith("/api"):
        return normalized
    return f"{normalized}/api"


def _ollama_options(params: dict[str, object]) -> dict[str, object]:
    """Translate portable application sampling parameters to Ollama options."""

    options: dict[str, object] = {}
    aliases = {"max_tokens": "num_predict"}
    supported = {"temperature", "top_p", "min_p", "seed", "num_ctx", "repeat_penalty"}
    for key, value in params.items():
        if value is None:
            continue
        target = aliases.get(key, key)
        if target in supported or target == "num_predict":
            options[target] = value
    return options


def _ollama_think(params: dict[str, object], *, default: bool | None = None) -> bool | str | None:
    """Resolve an explicit provider thinking setting before portable defaults.

    Most schema-bound calls safely suppress hidden thinking, but some providers
    (including GPT-OSS through Ollama) emit visible content only when thinking
    is enabled.  A binding may therefore opt in with ``thinking: true``.
    ``reasoning_effort: none`` remains the portable way to suppress it where no
    provider-specific setting was chosen.
    """

    explicit = params.get("thinking")
    if isinstance(explicit, bool):
        return explicit
    if isinstance(explicit, str):
        if explicit not in {"low", "medium", "high"}:
            raise ValueError("unsupported Ollama thinking level")
        return explicit
    return False if params.get("reasoning_effort") == "none" else default


def _parse_ollama_line(line: str) -> str:
    try:
        chunk = json.loads(line)
    except json.JSONDecodeError:
        return ""
    return (chunk.get("message") or {}).get("content") or ""
