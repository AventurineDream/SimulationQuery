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

## ⚠️ Environment gotcha (read before running anything)

This machine's system `python3` (3.12) has **no pip**, and `venv` cannot bootstrap
it (`ensurepip` missing). A working venv already exists at `.venv/` (created via
`python3 -m venv --without-pip` + a bootstrapped `get-pip.py`). **Use it:**

```bash
.venv/bin/improv ...          # the CLI
.venv/bin/python -m pytest -q # tests
```

If `.venv/` is ever missing, recreate it:

```bash
python3 -m venv --without-pip .venv
python3 -c "import urllib.request; urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py','/tmp/get-pip.py')"
.venv/bin/python /tmp/get-pip.py
.venv/bin/python -m pip install -e ".[dev]"
```

On the user's **real** machines the normal path works after `apt install python3.12-venv`.

`.venv/` and generated output (`transcripts/`, `*.script.md`) are gitignored.

## Common commands

```bash
.venv/bin/python -m pytest -q                                  # 8 tests, all passing
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

## Design decisions to respect

- **Planner is decoupled.** The app's job is import → validate → perform → export.
  Do not couple the engine to any particular planner. Two producers, one consumer.
- **The engine is UI-agnostic** (yields events only). The future TUI must consume
  those events, not reach into the orchestrator. This keeps a web UI possible later.
- **Per-turn calls are stateless.** A different model may play each character, so we
  do not keep a chat history per model — we rebuild context (the script so far) each
  turn. Keep it that way unless you deliberately redesign around single-model casts.
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
