# CLAUDE.md — orientation for the next agent

This file is for whoever picks up this project next. Read it first, then `README.md`.

## What this is

An app that lets a user **cast small local models as actors**, hand them a scene,
and have them **improvise it automatically**, producing a clean `script.md`. It is
explicitly **setup-and-watch**: no human-in-the-loop once a scene starts.

The architecture is **two phases joined by one contract**:

```
Planning (decoupled, external-first)      Performance (this app, automated)
────────────────────────────────────      ─────────────────────────────────
A planner emits a ProductionPlan JSON      `improv run` imports + validates the
 • a Claude desktop skill (today)   ──▶     plan, small models improvise turn by
 • a local agent (future, M3)               turn, exports script.md
 • a hand-written file
```

**The `ProductionPlan` JSON is the whole contract.** Anything that emits a valid
plan can drive the troupe. Defined in `src/improv_troupe/domain/plan.py`; the
exported JSON Schema lives at `schema/production_plan.schema.json` (regenerate with
`improv schema -o schema/production_plan.schema.json`).

## ⚠️ Environment setup (read before running anything)

The project requires Python 3.11+. On macOS, prefer the Homebrew interpreter
and use the reproducible setup script:

```bash
brew install python@3.14
bash scripts/setup_macos.sh
```

Once `.venv/` exists, use it:

```bash
.venv/bin/improv ...          # the CLI
.venv/bin/python -m pytest -q # tests
```

If `.venv/` is stale or was copied from another machine, move it aside and run
`bash scripts/setup_macos.sh` again. Do not copy virtual environments between
machines.

`.venv/` and generated output (`transcripts/`, `*.script.md`) are gitignored.

The Linux runtime is a separate installation. Its deployed checkout is
`/opt/improv-troupe`, its virtual environment is
`/opt/improv-troupe/.venv`, and its real service data is
`/var/lib/improv-troupe`. The current private target is `aven@10.0.0.103`.
The guest does not have `rsync`; use [DEPLOYMENT_HANDOFF.md](DEPLOYMENT_HANDOFF.md)
for the `tar` over SSH transfer and dashboard restart procedure. Never copy the
macOS `.venv` to Linux or point the real dashboard at a temporary data root.

The authenticated dashboard has an **End-of-day review** for one original
season day: opening snapshot, accepted shared script, run state, and every diary
attempt. It polls operational status every 60 seconds without reloading reading
panes. A wellness-held diary can be explicitly read by the owner while remaining
private, noncanon, and nonpublishable.

However, the S01 Day 2 review found that the dashboard's script projector orders
rows lexically and can place actor responses before the orchestrator beat that
prompted them. It also hides turn count and completion reason already returned
by the API. Do not use the current rendered script as production-trustworthy
chronology until Gate 12 repairs it.

The creator has decided to end S01 privately after Day 2 and overhaul the
operator workflow. Do not restart the worker to continue S01. Do not infer live
state from this checkout, run a dry worker against `/var/lib/improv-troupe`,
publish, delete artifacts, repair another diary, or issue a season command
without first reading [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) and
inspecting the authoritative Linux records. The private review and model
assessment are in
[benchmarks/s01-day-2-model-review-2026-08-24.md](benchmarks/s01-day-2-model-review-2026-08-24.md).

The active implementation sequence is: truthful dashboard and diagnostics,
manual pre-season rehearsal in a separate data root, then one isolated day with
live models. Final templates, round structure, 12B candidates, and model swaps
remain creator decisions after that evidence.

## Common commands

```bash
.venv/bin/python -m pytest -q                                  # full local suite
.venv/bin/improv run examples/the_last_train.plan.json --dry-run   # full pipeline, no servers
.venv/bin/improv validate examples/the_last_train.plan.json
.venv/bin/improv schema -o schema/production_plan.schema.json
.venv/bin/improv backends examples/backends.yaml              # discover models per endpoint
.venv/bin/improv run <plan> --config examples/backends.yaml -o out.script.md
```

`--dry-run` swaps in a deterministic **FakeClient** (`src/improv_troupe/llm/fake.py`)
so the entire prompting → streaming → parsing → export path runs offline. Use it to
test engine changes without any models.

## Code map

| Area | File | Notes |
|------|------|-------|
| Schema (the contract) | `domain/plan.py` | pydantic v2; change carefully, everything depends on it |
| Backends registry | `config.py` | maps handles → LM Studio/Ollama `/v1` endpoints |
| LLM client | `llm/client.py` | async OpenAI-compatible; engine depends only on the `ChatClient` protocol |
| Fake backend | `llm/fake.py` | powers `--dry-run` and tests |
| Casting | `casting.py` | "support both": concrete `backend`+`model`, else `model_hint`/`size_class` |
| Prompts | `engine/prompts.py` | stateless per-turn; each actor sees the full script as context |
| Output cleanup | `engine/parsing.py` | strips self-labels, other-speaker overruns, wrapping quotes |
| Orchestrator | `engine/orchestrator.py` | UI-agnostic, emits events; `round_robin` + `random` |
| Events | `engine/events.py` | `TurnStarted / TokenEmitted / TurnCompleted / SceneEnded` |
| Export | `engine/export.py` | renders `script.md` |
| CLI | `cli.py` | `validate | schema | backends | run` |
| Claude skill | `skills/scene-architect/SKILL.md` | desktop skill that emits a ProductionPlan |
| Long-form live runner | `application/scene_runner.py` | checkpointed four-actor scenes, durable mission clock, GM/actor contexts |
| Long-form context loader | `application/live_runtime.py` | schedule, prior canon/outcome, actor-local memory, hidden day direction |
| Day closure/direction | `application/season_days.py`, `application/daily.py` | closed-day transcript/canon review and private next-day plan |
| Private dashboard | `web/dashboard.py` | owner-only operations, stable diary and end-of-day reading |

## Design decisions to respect

- **Planner is decoupled.** The app's job is import → validate → perform → export.
  Do not couple the engine to any particular planner. Two producers, one consumer.
- **The engine is UI-agnostic** (yields events only). The future TUI must consume
  those events, not reach into the orchestrator. This keeps a web UI possible later.
- **Per-turn calls are stateless.** A different model may play each character, so we
  do not keep a chat history per model — we rebuild context (the script so far) each
  turn. The long-form runtime now also rebuilds prior accepted canon and only that
  actor's memory from durable events; this is not a shared model chat history.
- **Fictional time follows the immutable schedule.** Slots 1/2/3 are morning,
  afternoon, and evening. A sleep interval separates one day's evening from the
  next morning even when delayed work executes at another wall-clock time.
- **Hidden direction stays orchestrator-only.** Actors may receive revealed canon
  and a shared prior outcome, but never the private next-day direction or peer
  memory.
- **Preserve approved character cards.** A generated role sheet extends the
  creator-reviewed identity; it must not replace a profession, pronoun, public
  brief, voice anchor, or habit that disappeared between draft and green in S01.
- **Review order is causal order.** Projectors must show the orchestrator beat
  before the actor responses it prompted and must expose completion reason and
  accepted turn count.
- **Prefer native schemas.** The capability protocol alone is not evidence that
  live structured output is enforced. Capable backends use provider-native JSON
  Schema and record any tagged fallback explicitly.
- **Plans stay portable.** They reference backends by *handle* or *hint*, never raw
  URLs. Network topology lives only in `backends.yaml`.

## Status & roadmap

- [x] **M1** OpenAI-compatible client + model discovery
- [x] **M2** Performance engine: plan → improvised scene → `script.md` (round-robin/random)
- [ ] **M3** Local conversational planner *(optional — the external Claude skill works today)*
- [ ] **M4** Textual TUI: a watch screen + plan import. `textual` is already an
      optional dep (`pip install -e ".[tui]"`). Reuse the existing event stream.
- [ ] **M5** Templates, director-model turn-taking (there's a `director` seam to add
      as a new `turn_strategy`), cross-machine distribution tuning.

## Open items / things not yet decided

- **Recommended actor models are chosen and wired into `examples/backends.yaml`,
  but untested on real hardware.** Mac mini (16GB, workhorse): `qwen3:4b`,
  `qwen2.5:3b`, `gemma2:2b`, `llama3.2:3b`. Laptop (8GB, CPU-only): `llama3.2:1b`,
  `qwen2.5:1.5b`. See `examples/safehouse.plan.json` for a 6-actor cast split across
  both machines. Turns are sequential, so 6 characters can reuse ~5 model loads.
  First real-hardware run is still pending.
- **Not yet run against live LM Studio/Ollama** — only `--dry-run` has been exercised
  here. Fill in real hostnames in `examples/backends.yaml` and verify streaming +
  casting-hint resolution against actual `/v1/models` output.
- Infra: **two machines, each running LM Studio (:1234) and Ollama (:11434)**. Roughly
  one handles ~4B, the other ~9B class.

## Conventions

- Python ≥ 3.11, `src/` layout, pydantic v2, `rich` for CLI output, `httpx` for async
  HTTP. Type hints throughout; keep the docstring-per-module style already in place.
- Add tests under `tests/`; the engine is fully testable offline via `FakeClient`.
- Git identity is set globally to `aventurineseaton`. Local-only repo (no remote by
  the user's choice). Commit messages end with the `Co-Authored-By` trailer.
