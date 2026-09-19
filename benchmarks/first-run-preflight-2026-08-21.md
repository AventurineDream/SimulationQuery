# First-run preflight — 2026-08-21

> Private operational record. This is not a `green` approval.

## Current status

`PREFLIGHT_PASSED_NOT_GREEN`

## Passed checks

- Approved opening validates as the season `OpeningSnapshot`.
- Four approved cast IDs align with the draft model manifest.
- The local backend configuration maps `local` to Ollama at `http://10.0.0.103:11434/v1`.
- Ollama's OpenAI-compatible `/v1/models` endpoint lists all four selected models:
  - `gpt-oss:20b`
  - `ministral-3:8b`
  - `qwen3:8b`
  - `richardyoung/qwen3-8b-abliterated:Q4_K_M`
- A real `gpt-oss:20b` call generated the opening proposal successfully.
- `scripts/stage_first_run.py` created a temporary S01 DRAFT, persisted the opening, recorded `PREFLIGHT_PASSED_NOT_GREEN`, and safely replayed on a second run without greenlighting.

The creator subsequently ran the same staging command on the Linux guest and received `"status": "PREFLIGHT_PASSED_NOT_GREEN"`. This confirms the real S01 service database and live model endpoint passed the staging checks.

## Remaining infrastructure gate

- `http://10.0.0.103:8765/` is unreachable.
- `http://127.0.0.1:8765/` is also not running.
- The real S01 service database is on the Linux guest; local checkout state is not the operational source of truth.

## Next operational action

Start the dashboard on the private interface for Mac review. Only after that review should the creator send the explicit `green` command; private role sheets and orientation then become eligible for generation.

## Current deployment handoff — 2026-08-22

The Linux runtime target is `aven@10.0.0.103`; its checkout is
`/opt/improv-troupe` and its operational data root is `/var/lib/improv-troupe`.
The guest does not have `rsync`. Use the [deployment handoff](../DEPLOYMENT_HANDOFF.md)
to transfer the current checkout with `tar` over SSH, reinstall the editable
package, and restart the dashboard before reviewing this preflight state.

## Live dashboard review checkpoint — 2026-08-22

The creator confirmed that the updated private dashboard is reachable and
owner-authenticated. The dashboard reports Run 3 interrupted, with the exact
persisted cause and recovery status still to be inspected. All four visible
diary entries are private. No retry, skip, end, or publication decision is
recorded; inspect the Attention/notification details before taking the next
action.
