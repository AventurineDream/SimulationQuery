# First-run green-stage handoff — 2026-08-21

> Private operational record. The real Linux service database remains untouched
> until the handoff command is run on the guest.

## Approval

The creator sent the exact approval word `green` after reviewing the private
dashboard. This authorizes private role-sheet generation and actor orientation.
It does not authorize publication, and the scene remains stopped until the
private result is reviewed.

## Bridge

Run `scripts/green_first_run.py` on the Linux guest with the staged S01
database, approved opening, selected model manifest, and `/var/lib/improv-troupe`
data root. The bridge:

- rechecks the staged opening, manifest, and SQLite integrity;
- creates the private plan and one role sheet per approved cast member;
- records immutable role-sheet versions under the private root;
- applies `GreenSeason` and creates exactly 21 scheduled queue items;
- runs orientation through each selected actor binding;
- pauses on a genuine orientation refusal or malformed response;
- never drains the queue or executes a scene.

## Disposable integration evidence

- Live Ollama inventory exposed all four selected model IDs.
- The role-sheet repair path handled count placeholders, relationship maps, and
  malformed JSON without accepting invalid content.
- A complete disposable green-stage run persisted the private plan, role sheets,
  21-run schedule, and orientation audit records; its first high-variance
  orientation pass correctly paused on inconsistent actor envelopes.
- After the prompt/parser correction, all four selected actor bindings returned
  clean `ACCEPTED=true` / empty-signal envelopes in deterministic, non-persisted
  probes at `temperature=0`.

## Current gate

`REAL_LINUX_GREEN_PENDING_HANDOFF`

The real dashboard should be refreshed after the command. Expected safe state
after successful orientation is `ARMED` with 21 queued runs and no scene output
yet. Do not start or drain the service until the private role sheets and
orientation summary have been reviewed.

For the current Linux target (`aven@10.0.0.103`), use the
[deployment handoff](../DEPLOYMENT_HANDOFF.md) to transfer and reinstall the
updated checkout before refreshing the dashboard. The guest does not have
`rsync`; the handoff uses `tar` over SSH and preserves the separate
`/var/lib/improv-troupe` service data root.
