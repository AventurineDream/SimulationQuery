# DASH-07 — Isolated one-day acceptance and operator runbook

**Status:** deterministic rehearsal implemented and locally verified on
2026-08-27; creator review and any live-model day remain separate gates.

**Scope:** a new or empty nonproduction data root only. The rehearsal refuses
`/var/lib/improv-troupe`, any child of it, any parent containing it, and a
non-empty root. It does not contact a model endpoint, inspect S01, close a
season, publish, deploy, or restart a worker.

## What this rehearses

The script runs the normal durable paths for one synthetic season:

1. Day 1 morning — run 01;
2. Day 1 afternoon — run 02 after the clock advances;
3. Day 1 evening — run 03 after the clock advances;
4. four private diary opportunities;
5. day closure; and
6. a private next-day direction.

It produces `state/one-day-rehearsal-report.json` in that isolated root. The
report contains run outcomes, diary counts, event receipt IDs/types, safe
provenance, archive hashes, unresolved work, and creator judgment prompts. It
contains no raw prompts, wellness text, private artifact paths, real model
identities, or public projection.

## Controlled rehearsal command

```text
./.venv/bin/python scripts/run_one_day_rehearsal.py --data-root /private/tmp/a-new-empty-one-day-root
```

Use a freshly created dedicated child directory; do not reuse a prior root.
Expected result: three completed 16-turn runs, four written diaries, a closed
day, one next-day direction, no unresolved work, no public output, and a report
whose provenance says no model endpoint was contacted.

## Operator review questions

- Do morning, afternoon, and evening read as materially changed states?
- Can every blocked, failed, or deferred item be explained from the dashboard
  and the recorded receipts, without SQLite or a terminal?
- Are the four actors distinguishable in behavior, relationship, and voice?
- Is the retained four-round/16-actor-turn structure helping or causing the
  committee-like repetition observed in S01?
- Does this evidence justify a separately authorized real local-model day?

The script validates durable plumbing and timing. It is not evidence of model
quality, browser accessibility, creator understanding, or live-operation
readiness. Those are intentionally separate judgments.
