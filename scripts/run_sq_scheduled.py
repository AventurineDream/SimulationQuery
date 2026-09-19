#!/usr/bin/env python3
"""Scheduled SQ collection; collection only on an explicit tick."""
import argparse
import asyncio
import json
from datetime import date
from pathlib import Path
from improv_troupe.research.scheduled import authorize_scheduled_resume, prepare_scheduled, tick, finish_probes
from improv_troupe.research.pilot import preflight


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'preflight', 'tick', 'resume'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, default=Path('rehearsals/sq-pilot2-research-manifest.json'))
    parser.add_argument('--season-id', default='SQ-PILOT2-CONTEXT-20260907')
    parser.add_argument('--days', type=int, default=7)
    parser.add_argument('--sessions-per-day', type=int, default=3)
    parser.add_argument('--start-date', type=date.fromisoformat)
    parser.add_argument('--immediate-run-numbers', default='1,2',
                        help='comma-separated run numbers to make due at preparation time; empty for standard slots')
    parser.add_argument('--run-id', help='exact interrupted run id for an explicit scheduled resume')
    parser.add_argument('--resume-reason', default='creator-authorized continuation after verified code fix')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    kw = dict(repo=repo, config_path=args.config)
    if args.command == 'prepare':
        immediate = tuple(int(value) for value in args.immediate_run_numbers.split(',') if value.strip())
        result = prepare_scheduled(
            args.root, manifest_path=args.manifest, season_id=args.season_id,
            days=args.days, sessions_per_day=args.sessions_per_day,
            start_date=args.start_date, immediate_run_numbers=immediate, **kw,
        )
    elif args.command == 'preflight':
        result = asyncio.run(preflight(args.root, **kw))
        result = {'status': 'PREFLIGHT_PASSED', 'models': list(result['models'])}
    elif args.command == 'resume':
        if not args.run_id:
            parser.error('resume requires --run-id')
        result = authorize_scheduled_resume(
            args.root, run_id=args.run_id, reason=args.resume_reason, **kw,
        )
    else:
        result = asyncio.run(tick(args.root, **kw))
        if result['status'] == 'COMPLETED':
            result['probes'] = asyncio.run(finish_probes(args.root, **kw))
    print(json.dumps(result, indent=2))
    return 2 if result.get('status') == 'STOPPED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
