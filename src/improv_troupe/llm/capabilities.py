"""Optional structured-output capability negotiation over :class:`ChatClient`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from .client import ChatClient, Message


@runtime_checkable
class StructuredChatClient(ChatClient, Protocol):
    """Optional provider-native structured streaming surface."""

    async def stream_structured_chat(
        self,
        model: str,
        messages: list[Message],
        *,
        schema_name: str,
        **params: object,
    ) -> AsyncIterator[str]:
        """Yield a provider-validated structured response."""
        ...


def supports_native_structured(client: ChatClient) -> bool:
    """Return whether the backend advertises the optional structured method."""

    return callable(getattr(client, "stream_structured_chat", None))


async def stream_with_schema(
    client: ChatClient,
    *,
    model: str,
    messages: list[Message],
    schema_name: str,
    tagged_format_instructions: str,
    **params: object,
) -> AsyncIterator[str]:
    """Use native structured output when available, otherwise strict tags."""

    native = getattr(client, "stream_structured_chat", None)
    if callable(native):
        emitted = False
        try:
            async for chunk in native(model, messages, schema_name=schema_name, **params):
                # A whitespace-only provider response cannot satisfy a schema.
                # Treat it as absent so the bounded tagged fallback still gets
                # one chance to produce visible content.
                if chunk and chunk.strip():
                    emitted = True
                    yield chunk
        except ValueError:
            if emitted:
                raise
        else:
            if emitted:
                _set_response_format_mode(client, "NATIVE_SCHEMA")
                return

    if getattr(client, "research_transport", False):
        raise RuntimeError("research calls require native output; no format fallback")

    _set_response_format_mode(client, "TAGGED_FALLBACK")
    fallback_messages = [
        *messages,
        {
            "role": "system",
            "content": (
                "Native structured output is unavailable for this response. Return only the "
                f"following strict format for {schema_name}:\n{tagged_format_instructions}\n"
                "Return one complete response, close every opening tag before ending, use no "
                "Markdown fences or prose outside the required format, and do not quote the "
                "whole response."
            ),
        },
    ]
    # A response-format fallback is useful only if it reaches visible content.
    # On reasoning-capable local backends, preserve the native binding for the
    # first attempt but disable hidden thinking for this one format-recovery
    # attempt. Otherwise a model can spend its entire completion in a private
    # reasoning channel and return an empty, falsely-successful response.
    fallback_params = {**params, "reasoning_effort": "none"}
    async for chunk in client.stream_chat(model, fallback_messages, **fallback_params):
        yield chunk


def _set_response_format_mode(client: ChatClient, mode: str) -> None:
    """Expose the actual provider path to the durable call boundary.

    Calls are serial per backend in the worker, so this transient value is safe
    to read after collection and prevents a fallback from being reported as a
    native-schema success.
    """

    setattr(client, "last_response_format_mode", mode)


__all__ = ["StructuredChatClient", "stream_with_schema", "supports_native_structured"]
