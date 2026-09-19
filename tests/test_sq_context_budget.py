from improv_troupe.research.context_budget import bounded_daily_context, diary_excerpt


def test_bounded_director_context_retains_originals_and_order():
    canon = tuple(f"fact {n}: " + "x" * 170 for n in range(100))
    transcript = tuple(f"turn {n}: " + "y" * 300 for n in range(100))
    diaries = ("α" * 4000, "a short diary", "third diary " * 500)
    kept, receipt = bounded_daily_context(canon, transcript, diaries)
    assert receipt["original"]["scene_transcript"] == transcript
    assert receipt["original"]["closed_diaries"] == diaries
    assert kept["accepted_canon"] == canon[-len(kept["accepted_canon"]):]
    assert kept["scene_transcript"] == transcript[-len(kept["scene_transcript"]):]
    assert sum(len(s.encode()) + 2 for s in kept["accepted_canon"]) <= 3000
    assert sum(len(s.encode()) + 2 for s in kept["scene_transcript"]) <= 6000
    assert all(len(s.encode()) <= 2000 for s in kept["closed_diaries"])
    assert kept["closed_diaries"][1] == diaries[1]
    assert receipt["changed"]
    assert bounded_daily_context(canon, transcript, diaries) == (kept, receipt)


def test_small_context_and_unicode_are_preserved():
    kept, receipt = bounded_daily_context(("fact",), ("turn",), ("diary",))
    assert not receipt["changed"]
    assert kept == receipt["original"]
    text = "🌿" * 1000
    excerpt = diary_excerpt(text)
    assert "�" not in excerpt and len(excerpt.encode()) <= 2000


def test_round_bounded_scene_can_outlast_thirty_minutes(tmp_path):
    import asyncio
    from datetime import timedelta
    from improv_troupe.llm.fake import ScriptedFakeClient
    from tests.test_scene_runner import _runner, _tagged_actor, _tagged_orchestrator
    db, runner, clock = _runner(tmp_path,
        actor_clients=[ScriptedFakeClient([_tagged_actor(f"I wait {n}.") for n in range(4)]) for _ in range(4)],
        orchestrator_responses=[_tagged_orchestrator(n) for n in range(1, 5)])
    runner.enforce_wall_time_limit = False
    observed = []
    def completed_round(scene, n):
        observed.append(n)
        clock.advance(timedelta(minutes=31))
    runner.round_observer = completed_round
    result = asyncio.run(runner.execute())
    assert observed == [1, 2, 3, 4]
    assert db.connection.execute("SELECT completion_reason FROM runs").fetchone()[0] == "turn_limit"
