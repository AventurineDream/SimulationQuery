# Working on Simulation Query

Read `README.md`, `docs/PROJECT_ORGANIZATION.md`, and the relevant dated research
protocol before changing this project. `CLAUDE.md` points to the same guidance.

## Sources of truth

- GitHub: `https://github.com/AventurineDream/SimulationQuery` is the public
  software, methodology, examples, and implementation record.
- The private SimulationQuery Drive folder owns unpublished drafts, annotations,
  model outputs, operational records, and complete run evidence.
- The old local SimulationQuery folder is deprecated. Its files are preserved in
  Drive; do not use it as an independent current source.

Use an isolated clone or worktree. Check the remote and current default branch
before preparing a change. Preserve existing user edits. Keep cleanup changes
separate from changes to runtime behavior.

## Setup and verification

Use Python 3.11 or newer and a virtual environment created on this machine:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,tui]'
.venv/bin/python -m pytest -q
.venv/bin/python scripts/check_repository.py
.venv/bin/python -m compileall -q src scripts tests
.venv/bin/improv validate examples/the_last_train.plan.json
.venv/bin/improv run examples/the_last_train.plan.json --dry-run
git diff --check
```

The tests use synthetic responses and temporary databases. Use temporary output
paths for verification. Live model calls and service operations are separate
from offline validation.

## Evidence and operating boundaries

- Preserve completed and failed attempts, provider archives, logs, manifests,
  receipts, SQLite files, snapshots, annotations, and historical conditions.
  Private evidence belongs in Drive, not in the public working tree.
- `.rehearsal-data/` is retained private evidence, not disposable cache. Do not
  clean it with a broad delete command.
- Checked-in rehearsal YAML files are portable examples. The exact historical
  machine configurations are preserved in Drive. Keep filenames, backend
  handles, model choices, and experimental settings compatible with existing
  scripts and tests.
- A repository cleanup does not authorize restarting a worker, replaying a run,
  changing a frozen launch identity, closing a season, or publishing evidence.
  Those actions require their own recorded decision.
- Distinguish mechanical completion, human quality review, and administrative
  closure. Do not infer deployed behavior from a clean repository checkout.
- Do not change frozen protocols or rubric versions as part of organization.
  Preserve their hashes and original versions in the private evidence archive.

See `docs/CODEX_CLOUD_SETUP.md` for an isolated cloud environment and
`DEPLOYMENT_HANDOFF.md` for the generic deployment boundary.
