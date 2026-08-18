# AI Improv Troupe

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

## Install

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
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

## How casting binds to your machines

A plan references backends by **handle** (or by casting *hints*), never by raw URL,
so plans stay portable. Your `backends.yaml` maps handles to the LM Studio / Ollama
endpoints on your two machines. Binding supports **both** styles:

1. **Concrete** — a cast member sets `casting.backend` + `casting.model`.
2. **Portable** — it gives `model_hint` / `size_class`, and the app resolves it
   against the models your backends advertise at import time.

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
```

## Status / roadmap

- [x] **M1** OpenAI-compatible client + model discovery
- [x] **M2** Performance engine: plan → improvised scene → `script.md` (round-robin)
- [ ] **M3** Local conversational planner (optional; external Claude skill works today)
- [ ] **M4** Textual TUI (watch screen + plan import)
- [ ] **M5** Templates, director-model turn-taking, cross-machine tuning
