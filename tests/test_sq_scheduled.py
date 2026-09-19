import asyncio
import json
from datetime import datetime, timezone
from datetime import date

from improv_troupe.clock import VirtualClock
from improv_troupe.research.scheduled import authorize_scheduled_resume, prepare_scheduled, tick
from improv_troupe.research.pilot import preflight
from tests.test_sq_research import REPO, SyntheticTransport


def test_seven_day_schedule_immediate_pair_and_no_early_third(tmp_path):
    root = tmp_path / 'pilot'
    config = REPO / 'rehearsals/sq-pilot2-selected-config.yaml'
    spec = prepare_scheduled(root, repo=REPO, config_path=config,
                             manifest_path=REPO / 'rehearsals/sq-pilot2-research-manifest.json',
                             requested_at=datetime(2026, 9, 6, 22, tzinfo=timezone.utc))
    schedule = json.loads((root / 'schedule.json').read_text())
    assert len(schedule) == 21 and len(spec['worlds']) == 1
    assert schedule[-1]['scheduled_local'].startswith('2026-09-12T18:00:00')
    assert schedule[0]['available_at'] == schedule[1]['available_at'] == spec['schedule']['immediate_at_utc']
    assert schedule[2]['scheduled_local'].startswith('2026-09-06T18:00:00')
    # Override only the test clock: production uses actual request-time clock.
    clock = VirtualClock(datetime.fromisoformat(spec['schedule']['immediate_at_utc']))
    assert clock.now() < datetime(2026, 9, 7, 1, tzinfo=timezone.utc)
    async def run():
        await preflight(root, repo=REPO, config_path=config, client_type=SyntheticTransport)
        result = await tick(root, repo=REPO, config_path=config, client_type=SyntheticTransport, clock=clock)
        assert result['status'] == 'SCHEDULED', result
        assert len(result['runs']) == 2 and result['next_run'].endswith('03')
        count = len(list(root.glob('**/provider/*/request.json')))
        second = await tick(root, repo=REPO, config_path=config, client_type=SyntheticTransport, clock=clock)
        assert second['runs'] == []
        assert len(list(root.glob('**/provider/*/request.json'))) == count
        # Exercise every later scheduled scene without real waiting.
        for item in schedule[2:]:
            clock.set(datetime.fromisoformat(item['scheduled_local']))
            result = await tick(root, repo=REPO, config_path=config, client_type=SyntheticTransport, clock=clock)
            assert result['status'] in {'SCHEDULED', 'COMPLETED'}, result
        assert result['status'] == 'COMPLETED'
        assert len(list((root / 'worlds/world-01/checkpoints').glob('*.json'))) == 4
    asyncio.run(run())


def test_interrupted_scheduled_attempt_never_restarts(tmp_path):
    root = tmp_path / 'pilot'
    config = REPO / 'rehearsals/sq-pilot2-selected-config.yaml'
    prepare_scheduled(root, repo=REPO, config_path=config,
                      manifest_path=REPO / 'rehearsals/sq-pilot2-research-manifest.json',
                             requested_at=datetime(2026, 9, 6, 22, tzinfo=timezone.utc))
    async def run():
        await preflight(root, repo=REPO, config_path=config, client_type=SyntheticTransport)
        (root / 'attempts').mkdir()
        (root / 'attempts/unfinished.json').write_text('{}')
        result = await tick(root, repo=REPO, config_path=config, client_type=SyntheticTransport)
        assert result['status'] == 'STOPPED'
        assert not list(root.glob('**/provider/*/request.json'))
    asyncio.run(run())


def test_explicit_scheduled_resume_reopens_only_the_stopped_run(tmp_path):
    root = tmp_path / 'pilot'
    config = REPO / 'rehearsals/sq-pilot2-selected-config.yaml'
    prepare_scheduled(root, repo=REPO, config_path=config,
                      manifest_path=REPO / 'rehearsals/sq-pilot2-research-manifest.json',
                      requested_at=datetime(2026, 9, 6, 22, tzinfo=timezone.utc))

    class Failing(SyntheticTransport):
        fail_actor = True

    async def run():
        await preflight(root, repo=REPO, config_path=config, client_type=Failing)
        stopped = await tick(root, repo=REPO, config_path=config, client_type=Failing,
                             clock=VirtualClock(datetime(2026, 9, 6, 22, tzinfo=timezone.utc)))
        assert stopped['status'] == 'STOPPED'
        run_id = 'SQ-PILOT2-RETRY-20260906-run-01'
        authorized = authorize_scheduled_resume(
            root, repo=REPO, config_path=config, run_id=run_id,
            reason='verified correction-scope repair',
            authorized_at=datetime(2026, 9, 6, 22, tzinfo=timezone.utc),
        )
        assert authorized['status'] == 'AUTHORIZED'
        resumed = await tick(
            root, repo=REPO, config_path=config, client_type=SyntheticTransport,
            # Keep this at the intended resume boundary. Using wall-clock time
            # eventually makes every historical schedule item overdue and
            # turns this bounded resume test into a full schedule drain.
            clock=VirtualClock(datetime(2026, 9, 6, 22, tzinfo=timezone.utc)),
        )
        assert resumed['runs'][0] == run_id
        assert resumed['runs'].count(run_id) == 1
        assert json.loads((root / 'resume-consumed.json').read_text())['run_id'] == run_id
        assert (root / 'STOPPED.before-resume.json').exists()
        assert not (root / 'STOPPED.json').exists()
        assert resumed['status'] == 'SCHEDULED'
    asyncio.run(run())


def test_six_day_schedule_is_sunday_through_friday_with_18_runs(tmp_path):
    root = tmp_path / 'six-day-pilot'
    config = REPO / 'rehearsals/sq-pilot2-selected-config.yaml'
    spec = prepare_scheduled(
        root, repo=REPO, config_path=config,
        manifest_path=REPO / 'rehearsals/sq-pilot2-research-manifest.json',
        requested_at=datetime(2026, 9, 10, 22, tzinfo=timezone.utc),
        season_id='SQ-PILOT2-SIX-DAY-20260913',
        start_date=date(2026, 9, 13),
        days=6,
        sessions_per_day=3,
        immediate_run_numbers=(),
    )
    schedule = json.loads((root / 'schedule.json').read_text())
    assert len(schedule) == 18
    assert spec['schedule']['calendar'] == 'sun-friday'
    assert spec['checkpoints'] == [1, 8, 16, 72]
    assert schedule[0]['scheduled_local'].startswith('2026-09-13T06:00:00')
    assert schedule[-1]['scheduled_local'].startswith('2026-09-18T18:00:00')
    assert schedule[0]['available_at'] == '2026-09-13T13:00:00+00:00'
    assert schedule[-1]['available_at'] == '2026-09-19T01:00:00+00:00'
