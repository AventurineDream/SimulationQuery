from datetime import datetime, timezone

from improv_troupe.application.model_calls import ModelCallExecutor
from improv_troupe.clock import VirtualClock
from improv_troupe.infrastructure import SQLiteDatabase
from improv_troupe.llm.fake import ScriptedFakeClient


def test_peach_profile_merges_all_system_messages_first(tmp_path):
    database = SQLiteDatabase(tmp_path / "test.sqlite3")
    database.migrate()
    executor = ModelCallExecutor(
        database=database, client=ScriptedFakeClient([]),
        clock=VirtualClock(datetime.now(timezone.utc)), audit_root=tmp_path,
        backend="local", model="peach", prompt_profile="peach",
    )
    messages = executor._adapt_messages([
        {"role": "system", "content": "identity"},
        {"role": "user", "content": "scene"},
        {"role": "system", "content": "format"},
        {"role": "assistant", "content": "prior"},
    ])
    assert messages == [
        {"role": "system", "content": "identity\n\nformat"},
        {"role": "user", "content": "scene"},
        {"role": "character", "content": "prior"},
    ]
