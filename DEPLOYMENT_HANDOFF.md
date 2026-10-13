# Deployment handoff

This is a generic deployment boundary for AI Improv Troupe. Exact private host
addresses, operator paths, installed model bindings, and previous transfer/restart
commands are preserved in the SimulationQuery Drive operating archive.
Use its current record before interacting with a deployed service.

## Service layout

The supplied units use these conventional paths:

- `/opt/improv-troupe`: installed source and a virtual environment created on Linux.
- `/etc/improv-troupe/config.yaml`: operator configuration.
- `/var/lib/improv-troupe`: persistent, backed-up service data.

See [the example configuration](deploy/config.example.yaml),
[the service unit](deploy/improv-troupe.service), and
[the example model manifest](deploy/model-manifest.example.json).
Copy and review examples privately; configure the actual endpoint and filesystem
for the target. A virtual environment from another machine is not portable.

## Prepare and verify

Use a fresh checkout of an explicitly selected commit. Install and run the
[offline checks](AGENTS.md) before deployment. Compare the intended source,
dependencies, model/configuration hashes, receipt, and target service state with
the private operating record. A running worker retains its imported code; updating
an editable checkout is not proof that the worker runs the new version.

Before any service action, preserve the current database and its WAL state,
launch receipts, logs, provider request/response archives, model outputs, manifests,
and completed-scene snapshots. Check the actual process and lock holder rather
than relying on a PID or lock file alone.

The exact transport mechanism depends on the target. Use a reviewed transfer into
a separate staging directory and verify hashes before replacing source. Preserve
user edits and never copy a development virtual environment onto another host.

## Operating decisions

Starting or restarting a worker, resuming an interrupted scene, changing a frozen
configuration, ending a season, and publishing artifacts each need their own
recorded decision. A dry worker must use a separate temporary data root; it must
not advance real season state. Keep the dashboard authenticated and privately
reachable, and keep its password material out of the repository and archives.

Mechanical scene completion, diary quality review, and administrative closure
are distinct. The current Drive index records the completed Porch run and its
remaining closure decision. Historical S01/S02 instructions are preserved as
history and are not a current deployment prescription.

See [project organization](docs/PROJECT_ORGANIZATION.md) for private evidence
locations and [cloud setup](docs/CODEX_CLOUD_SETUP.md) for isolated development.
