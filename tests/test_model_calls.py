import asyncio
from datetime import datetime, timezone

from improv_troupe.application import ModelCallExecutor
from improv_troupe.clock import VirtualClock
from improv_troupe.infrastructure import SQLiteDatabase
from improv_troupe.llm import ScriptedFakeClient, ScriptedStream


def _executor(tmp_path, client):
    database = SQLiteDatabase(tmp_path / "state" / "improv.sqlite3")
    database.migrate()
    return ModelCallExecutor(
        database=database,
        client=client,
        clock=VirtualClock(datetime(2026, 8, 21, 6, tzinfo=timezone.utc)),
        audit_root=tmp_path / "private",
        backend="scripted-fake",
        model="candidate-8b",
    )


def test_model_call_executor_persists_success_and_private_prompt_output(tmp_path):
    executor = _executor(tmp_path, ScriptedFakeClient([ScriptedStream(("hello ", "world"))]))
    result = asyncio.run(
        executor.execute(
            call_id="call-success",
            run_id=None,
            purpose="actor_turn",
            attempt=1,
            messages=[{"role": "user", "content": "token=secret"}],
            secrets=("secret",),
            schema_name="actor_turn",
            tagged_format_instructions="<ACTOR_TEXT>...</ACTOR_TEXT>",
            character_id="mara",
            prompt_version_id="scene-actor-v1",
            context_version_id="scene:S02-run-01:round:1:v1",
            role_sheet_version_id="mara:v2",
        )
    )
    assert result.text == "hello world"
    row = executor.database.connection.execute(
        "SELECT status, prompt_path, output_path, prompt_sha256, output_sha256, "
        "response_format_mode, character_id, prompt_version_id, schema_version_id, "
        "context_version_id, role_sheet_version_id "
        "FROM model_calls WHERE call_id = ?",
        ("call-success",),
    ).fetchone()
    assert row["status"] == "COMPLETED"
    assert row["output_path"].endswith("output.md")
    assert row["prompt_sha256"]
    assert row["output_sha256"]
    assert row["response_format_mode"] == "TAGGED_FALLBACK"
    assert row["character_id"] == "mara"
    assert row["prompt_version_id"] == "scene-actor-v1"
    assert row["schema_version_id"] == "actor_turn:v1"
    assert row["context_version_id"] == "scene:S02-run-01:round:1:v1"
    assert row["role_sheet_version_id"] == "mara:v2"
    prompt = open(row["prompt_path"], encoding="utf-8").read()
    assert "secret" not in prompt
    assert "[REDACTED]" in prompt


def test_model_call_executor_keeps_partial_output_and_failure_metadata(tmp_path):
    executor = _executor(
        tmp_path,
        ScriptedFakeClient([ScriptedStream(("partial",), error=TimeoutError())]),
    )
    result = asyncio.run(
        executor.execute(
            call_id="call-failure",
            run_id=None,
            purpose="diary",
            attempt=1,
            messages=[{"role": "user", "content": "write"}],
        )
    )
    assert result.error_type == "TimeoutError"
    row = executor.database.connection.execute(
        "SELECT status, error_type, output_path FROM model_calls WHERE call_id = ?",
        ("call-failure",),
    ).fetchone()
    assert row["status"] == "FAILED"
    assert row["error_type"] == "TimeoutError"
    assert row["output_path"].endswith("output.partial.md")
    assert open(row["output_path"], encoding="utf-8").read() == "partial"


def test_model_call_executor_merges_binding_defaults_with_call_params(tmp_path):
    client = ScriptedFakeClient(["ok"])
    executor = _executor(tmp_path, client)
    executor.default_params = {
        "temperature": 0.7,
        "reasoning_effort": "none",
    }

    asyncio.run(
        executor.execute(
            call_id="call-params",
            run_id=None,
            purpose="actor_turn",
            attempt=1,
            messages=[{"role": "user", "content": "write"}],
            params={"max_tokens": 640},
        )
    )

    assert client.calls[0]["params"] == {
        "temperature": 0.7,
        "reasoning_effort": "none",
        "max_tokens": 640,
    }
