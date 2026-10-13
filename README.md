# Simulation Query · AI Improv Troupe

Simulation Query studies acceptance-boundary continuity in multi-agent roleplay.
AI Improv Troupe is the Python runtime: a planner produces a scene contract,
local models play the cast, and the engine records accepted turns and evidence.

This is the [public project repository](https://github.com/AventurineDream/SimulationQuery).
Private manuscripts, sealed annotations, raw outputs, exact operating
configurations, and completed run archives live in the private SimulationQuery
Drive folder. The previous local SimulationQuery folder is deprecated.
See [project organization](docs/PROJECT_ORGANIZATION.md) for the storage policy.

## Start here

- [Documentation map](docs/README.md): architecture, implementation, and tools.
- [Research index](research/README.md): protocols, coding rules, and dated decisions.
- [Agent guidance](AGENTS.md): setup, validation, and evidence boundaries.
- [Codex cloud setup](docs/CODEX_CLOUD_SETUP.md): prepare an isolated environment.

## Install

Use Python 3.11 or newer on Linux or macOS. Create a virtual environment on the
machine where you will run the software:

```bash
git clone https://github.com/AventurineDream/SimulationQuery.git
cd SimulationQuery
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,tui]'
```

On macOS, `bash scripts/setup_macos.sh` remains available for Homebrew Python.
The `tui` extra is optional for normal use; installing it includes the UI in test
coverage. The package name remains `improv-troupe` and the command is `improv`.

## Try an offline scene

```bash
.venv/bin/improv validate examples/the_last_train.plan.json
.venv/bin/improv run examples/the_last_train.plan.json --dry-run
.venv/bin/improv schema -o /tmp/production_plan.schema.json
```

The dry run uses a deterministic fake client. It exercises the prompt, event,
parsing, and export pipeline without contacting a model server.

Planning and performance meet at one contract, `ProductionPlan`:

```text
External planner or handwritten plan
                |
       ProductionPlan JSON
                |
        validate and perform
                |
       accepted scene + export
```

The schema is defined in `src/improv_troupe/domain/plan.py` and exported in
[schema/production_plan.schema.json](schema/production_plan.schema.json).
The [scene architect skill](skills/scene-architect/SKILL.md) helps a planner
produce that contract. The engine is UI-independent and emits events.

For a live standalone scene, configure your own endpoints in a copy of
[examples/backends.yaml](examples/backends.yaml), then explicitly pass that
configuration:

```bash
.venv/bin/improv backends /path/to/backends.yaml
.venv/bin/improv run examples/the_last_train.plan.json \
  --config /path/to/backends.yaml -o /tmp/scene.script.md
```

Checked-in rehearsal YAML files now use portable local paths and a loopback
model endpoint. They preserve model handles and experimental settings; they are
starting points, not exact historical machine configurations. Original versions
are retained in the private Drive archive.

## Research and status

Start with [Pilot-2 protocol](research/PILOT2_PROTOCOL.md),
[coding guide](research/PILOT2_CODEBOOK.md), and the
[diary claim calibration protocol](research/DIARY_CLAIM_CALIBRATION_PROTOCOL_V01.md).
The [implementation record](IMPLEMENTATION_STATUS.md) and
[research implementation record](research/IMPLEMENTATION_STATUS.md) are dated
software history. They do not establish the current state of a private server.

The completed Porch Season 1 evidence is indexed in Drive. Its copied database
and archive show 21 completed scenes, seven closed days, and 28 written diaries.
Administrative season closure remains a separate decision. This accelerated
stabilization run does not demonstrate seven-real-day pacing or establish prose
quality or a research conclusion.

The [rehearsal index](rehearsals/README.md) and
[benchmark index](benchmarks/README.md) retain bounded historical summaries.
Failed attempts and private diaries remain evidence even when withheld from
acceptance or publication.

## Validate a change

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/check_repository.py
.venv/bin/python -m compileall -q src scripts tests
git diff --check
```

[GitHub Actions](.github/workflows/ci.yml) repeats offline validation on Python
3.11 and 3.14. The repository check verifies local documentation links, JSON/YAML
syntax, and known private-artifact boundaries.

## Long-form service

The runtime also supports persistent seasons, scheduling, day closure, private
diaries, model-call archives, and an authenticated operator dashboard. Read the
[generic deployment handoff](DEPLOYMENT_HANDOFF.md),
[architecture](ARCHITECTURE_SPEC.md), and
[dashboard documentation](docs/dashboard/README.md) before working on it.
Keep live data on a persistent, backed-up filesystem.

An ordinary repository change does not authorize deploying to the run host,
restarting a worker, replaying a completed scene, changing a frozen launch
identity, closing a season, or publishing private artifacts. Use the current
Drive operating record and a separately recorded decision for those actions.
