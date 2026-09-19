"""One recorded native Ollama request per call, with bounded context and no fallback."""
from __future__ import annotations

import hashlib
import json
import time
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..llm.audit import AuditWriter
from ..llm.client import _ollama_api_url, _ollama_options, _ollama_think
from ..llm.structured import schema_for


class ResearchTransportError(RuntimeError):
    pass


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def digest(value) -> str:
    return hashlib.sha256(dumps(value).encode()).hexdigest()


class ResearchOllamaClient:
    """Isolated transport for research. It does not alter the legacy client defaults.

    Response bytes are saved even if JSON parsing, completion, or budget checks fail.
    A failed request latches this client closed; use a new client for a new world
    or an independent probe branch, never to resume an interrupted parent world.
    """

    research_transport = True

    def __init__(self, backend, audit_root: Path, *, world_id: str, seed: int,
                 phase: str = "parent", http_transport=None):
        self.backend = backend
        self.base_url = _ollama_api_url(backend.base_url)
        self.audit = AuditWriter(audit_root)
        self.world_id, self.seed, self.phase = world_id, seed, phase
        self.http_transport = http_transport
        self.failed = False
        self.last_metadata = None
        self.last_response_format_mode = "NATIVE_SCHEMA"

    def _http(self):
        return httpx.AsyncClient(
            timeout=self.backend.timeout_seconds, transport=self.http_transport,
            headers={"Authorization": f"Bearer {self.backend.api_key}"},
        )

    async def identity(self, models: list[str]) -> dict:
        """Read model digests, templates, defaults and server version; no generation."""
        async with self._http() as client:
            tags = await client.get(f"{self.base_url}/tags")
            tags.raise_for_status()
            version = await client.get(f"{self.base_url}/version")
            version.raise_for_status()
            inventory = {m["name"]: m for m in tags.json()["models"]}
            resolved = {}
            for model in sorted(set(models)):
                if model not in inventory or not inventory[model].get("digest"):
                    raise ResearchTransportError(f"model has no exact installed digest: {model}")
                response = await client.post(f"{self.base_url}/show", json={"model": model})
                response.raise_for_status()
                show = response.json()
                # /show preserves provider-injected templates/system/default options.
                resolved[model] = {"digest": inventory[model]["digest"], "show": show}
            return {"server": self.base_url, "version": version.json(), "models": resolved}

    async def list_models(self):
        async with self._http() as client:
            result = await client.get(f"{self.base_url}/tags")
            result.raise_for_status()
            return [m["name"] for m in result.json()["models"]]

    async def stream_structured_chat(self, model, messages, *, schema_name, **params):
        messages = [*messages, {"role": "system", "content": (
            "Return only a single JSON object that conforms exactly to the provided "
            "response schema. Do not use XML-style tags, Markdown, or prose outside the JSON object."
        )}]
        async for text in self._request(model, messages, schema=schema_for(schema_name), **params):
            yield text

    async def stream_chat(self, model, messages, **params):
        async for text in self._request(model, messages, schema=None, **params):
            yield text

    async def _request(self, model, messages, *, schema, **params):
        if self.failed:
            raise ResearchTransportError("world/branch transport is stopped after a prior fault")
        meta = dict(params.pop("_sq_meta", {}))
        call_id = meta.get("call_id")
        if not call_id:
            raise ResearchTransportError("research call requires a stable call_id")
        request_id = digest([self.world_id, self.phase, call_id])[:24]
        folder = Path(request_id)
        if (self.audit.root / folder).exists():
            raise ResearchTransportError("duplicate research request; automatic replay is prohibited")
        options = _ollama_options(params)
        unknown = set(params) - {
            "temperature", "top_p", "min_p", "repeat_penalty", "num_predict", "max_tokens",
            "num_ctx", "seed", "thinking", "reasoning_effort",
        }
        if unknown:
            raise ResearchTransportError(f"unrecorded/unsupported sampling options: {sorted(unknown)}")
        options["seed"] = int(digest([self.seed, self.phase, call_id])[:8], 16) % (2**31)
        payload = {"model": model, "messages": messages, "stream": False,
                   "options": options, "think": _ollama_think(params, default=False)}
        if schema is not None:
            payload["format"] = schema
        record = {"request_id": request_id, "world_id": self.world_id, "phase": self.phase,
                  **meta, "started_at_utc": datetime.now(timezone.utc).isoformat(),
                  "network_sent": False, "status": "FAILED", "payload_sha256": digest(payload)}
        self.last_metadata = None
        self.audit.write_text(folder / "request.json", dumps(payload))
        started = time.monotonic()
        raw = bytearray()
        response = None
        try:
            context_limit = options.get("num_ctx")
            output_limit = options.get("num_predict")
            if not isinstance(context_limit, int) or not isinstance(output_limit, int):
                raise ResearchTransportError("explicit num_ctx and num_predict are required")
            # Conservative admission guard, not an exact tokenizer. Include schemas
            # and allowance for chat-template expansion. Actual provider counts are
            # checked below; never silently drop history or enlarge context.
            input_bound = len(dumps(messages).encode()) + len(dumps(schema).encode()) + 1024
            record["input_utf8_budget_bound"] = input_bound
            if input_bound + output_limit > context_limit:
                raise ResearchTransportError("context admission budget exceeded; freeze a larger budget before a new pilot")
            # Persist request identity before I/O, and each received byte prefix
            # during I/O. A process kill may prevent a final record, but does not
            # erase already delivered response bytes or their request ancestry.
            self.audit.write_text(folder / "started.json", dumps(record))
            raw_path = self.audit.root / folder / "response.bin"
            with raw_path.open("xb") as handle:
                os.chmod(raw_path, 0o600)
                async with self._http() as client:
                    record["network_sent"] = True
                    async with client.stream("POST", f"{self.base_url}/chat", json=payload) as response:
                        async for chunk in response.aiter_bytes():
                            raw.extend(chunk)
                            handle.write(chunk)
                            handle.flush()
                            os.fsync(handle.fileno())
                        response.raise_for_status()
            data = json.loads(raw)
            record["provider_created_at"] = data.get("created_at")
            record["finish_reason"] = data.get("done_reason")
            prompt_count, output_count = data.get("prompt_eval_count"), data.get("eval_count")
            record["usage"] = {"prompt_tokens": prompt_count, "completion_tokens": output_count,
                               "total_tokens": (prompt_count + output_count
                                                if isinstance(prompt_count, int) and isinstance(output_count, int) else None)}
            if data.get("done") is not True or data.get("done_reason") != "stop":
                raise ResearchTransportError("response has no verified normal completion")
            if not isinstance(prompt_count, int) or not isinstance(output_count, int):
                raise ResearchTransportError("provider token counts are missing")
            if prompt_count + output_limit > context_limit or output_count >= output_limit:
                raise ResearchTransportError("response is at context/output capacity")
            message = data.get("message") or {}
            if message.get("tool_calls"):
                raise ResearchTransportError("tool calls are recorded but unsupported in Pilot 2")
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise ResearchTransportError("empty visible response; no fallback")
            record["status"] = "COMPLETED"
        except BaseException as exc:
            self.failed = True
            record["error_type"] = type(exc).__name__
            # Keep error details local; do not serialize credentials/HTTP headers.
            record["error_detail"] = str(exc) if isinstance(exc, ResearchTransportError) else None
            raise
        finally:
            record["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
            record["latency_ms"] = round((time.monotonic() - started) * 1000)
            record["http_status"] = response.status_code if response is not None else None
            self.audit.write_text(folder / "response.txt", raw.decode("utf-8", errors="replace"))
            record["response_sha256"] = hashlib.sha256(raw).hexdigest()
            self.audit.write_text(folder / "record.json", dumps(record))
            self.last_metadata = record
        yield content
