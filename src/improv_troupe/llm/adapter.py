"""Backend-neutral normalization around the low-level streaming client."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from ..clock import Clock, SystemClock
from .capabilities import stream_with_schema
from .client import ChatClient, Message


class NormalizedCallStatus(str, Enum):
    """The durable disposition of one model-call attempt."""

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


@dataclass(frozen=True)
class Usage:
    """Optional token accounting supplied by a capable backend."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class NormalizedCallResult:
    """A backend-independent record of a streaming attempt.

    The low-level client does not expose provider-specific usage or finish
    reasons, so those fields remain optional. Errors retain only their type;
    raw exception text belongs in a private audit record, not a public result.
    """

    call_id: str
    purpose: str
    backend: str
    model: str
    status: NormalizedCallStatus
    text: str
    started_at: datetime
    ended_at: datetime
    latency_ms: int
    usage: Usage | None = None
    finish_reason: str | None = None
    cancelled: bool = False
    error_type: str | None = None
    parse_warnings: tuple[str, ...] = ()


async def collect_chat(
    client: ChatClient,
    *,
    call_id: str,
    purpose: str,
    backend: str,
    model: str,
    messages: list[Message],
    clock: Clock | None = None,
    schema_name: str | None = None,
    tagged_format_instructions: str | None = None,
    **params: object,
) -> NormalizedCallResult:
    """Collect one stream while preserving partial output on failure/cancel."""

    timer = clock or SystemClock()
    started = _aware_now(timer)
    chunks: list[str] = []
    try:
        if schema_name is not None and tagged_format_instructions is not None:
            stream = stream_with_schema(
                client,
                model=model,
                messages=messages,
                schema_name=schema_name,
                tagged_format_instructions=tagged_format_instructions,
                **params,
            )
        else:
            stream = client.stream_chat(model, messages, **params)
        async for chunk in stream:
            chunks.append(chunk)
    except asyncio.CancelledError:
        ended = _aware_now(timer)
        return _result(
            call_id=call_id,
            purpose=purpose,
            backend=backend,
            model=model,
            status=NormalizedCallStatus.INTERRUPTED,
            text="".join(chunks),
            started=started,
            ended=ended,
            cancelled=True,
            error_type="CancelledError",
        )
    except Exception as exc:
        ended = _aware_now(timer)
        return _result(
            call_id=call_id,
            purpose=purpose,
            backend=backend,
            model=model,
            status=NormalizedCallStatus.FAILED,
            text="".join(chunks),
            started=started,
            ended=ended,
            error_type=type(exc).__name__,
        )

    ended = _aware_now(timer)
    result = _result(
        call_id=call_id,
        purpose=purpose,
        backend=backend,
        model=model,
        status=NormalizedCallStatus.COMPLETED,
        text="".join(chunks),
        started=started,
        ended=ended,
    )
    metadata = getattr(client, "last_metadata", None)
    if getattr(client, "research_transport", False) and metadata:
        usage = metadata.get("usage", {})
        result = replace(result, finish_reason=metadata.get("finish_reason"), usage=Usage(**usage))
    return result


def _result(
    *,
    call_id: str,
    purpose: str,
    backend: str,
    model: str,
    status: NormalizedCallStatus,
    text: str,
    started: datetime,
    ended: datetime,
    cancelled: bool = False,
    error_type: str | None = None,
) -> NormalizedCallResult:
    latency_ms = max(0, int((ended - started).total_seconds() * 1000))
    return NormalizedCallResult(
        call_id=call_id,
        purpose=purpose,
        backend=backend,
        model=model,
        status=status,
        text=text,
        started_at=started,
        ended_at=ended,
        latency_ms=latency_ms,
        cancelled=cancelled,
        error_type=error_type,
    )


def _aware_now(clock: Clock) -> datetime:
    value = clock.now()
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value


__all__ = ["NormalizedCallResult", "NormalizedCallStatus", "Usage", "collect_chat"]
