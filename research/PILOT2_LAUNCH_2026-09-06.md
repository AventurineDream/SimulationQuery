# Seven-day Pilot 2 — launch record

Authorized September 6, 2026: one seven-day season, first two runs immediately in sequence, remaining runs at standard Pacific times. The immediate instruction superseded the earlier run-1 09:12 request.

## Verified deployment

- Server: `aven@10.0.0.103`. The server accepts the existing `id_ed25519` key; macOS `/usr/bin/ssh -o UseKeychain=yes -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519` successfully authenticates. Ordinary BatchMode SSH did not unlock the key.
- Isolated frozen checkout: `/home/aven/sq-pilot2-20260906/checkout`.
- Private experiment root: `/home/aven/sq-pilot2-20260906/data`.
- Season: `SQ-PILOT2-20260906`, world `world-01`.
- Python dependencies: existing `/opt/improv-troupe/.venv/bin/python`, with `PYTHONPATH` pointing to the isolated checkout. Dependency versions are recorded in the frozen experiment. No old source, database or service was modified.
- Host cron is active. A preserved user-crontab installation runs `/home/aven/sq-pilot2-20260906/run.sh` each minute. The dispatcher serializes work with a process lock, ignores not-yet-due slots, and stops on incomplete attempts. Cron operates independently of SSH sessions. User lingering could not be enabled and is not relied on.
- Scheduler evidence: `crontab.before.txt`, `crontab.installed.txt`, `launch.pid`, `scheduler.log` in the isolated deployment root. Initial dispatcher PID: 1382389.

## Verification at launch

Installed model identity/context preflight passed for GPT-OSS 20B actors and Qwen3 30B Instruct director. The complete local suite passed: 290 tests, including all 21 scheduled scenes with synthetic responses and no early third scene. Server pytest was unavailable; this is not a claim that the server test suite ran. Server preparation, imports and live metadata preflight succeeded.

Read-only server SQLite verification after dispatch showed:

- Run 1 RUNNING; director-plan round 1 call STREAMING; one actual provider request persisted.
- Run 2 QUEUED and immediately due. It follows run 1 without overlapping model requests, subject to the frozen stop-on-fault rule.
- Both first-run queue overrides were recorded at `2026-09-06T23:03:14.946727+00:00` (16:03:14 Pacific). These are due times, not claims of generation completion or backdated starts.
- Runs 3–21 retain their standard schedule: today at 18:00, then 06:00/12:00/18:00 daily through September 12 at 18:00 Pacific.
- A concurrent scheduler invocation reported BUSY, verifying exclusion while the immediate dispatcher was running.

Neither completed run nor research result is claimed by this launch snapshot. Consult the live database and `STOPPED.json` before attempting recovery. The frozen policy prohibits automatic replay of a partial attempt. Do not edit the frozen checkout during collection.

## Study scope

See [seven-day amendment](PILOT2_SEVEN_DAY_AMENDMENT.md). This is one exploratory world, preserving checkpoints 1/8/16 plus exploratory final checkpoint 84. Probe branches are deferred until the parent finishes. The two-day three-world design remains available as a separate protocol, not as the sample collected here.
