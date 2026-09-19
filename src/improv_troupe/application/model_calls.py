"""Durable execution boundary for one backend-neutral model-call attempt."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping

from ..clock import Clock, SystemClock
from ..infrastructure import ModelCallRepository, SQLiteDatabase
from ..llm.adapter import NormalizedCallResult, collect_chat
from ..llm.audit import AuditWriter
from ..llm.capabilities import supports_native_structured
from ..llm.client import ChatClient, Message


@dataclass
class ModelCallExecutor:
    """Persist private evidence around one streaming call.

    The executor does not parse or accept story content. Callers decide whether
    the normalized text becomes a turn, diary, or canon after this boundary.
    """

    database: SQLiteDatabase
    client: ChatClient
    clock: Clock
    audit_root: str | Path
    backend: str
    model: str
    prompt_profile: str = "general"
    default_params: Mapping[str, object] = field(default_factory=dict)
    calls: ModelCallRepository | None = None
    audit: AuditWriter = field(init=False)

    def __post_init__(self) -> None:
        self.calls = self.calls or ModelCallRepository(self.database)
        self.audit = AuditWriter(self.audit_root)

    async def execute(
        self,
        *,
        call_id: str,
        run_id: str | None,
        purpose: str,
        attempt: int,
        messages: list[Message],
        secrets: tuple[str, ...] = (),
        params: Mapping[str, object] | None = None,
        schema_name: str | None = None,
        tagged_format_instructions: str | None = None,
        character_id: str | None = None,
        prompt_version_id: str | None = None,
        schema_version_id: str | None = None,
        context_version_id: str | None = None,
        role_sheet_version_id: str | None = None,
        character_card_version_id: str | None = None,
        correction_of_call_id: str | None = None,
    ) -> NormalizedCallResult:
        messages = self._adapt_messages(messages)
        research = getattr(self.client, "research_transport", False)
        timer = SystemClock() if research else self.clock
        prompt_path = Path("model-calls") / call_id / "prompt.md"
        prompt = json.dumps(messages, sort_keys=True, ensure_ascii=False, indent=2)
        prompt_artifact = self.audit.write_text(prompt_path, prompt, secrets=secrets)
        response_format_mode = None
        if schema_name is not None and tagged_format_instructions is not None:
            response_format_mode = (
                "NATIVE_SCHEMA" if supports_native_structured(self.client) else "TAGGED_FALLBACK"
            )
        self.calls.create(
            call_id=call_id,
            run_id=run_id,
            purpose=purpose,
            attempt=attempt,
            status="STREAMING",
            backend=self.backend,
            model=self.model,
            started_at=timer.now().isoformat(),
            prompt_path=str(prompt_artifact.path),
            prompt_sha256=prompt_artifact.sha256,
            character_id=character_id,
            response_format_mode=response_format_mode,
            prompt_version_id=prompt_version_id,
            schema_version_id=schema_version_id or (f"{schema_name}:v1" if schema_name else None),
            context_version_id=context_version_id,
            role_sheet_version_id=role_sheet_version_id,
            character_card_version_id=character_card_version_id,
            correction_of_call_id=correction_of_call_id,
        )

        effective_params = dict(self.default_params)
        effective_params.update(params or {})
        if research:
            effective_params["_sq_meta"] = {
                "call_id": call_id, "purpose": purpose, "run_id": run_id,
                "character_id": character_id, "correction_of_call_id": correction_of_call_id,
            }
        result = await collect_chat(
            self.client,
            call_id=call_id,
            purpose=purpose,
            backend=self.backend,
            model=self.model,
            messages=messages,
            clock=timer,
            schema_name=schema_name,
            tagged_format_instructions=tagged_format_instructions,
            **effective_params,
        )
        output_suffix = "output.md" if result.status.value == "COMPLETED" else "output.partial.md"
        output_artifact = self.audit.write_text(
            Path("model-calls") / call_id / output_suffix,
            result.text,
            secrets=secrets,
        )
        actual_response_format_mode = response_format_mode
        if schema_name is not None and tagged_format_instructions is not None:
            actual_response_format_mode = getattr(
                self.client, "last_response_format_mode", response_format_mode
            )
        self.calls.finish(
            call_id=call_id,
            status=result.status.value,
            ended_at=result.ended_at.isoformat(),
            latency_ms=result.latency_ms,
            output_path=str(output_artifact.path),
            output_sha256=output_artifact.sha256,
            finish_reason=result.finish_reason,
            cancelled=result.cancelled,
            error_type=result.error_type,
            usage_json=(json.dumps(asdict(result.usage), sort_keys=True) if result.usage else None),
            response_format_mode=actual_response_format_mode,
        )
        if result.status.value == "COMPLETED":
            self.calls.record_diagnostics(
                call_id=call_id,
                parse_status="PENDING",
                validation_status="PENDING",
                acceptance_status="PENDING",
                render_status="PENDING",
            )
        else:
            self.calls.record_diagnostics(
                call_id=call_id,
                parse_status="NOT_REACHED",
                validation_status="NOT_REACHED",
                acceptance_status="NOT_REACHED",
                render_status="NOT_REACHED",
                validator_code="TRANSPORT_FAILURE",
                validator_detail=result.error_type,
            )
        return result

    def _adapt_messages(self, messages: list[Message]) -> list[Message]:
        """Respect model-specific chat-template constraints at the transport edge."""
        if self.prompt_profile != "peach":
            return messages
        systems = [str(message["content"]) for message in messages if message["role"] == "system"]
        adapted: list[Message] = []
        if systems:
            adapted.append({"role": "system", "content": "\n\n".join(systems)})
        for message in messages:
            if message["role"] == "system":
                continue
            role = "character" if message["role"] == "assistant" else message["role"]
            adapted.append({"role": role, "content": message["content"]})  # type: ignore[typeddict-item]
        return adapted


__all__ = ["ModelCallExecutor"]
