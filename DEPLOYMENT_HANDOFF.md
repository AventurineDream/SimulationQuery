# AI Improv Troupe — Linux deployment handoff

**Purpose:** transfer the current checkout to the Linux runtime, refresh the
installed package, and open the private dashboard from the Mac.

This is an operational handoff, not a green approval and not permission to
drain the real season. The Linux database at `/var/lib/improv-troupe` remains
the operational source of truth.

**Current S01 boundary — 2026-08-24:** the creator has decided to end S01
privately after the Day 2 review. Do not restart the scene worker to continue
queued S01 work, and do not replay a historical green, recovery, wellness-policy,
or diary-repair command. First read [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)
and inspect authoritative season, run, work, recovery, model-call, day, and diary
state. Ending does not authorize publication or deletion.

## Current target

- SSH target: `aven@10.0.0.103`
- Linux checkout: `/opt/improv-troupe`
- Linux virtual environment: `/opt/improv-troupe/.venv`
- Persistent service data: `/var/lib/improv-troupe`
- Dashboard URL from the Mac: `http://10.0.0.103:8765`
- Dashboard bind address: `10.0.0.103`

## Isolated S02 test-season target — approved 2026-08-28

S02 must not reuse S01's checkout, service, config, or data root. Its approved
isolation is:

- checkout: `/opt/improv-troupe-test`
- config: `/etc/improv-troupe-test/config.yaml`
- persistent data: `/var/lib/improv-troupe-test`
- worker: `improv-troupe-test.service`
- Sunday Day 1 start: 06:00 Pacific on 2026-08-30

The test package is `benchmarks/s02-test-approved-opening-2026-08-30.json`
and `benchmarks/s02-test-model-manifest-2026-08-30.json`. The test service
enables bounded automatic recovery only for transport timeouts: at most three
total attempts, after which the creator-controlled recovery path applies.
The one-shot Green timer is deliberately separate in
`deploy/improv-troupe-test-green.timer`; install it only after S02 preflight
passes and the operator has verified the separate root. No S01 service restart
or data-root write is part of this test-season setup.

### Verified isolated deployment — 2026-08-28

The creator supplied Linux-console evidence that S02 preflight passed in the
separate root. The checks for backend reachability, model manifest, persistent
roots, and SQLite integrity all passed; the season remained
`PREFLIGHT_PASSED_NOT_GREEN`. `improv-troupe-test.service` was active with the
test checkout, config, and data root. The one-shot Green timer was armed for
Saturday 2026-08-29 at 06:05 Pacific, preserving a Sunday 2026-08-30 Day 1
start. This is deployment evidence for S02 only; it is not evidence of an S01
restart, mutation, or public release.

The Linux host currently does not have `rsync`. Use the standard `tar` and
`ssh` tools instead. Do not copy `.venv` from the Mac; virtual environments
are platform-specific.

## Transfer the current checkout from macOS

Run these commands on the Mac from the current checkout. The archive overwrites
matching source files under `/opt/improv-troupe` but does not delete files from
the Linux checkout or touch `/var/lib/improv-troupe`.

```bash
export IMPROV_LINUX_TARGET='aven@10.0.0.103'

tar -czf - \
  --exclude='.venv' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  -C /Users/aven/Software/Github/AI-improv-troupe . \
| ssh "$IMPROV_LINUX_TARGET" 'cat > /tmp/improv-troupe-update.tar.gz'

ssh -t "$IMPROV_LINUX_TARGET" \
  'sudo mkdir -p /opt/improv-troupe && \
   sudo tar --no-same-owner -xzf /tmp/improv-troupe-update.tar.gz -C /opt/improv-troupe && \
   sudo chmod 750 /opt/improv-troupe && \
   sudo chgrp -R improv /opt/improv-troupe/src && \
   sudo chmod -R g+rX /opt/improv-troupe/src && \
   rm -f /tmp/improv-troupe-update.tar.gz'
```

This transfers the current checkout, including its current uncommitted project
work. It does not transfer the Mac virtual environment or Git metadata. The
second SSH command may prompt for the Linux `sudo` password; the temporary
archive is removed only after extraction succeeds. The final mode keeps the
checkout private while allowing the `improv` service group to traverse it; the
Mac checkout's top-level directory mode must not block the service user.

## Refresh the Linux package

Run this on the Linux guest after the transfer:

```bash
cd /opt/improv-troupe
/opt/improv-troupe/.venv/bin/python -m pip install --no-deps -e .
grep -n "End-of-day review" src/improv_troupe/web/dashboard.py
grep -n "overnight sleep period has passed" \
  src/improv_troupe/application/scene_runner.py
grep -n "mission-progress, danger, mystery, and relationship clocks" \
  src/improv_troupe/llm/context.py
sudo -u improv /opt/improv-troupe/.venv/bin/python - <<'PY'
from improv_troupe.config import AppConfig

config = AppConfig.load("/etc/improv-troupe/config.yaml")
for handle, backend in config.backends.items():
    print(f"{handle}: timeout_seconds={backend.timeout_seconds:g}")
PY
sudo -u improv /opt/improv-troupe/.venv/bin/python -c \
  'import improv_troupe; print(improv_troupe.__file__)'
```

All three `grep` commands should print matching lines, and the timeout check
should report `local: timeout_seconds=300`. If one does not, the updated
checkout or config did not reach the Linux guest. The final command should
print a path under `/opt/improv-troupe/src`; if it raises `ModuleNotFoundError`,
the editable package install did not complete or the `improv` service user
cannot read the source tree, and neither dashboard nor scene service should be
restarted yet.

## Start the real dashboard

Stop any older dashboard process first with `Ctrl-C`. On the Linux guest:

```bash
cd /opt/improv-troupe
export IMPROV_DASHBOARD_USERNAME=owner
export IMPROV_DASHBOARD_PASSWORD_HASH="$(
  /opt/improv-troupe/.venv/bin/improv dashboard-hash
)"
```

Enter the owner password twice. Then start the dashboard as the service user:

```bash
sudo -u improv env \
  IMPROV_DASHBOARD_USERNAME=owner \
  IMPROV_DASHBOARD_PASSWORD_HASH="$IMPROV_DASHBOARD_PASSWORD_HASH" \
  /opt/improv-troupe/.venv/bin/improv dashboard \
  --data-root /var/lib/improv-troupe \
  --bind 10.0.0.103 \
  --port 8765 \
  --enable-v2
```

Open `http://10.0.0.103:8765` on the Mac. Sign in with username `owner` and
the original password entered during `dashboard-hash`; never enter the
`scrypt$...` hash as the password.

The authenticated base URL now opens the v2 Home surface at `/v2/home`. The
preserved v1 dashboard is available only for an explicit rollback by adding
`--legacy` to the launch command.

## Safe checks

Before trusting the dashboard state, inspect the real database from the Linux
guest:

```bash
/opt/improv-troupe/.venv/bin/improv status \
  --data-root /var/lib/improv-troupe
```

Do not run `improv serve --dry-run` against the real season. It can advance due
work without model calls. The scheduler service and the dashboard are separate;
the scheduler normally continues independently when the Mac browser is closed.
S01 is currently an explicit exception: leave its worker stopped until the
creator-approved private end is inspected, executed, and verified.

## After the first successful sign-in

Confirm that the dashboard is reading the real season root, that the current
run and queued work are visible, and that the Attention panel reflects any
interruption. If a run is marked `RECOVERY_REQUIRED`, review its notification
before choosing `retry`, `skip`, or `end`; those are creator decisions and are
not automatic story recovery.

Diary entries showing as private is the safe default. Keep them private unless
the season is closed and you have completed the explicit end-of-season review
and publication decision. Do not treat a successful login or a visible diary
entry as evidence that the interrupted run has resumed.

## Stable end-of-day review

After this checkout is installed, the dashboard includes an **End-of-day
review** panel. Select the season and original day to read the opening snapshot,
the accepted shared script grouped by run, and every diary record together.
This is the intended creator reading surface at the end of a day.

The page polls operational status every 60 seconds, but it does **not** reload
the Diary desk or End-of-day review on that timer. An expanded entry therefore
stays open while you read it. Use the top-level **Refresh** button when you
want all displayed content reloaded, or **Reload review** when you want to
refresh only the selected day.

Wellness-held and format-invalid diary attempts remain `PRIVATE`. The signed-in
owner may explicitly expand their private review text and, if needed, their raw
model output. This does not accept, clear, publish, or overwrite the diary; the
separate end-of-season publication gate remains the only clearance path. Raw
prompts, hidden plans, role sheets, and model identities are still not exposed
by the dashboard.

To mark current unread operator notifications as read without deleting any
audit, diary, event, or notification records, run this on the Linux guest as
the service user:

```bash
sudo -u improv /opt/improv-troupe/.venv/bin/python -c '
import sqlite3
from datetime import datetime, timezone

path = "/var/lib/improv-troupe/state/improv.sqlite3"
with sqlite3.connect(path) as database:
    result = database.execute(
        "UPDATE notifications SET read_at = ? WHERE read_at IS NULL",
        (datetime.now(timezone.utc).isoformat(),),
    )
    print(f"Marked {result.rowcount} operator notifications read.")
'
```

This changes only the `read_at` marker. Refresh the dashboard afterward; its
unread notification count should be zero unless a new notification arrives.

## Historical S01 manual wellness policy and Ivy diary repair

The commands in this section record the earlier S01 recovery handoff. They are
not current instructions. Do not run them unless a fresh authoritative-state
inspection establishes that the exact operation is still required and the
creator separately approves it.

The creator's S01 decision is to keep accepting and privately recording wellness
signals, while leaving any decision to pull an actor manual. This is persisted
on the season; it does not change the automatic three-signal default for future
seasons. Apply it once after the updated package is installed:

```bash
sudo -u improv /opt/improv-troupe/.venv/bin/python \
  -m improv_troupe.cli wellness-policy S01 \
  --manual-review \
  --request-id s01-manual-wellness-2026-08-22 \
  --data-root /var/lib/improv-troupe \
  --json
```

Confirm the response contains `"auto_tap_out": false`, then confirm status
reports `wellness_policy: MANUAL_REVIEW`. Signals still create private audit
artifacts and operator notifications. A new scene signal still pauses that run
for your review; this policy removes automatic cast departure, not the manual
safety checkpoint.

If Ivy's Day 1 record is still `PRIVATE` with no accepted content, it can be
repaired as a new model attempt using a completed Day 1 scene for context. Do
not rerun this command when the dashboard already shows accepted Ivy content.
The old model call, output, and validation history remain private and are not
overwritten. If the scheduler is managed by systemd, stop it briefly so the
repair is the only writer, run the command, then start it again:

```bash
sudo systemctl stop improv-troupe

sudo -u improv /opt/improv-troupe/.venv/bin/python \
  -m improv_troupe.cli repair-diary S01 \
  --character ivy-fermion \
  --run S01-run-01 \
  --config /etc/improv-troupe/config.yaml \
  --data-root /var/lib/improv-troupe \
  --json

sudo systemctl start improv-troupe
```

The repair command is deliberately limited to a PRIVATE diary with no accepted
content and requires the season's manual-review policy first. `S01-run-01` is
the original Day 1 / slot 1 scene context; do not substitute Run 3 unless you
intend to change the diary context. Afterward, refresh the authenticated diary
desk and verify Ivy is `WRITTEN` with a private content path. Leave the other
three diary records private until the separate publication review.

## If the dashboard still shows the old JSON page

The old process or an old installed checkout is still serving port `8765`.
Stop that process, repeat the package refresh, verify the `grep` check above,
and start the dashboard again. A hard browser refresh is safe after the new
process is running.
