"""A deterministic fake backend for `--dry-run` and tests.

It ignores the model and improvises harmless placeholder lines so the full
pipeline (prompting -> streaming -> parsing -> export) can run with no servers.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from typing import AsyncIterator

from .client import Message

_LINES = [
    "Well, this is a fine mess we've landed in.",
    "[glancing at the door] I wouldn't count on that.",
    "You always say that, and you're always half right.",
    "Let's not pretend either of us planned this.",
    "There's a reason I stopped asking questions.",
    "Say what you mean. We don't have the time.",
    "[a long pause] Fine. Have it your way.",
    "I've seen how this ends. It isn't good.",
]


@dataclass(frozen=True)
class ScriptedStream:
    """A deterministic partial stream with an optional terminal failure."""

    chunks: tuple[str, ...]
    error: BaseException | None = None
    delay: float = 0.0


class FakeClient:
    """Yields a stable, character-flavored line per (speaker, turn)."""

    def __init__(self, models: list[str] | None = None, delay: float = 0.01):
        self._models = models or ["fake-1b", "fake-3b"]
        self._delay = delay
        self._counts: dict[str, int] = {}

    async def list_models(self) -> list[str]:
        return list(self._models)

    async def stream_chat(
        self, model: str, messages: list[Message], **params: object
    ) -> AsyncIterator[str]:
        speaker = _speaker_of(messages)
        n = self._counts.get(speaker, 0)
        self._counts[speaker] = n + 1
        idx = int(hashlib.sha1(f"{speaker}:{n}".encode()).hexdigest(), 16) % len(_LINES)
        line = _LINES[idx]
        for word in line.split(" "):
            await asyncio.sleep(self._delay)
            yield word + " "


class ScriptedFakeClient:
    """Deterministic scripted client for future workflow tests.

    Each call consumes one scripted response.  A response may be a string, an
    iterable of token strings, or an exception to raise.  The client records
    every request without requiring a network service or real model.
    """

    def __init__(self, responses: Iterable[object] = ()):
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def list_models(self) -> list[str]:
        return ["scripted-fake"]

    async def stream_chat(
        self, model: str, messages: list[Message], **params: object
    ) -> AsyncIterator[str]:
        call_number = len(self.calls)
        self.calls.append({"model": model, "messages": messages, "params": params})
        response: object = "scripted response"
        if call_number < len(self._responses):
            response = self._responses[call_number]
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, ScriptedStream):
            tokens = response.chunks
        elif isinstance(response, str):
            tokens = response.split(" ")
        else:
            tokens = list(response)  # type: ignore[arg-type]
        for token in tokens:
            delay = response.delay if isinstance(response, ScriptedStream) else 0
            await asyncio.sleep(delay)
            yield str(token)
        if isinstance(response, ScriptedStream) and response.error is not None:
            raise response.error


def _speaker_of(messages: list[Message]) -> str:
    """Recover which character we're generating for from the system prompt."""
    for msg in messages:
        if msg["role"] == "system" and msg["content"].startswith("You are "):
            # "You are NAME, a character ..."
            return msg["content"][len("You are ") :].split(",", 1)[0].strip()
    return "?"
