import asyncio
import json
import httpx
from improv_troupe.application.diaries import _diary_generation_params
from improv_troupe.llm.client import _ollama_think
from tests.test_diaries import _service
from tests.test_sq_research import client, response


def test_diary_level_overrides_only_thinking_and_preserves_budget(tmp_path):
    db, clock, service, actor = _service(tmp_path, [])
    actor.executor.default_params = {"num_predict": 4096, "thinking": True}
    assert _diary_generation_params(actor.executor) == {}
    actor.executor.client.diary_thinking = "low"
    assert _diary_generation_params(actor.executor) == {"thinking": "low"}


def test_ollama_level_reaches_exact_wire(tmp_path):
    sent = []
    def handler(req):
        sent.append(json.loads(req.content))
        return httpx.Response(200, json=response('hello'))
    c = client(tmp_path, handler)
    async def run():
        return [part async for part in c.stream_structured_chat(
            'gpt-oss:20b', [{'role':'user','content':'Write a diary'}],
            schema_name='diary', thinking='low', num_ctx=32768, num_predict=4096,
            _sq_meta={'call_id':'diary-low'})]
    asyncio.run(run())
    assert sent[0]['think'] == 'low'
    assert sent[0]['options']['num_predict'] == 4096
    assert _ollama_think({'thinking': True}) is True
