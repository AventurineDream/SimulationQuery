# Codex cloud setup for Simulation Query

This repository can be installed and tested in an isolated Codex cloud
environment. Offline validation needs Python and the package dependencies;
it does not need the private model server or the Season 1 database.

The October 12 cleanup was prepared in an isolated local clone. A cloud VM was
not attached to that chat. These directions prepare the equivalent workflow for
future work; they are not a claim that a cloud environment has been created.

## Create an environment

1. Open Settings > Codex Cloud > Environments and choose Create environment.
2. Select `AventurineDream/SimulationQuery` and describe the setup below. Complete
   any GitHub connection prompt and keep the environment private.
3. Ask the setup agent to create a local virtual environment, install the test
   and optional TUI dependencies, and run the offline checks.
4. Review setup results, save the environment, and publish it. Start a task with
   that environment selected.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,tui]'
.venv/bin/python -m pytest -q
.venv/bin/python scripts/check_repository.py
.venv/bin/improv validate examples/the_last_train.plan.json
.venv/bin/improv run examples/the_last_train.plan.json --dry-run
```

Allow the package registry destinations needed for installation. A normal
software cleanup does not require model credentials, a VPN to the run host, or
an active service. Create the virtual environment on the VM rather than copying
one from another machine.

## Private material

Use the connected Drive tools, when available in the selected environment, to
read private source documents by their existing IDs. Otherwise copy the required
verified archive into the task's private workspace. Keep private input outside
the Git checkout, preserve its manifest, and verify checksums after transfer.
Never commit private evidence to make it accessible to a cloud task.

Save outputs back to Drive and public changes through GitHub. A task VM's saved
state is a working copy, not a replacement for either source of truth. This
project's completed Season 1 archive and run host have their own preservation
boundary; leave service and closure actions to a separately recorded decision.

The current product workflow, including publishing environments and starting
tasks, is documented in [OpenAI's cloud environments guide](https://learn.chatgpt.com/docs/environments/cloud-environments).
