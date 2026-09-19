# AI Improv Troupe

Simulation Query research: [Pilot-2 protocol](research/PILOT2_PROTOCOL.md), [coding guide](research/PILOT2_CODEBOOK.md), and [implementation status](research/IMPLEMENTATION_STATUS.md).

Cast a small group of local models as actors, hand them a scene, and let them
improvise the rest. You design the show in a planning step, give the green light,
and the troupe performs it automatically — producing a clean `script.md` at the end.

## The two phases

```
Planning (decoupled)                Performance (automated)
────────────────────                ───────────────────────
Any planner produces a      ──▶     improv run reads the plan,
ProductionPlan JSON:                small models improvise turn
 • a Claude desktop skill           by turn, and it exports a
 • a local agent (later)            clean script.md.
 • a hand-written file
```

The **ProductionPlan JSON** is the contract between the two halves. Anything that
emits a valid plan can drive the troupe. See `skills/scene-architect/` for a
Claude desktop skill that runs the design conversation and outputs the JSON.

## Install on macOS

The repository is platform-neutral Python, but the supported interpreter is
Python 3.11 or newer. On Apple Silicon, Homebrew is the simplest route:

```bash
brew install python@3.14
bash scripts/setup_macos.sh
```

The script creates the local `.venv` and installs the package plus its test
dependencies. You can also run the commands manually with any Python 3.11+
interpreter:

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

## Use it

```bash
# See the whole pipeline with no servers running:
improv run examples/the_last_train.plan.json --dry-run

# Export the schema your planner should target:
improv schema -o schema/production_plan.schema.json

# Point it at your machines and check what's loaded:
improv backends examples/backends.yaml

# Perform for real:
improv run examples/the_last_train.plan.json --config examples/backends.yaml -o out.script.md
```

## Long-form season service on Linux / Proxmox

The seven-day season workflow runs on Linux. Proxmox can host it in either a
VM or an LXC container; the application does not depend on which one you use.
The important deployment boundary is a persistent filesystem for the service
data root, preferably mounted at `/var/lib/improv-troupe` and included in the
server backup plan. The Mac is intended to be the private dashboard client,
not the scheduler host.

The 21 runs are also a seven-day fiction clock: each day has a morning,
afternoon, and evening scene, with meaningful off-screen time between them and
an overnight sleep interval before the next morning. Live context carries
forward accepted canon, the prior run's final shared outcome, and each actor's
own memory. A closed day's hidden direction is supplied only to the
orchestrator. The prompts treat that orchestrator as a TTRPG game master: it
adjudicates choices, advances private progress/danger/mystery/relationship
clocks, and creates concrete diary-worthy beats without scripting actor choices
or reducing every run to a technical emergency.

In strict rehearsal mode, that direction is tested as a two-pass game loop:
the director first records a private scene objective, adjudication, state
change, pressure, two actor-facing choices, clock change, and canon update;
only then does a render pass supply fresh scene texture while the approved
decision is compiled verbatim into shared narration. Actors may take either
offered course or make another move entirely.

### Current project phase

The private S01 pilot reached Day 2 and produced encouraging diaries but exposed
serious operator, chronology, structured-output, character-input, continuity,
and repetition failures. The creator has decided to end S01 privately and use it
as evidence for an operator overhaul. Do not restart the live worker to continue
S01 from this README. Inspect authoritative Linux state before the separate
season-end action, and do not publish or delete any S01 artifact.

The active reliability line is an isolated, one-day rehearsal of the porch
season's MAGIC rules, runtime-owned dice adjudication, and private diary
fidelity gate. The latest live run completed mechanically with eight accepted
actor turns, no cheetah turns, four diary attempts, and a closed day. Diary
envelopes carry range-checked references to the accepted scene, and the
reviewer now checks those claims against numbered scene evidence. The v07 run
recorded one malformed-diary correction, two malformed-review corrections, and
one concrete evidence-reference/event-order finding. Its quality status is
`HUMAN_REVIEW_REQUIRED`: no diary was released to future direction. See the
[latest rehearsal review](rehearsals/season-1-porch-magic-diary-reviewer-evidence-v01-2026-09-17.md)
for the separate mechanical and quality results.

Start with [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for the current
handoff and [docs/README.md](docs/README.md) for the repository map. The earlier
dashboard product, design, and walkthrough records remain preserved under
[docs/dashboard/](docs/dashboard/); they are historical implementation evidence,
not authorization to deploy, restart a worker, alter S01, or publish anything.

The current service boundary can be initialized and inspected before live
models are selected:

```bash
improv migrate --config /etc/improv-troupe/config.yaml
improv status --config /etc/improv-troupe/config.yaml
improv recover --config /etc/improv-troupe/config.yaml
```

`improv serve --dry-run --once` is an infrastructure test only. It completes
due scene work without model calls and must never be used to advance a real
season. The normal `serve` command requires backend configuration plus a
private season model manifest; it is ready to construct live scene runners,
but should remain off the real season until model availability and output
quality have been checked locally.

The staged systemd unit is [deploy/improv-troupe.service](deploy/improv-troupe.service),
with a commented configuration starting point at
[deploy/config.example.yaml](deploy/config.example.yaml). Install the unit
inside the Linux VM/container, not on the Proxmox host, after live model
preflight is available. Keep the service and future dashboard on the private
network. A season’s private model assignment follows the shape in
[deploy/model-manifest.example.json](deploy/model-manifest.example.json); use
`actor_default` for shared actor weights or the `actors` map for per-character
assignments.

The current private Linux target is `aven@10.0.0.103`. The guest does not have
`rsync`; use the no-rsync [deployment handoff](DEPLOYMENT_HANDOFF.md) to stream
the current macOS checkout with `tar` over SSH. Never copy the macOS `.venv` to
Linux, and never use `/tmp` as the real season data root. Refreshing the editable
package does not hot-reload an existing scene worker. A worker restart is a
separate operational action and must follow the current status record; for the
present S01 handoff, continuing the queued season is explicitly out of scope.

The private dashboard is an authenticated operator view served from the Linux
runtime and opened in a browser on the Mac. Generate its password hash
interactively, keep the hash in the service environment rather than season
artifacts, and bind only to the private interface:

```bash
cd /opt/improv-troupe
export IMPROV_DASHBOARD_USERNAME=owner
export IMPROV_DASHBOARD_PASSWORD_HASH="$(
  /opt/improv-troupe/.venv/bin/improv dashboard-hash
)"
sudo -u improv env \
  IMPROV_DASHBOARD_USERNAME=owner \
  IMPROV_DASHBOARD_PASSWORD_HASH="$IMPROV_DASHBOARD_PASSWORD_HASH" \
  /opt/improv-troupe/.venv/bin/improv dashboard \
  --bind 10.0.0.103 \
  --data-root /var/lib/improv-troupe \
  --port 8765 \
  --enable-v2
```

Open `http://10.0.0.103:8765` from the Mac. Enter the original password used
for `dashboard-hash`, not the generated `scrypt$...` hash. Stop an older manual
dashboard process with `Ctrl-C` before restarting it after a checkout update.

Use `--secure-cookie` when the private reverse proxy provides HTTPS. The
dashboard exposes status, authenticated diary reading, an end-of-day review,
recovery actions, and the explicit publication gate. It does not expose raw
prompts, hidden plans, role sheets, or model identities.

The v2 operator dashboard is now the live surface. After sign-in, `/` redirects
to `/v2/home`; the deep links `/v2/prepare`, `/v2/live`, `/v2/review`,
`/v2/diagnostics`, and `/v2/seasons` remain available. Home, Review, Live, and
Diagnostics are authenticated reads; Prepare accepts only versioned rehearsal
actions in a sandbox environment and rejects S01. The preserved v1 renderer is
kept only as an explicit rollback with `--legacy` and is not the normal launch
path.

The preserved legacy Day-review route remains a private pilot surface. The v2
Review route repairs local chronology with additive schema-2 accepted sequence,
cause-link, and acceptance-time evidence for new turns, without backfilling or
rewriting legacy rows. Schema 3 adds nullable stored call provenance and
downstream-stage evidence for Diagnostics; legacy gaps remain labeled
unavailable. Schema 4 adds the isolated preparation workspace, immutable card
and assignment versions, receipts, and invalidation events. Green remains a
readiness receipt and does not arm the season. No local verification is
production deployment evidence.

The end-of-day review gathers one original day’s opening snapshot, accepted
shared-script turns, run states, and every diary record in one owner-only
reading surface. A wellness-held diary remains `PRIVATE` and nonpublishable,
but the v2 signed-in owner can deliberately open only safely separated diary
text plus a wellness-presence marker, without receiving raw wellness wording
or changing diary, canon, wellness, or publication state. This is a review
exception, not a public or automatic clearance path. The legacy route's broader
raw-output behavior is preserved only as rollback and is not the v2 privacy
contract.

Operational status refreshes every 60 seconds. That refresh deliberately does
not re-render the Diary desk or End-of-day review, so an entry cannot collapse
while it is being read. Use **Refresh** to load new content everywhere, or
**Reload review** after selecting a different review day.

During live review, treat an interrupted run as a recovery decision point, not
as permission to continue automatically. Inspect the dashboard's Attention
panel and notification first; use `retry`, `skip`, or `end` only after the
persisted status is confirmed. Diary entries remain private by default and
require a separate end-of-season privacy/wellness review before publication.

The service setting `recovery_wait_seconds` defaults to `14400` (four hours).
During supervised troubleshooting it may be set temporarily to `0`; failures
then become `RECOVERY_REQUIRED` on the next service poll, but still require an
explicit creator decision and never retry automatically. Restore `14400` when
the supervised recovery session ends.

Wellness signals remain private observational records. The default policy and
the S01 manual-review override are documented in
[PRODUCTION_SPEC.md](PRODUCTION_SPEC.md) and the historical operational commands
remain in [DEPLOYMENT_HANDOFF.md](DEPLOYMENT_HANDOFF.md). Do not replay an S01
policy, diary-repair, green, recovery, or season-control command merely because
it appears in a historical record; first inspect current authoritative state and
the exact next action in `IMPLEMENTATION_STATUS.md`.

## How casting binds to your machines

A plan references backends by **handle** (or by casting *hints*), never by raw URL,
so plans stay portable. Your `backends.yaml` maps handles to the LM Studio / Ollama
endpoints on your two machines. Binding supports **both** styles:

1. **Concrete** — a cast member sets `casting.backend` + `casting.model`.
2. **Portable** — it gives `model_hint` / `size_class`, and the app resolves it
   against the models your backends advertise at import time.

Each backend may set `timeout_seconds` for model discovery and streaming calls;
it defaults to 300 seconds so slower local models can finish without being
mistaken for unavailable services.

## Project layout

```
src/improv_troupe/
  domain/plan.py     # ProductionPlan schema (the contract)
  config.py          # backends.yaml registry
  llm/               # OpenAI-compatible async client + fake backend
  engine/            # prompts, parsing, orchestrator, export — UI-agnostic
  casting.py         # bind actors -> (backend, model)
  cli.py             # improv validate | schema | backends | run
skills/scene-architect/   # Claude desktop skill that emits a ProductionPlan
examples/            # sample plan + backends.yaml
benchmarks/          # private model/preflight/pilot evidence; never public export
IMPLEMENTATION_STATUS.md  # current evidence boundary and exact next action
IMPLEMENTATION_PLAN.md    # gated implementation and operator-overhaul checklist
```

## Status / roadmap

- [x] **M1** OpenAI-compatible client + model discovery
- [x] **M2** Performance engine: plan → improvised scene → `script.md` (round-robin)
- [ ] **M3** Local conversational planner (optional; external Claude skill works today)
- [ ] **M4** Textual TUI (watch screen + plan import)
- [ ] **M5** Templates, director-model turn-taking, cross-machine tuning
- [ ] **M6** Operator overhaul: truthful dashboard, manual pre-season rehearsal, one-day acceptance
