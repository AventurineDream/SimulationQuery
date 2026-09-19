#!/usr/bin/env python3
"""Live engineering gate on a private clone; never resumes the research parent."""
import argparse
import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from improv_troupe.application.actor_audition_rehearsal import _audition_scene_factory
from improv_troupe.application.season_days import SeasonDayCoordinator
from improv_troupe.clock import VirtualClock
from improv_troupe.config import AppConfig
from improv_troupe.infrastructure import DataRoots, SQLiteDatabase
from improv_troupe.llm.audit import AuditWriter
from improv_troupe.research.pilot import parent_hashes
from improv_troupe.research.transport import ResearchOllamaClient, dumps


async def validate(source, destination, config_path):
    if destination.exists():
        raise ValueError('validation destination must be new')
    before = parent_hashes(source)
    shutil.copytree(source, destination)
    audit = AuditWriter(destination)
    audit.write_text('validation-origin.json', dumps({'source':str(source), 'sha256':before,
                                                    'purpose':'engineering only; not independent research data'}))
    roots = DataRoots.from_root(destination)
    db = SQLiteDatabase(roots.state/'improv.sqlite3')
    # Relocate absolute artifact pointers in this private clone only. Original
    # accepted text is never edited. Copied hashes still identify original bytes.
    with db.transaction() as connection:
        tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for table in tables:
            for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall():
                column = row[1]
                if row[2].upper() == 'TEXT':
                    connection.execute(f'UPDATE "{table}" SET "{column}"=replace("{column}",?,?) WHERE instr("{column}",?)>0',
                                       (str(source), str(destination), str(source)))
    config = AppConfig.load(config_path)
    row = db.connection.execute('SELECT r.run_id,r.season_id,r.actual_completed_at FROM runs r JOIN schedule_slots s ON r.slot_id=s.slot_id WHERE s.run_number=3').fetchone()
    if row is None or row['actual_completed_at'] is None:
        raise ValueError('source must have completed scene 3')
    clock = VirtualClock(datetime.fromisoformat(row['actual_completed_at']))
    client = ResearchOllamaClient(config.backend('local'), roots.private/'validation-provider',
                                  world_id=destination.name, seed=271828, phase='engineering-day-end')
    client.bounded_daily_context = True
    client.diary_thinking = 'low'
    audit.write_text('validation-identity.json', dumps(await client.identity(['gpt-oss:20b','qwen3:30b-instruct'])))
    factory = _audition_scene_factory(db, roots, config, clock, lambda _:client)
    factory.sessions_per_day = 3
    coordinator = SeasonDayCoordinator(database=db, clock=clock, scene_factory=factory,
        strict_rehearsal_acceptance=True, strict_diary_word_count=True, sessions_per_day=3, final_day_number=7)
    baseline_calls = {r[0] for r in db.connection.execute('SELECT call_id FROM model_calls')}
    result = {'status':'FAILED'}
    try:
        payload = {'run_id':row['run_id'], 'season_id':row['season_id'], 'day_number':1, 'slot_number':3}
        scene = factory(payload)
        scene._hydrate()
        await coordinator.after_scene(payload, scene, SimpleNamespace(transcript=scene.transcript))
        if client.failed:
            raise RuntimeError('transport failed')
        diaries = [dict(r) for r in db.connection.execute('SELECT character_id,status,word_count FROM diaries WHERE day_number=1')]
        if len(diaries) != 3 or any(r['status'] != 'WRITTEN' or not 300 <= r['word_count'] <= 800 for r in diaries):
            raise RuntimeError('all three diaries must pass acceptance')
        day = db.connection.execute('SELECT closed FROM days WHERE day_number=1').fetchone()
        if not day or not day[0]:
            raise RuntimeError('day did not close')
        events = db.connection.execute("SELECT payload_json FROM domain_events WHERE event_type='NextDayDirectionCreated'").fetchall()
        if len(events) != 1:
            raise RuntimeError('expected exactly one persisted next-day direction')
        next_run = db.connection.execute('SELECT r.run_id FROM runs r JOIN schedule_slots s ON r.slot_id=s.slot_id WHERE s.run_number=4').fetchone()[0]
        morning = factory({'run_id':next_run,'season_id':row['season_id']})
        if not morning.private_day_direction:
            raise RuntimeError('next morning did not load direction')
        result = {'status':'PASSED','diaries':diaries,'day_closed':True,'direction_persisted':True,
                  'next_morning_loads_direction':True}
    except Exception as exc:
        result.update(error=type(exc).__name__, detail=str(exc))
    finally:
        result['new_calls'] = [dict(r) for r in db.connection.execute('SELECT call_id,purpose,status,acceptance_status,validator_code FROM model_calls') if r['call_id'] not in baseline_calls]
        db.connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        db.connection.close()
        result['parent_unchanged'] = parent_hashes(source) == before
        if not result['parent_unchanged']:
            result['status'] = 'FAILED'
        audit.write_text('validation-result.json', dumps(result))
    print(dumps(result), flush=True)
    return result['status'] == 'PASSED'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if asyncio.run(validate(args.source, args.destination, args.config)) else 2)
