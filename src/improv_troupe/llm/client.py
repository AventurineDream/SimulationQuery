"""Async OpenAI-compatible chat client.

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

    def __init__(self, base_url: str, api_key: str = "not-needed", timeout: float = 120.0):
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
