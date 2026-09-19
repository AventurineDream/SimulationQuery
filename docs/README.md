# Project documentation map

The repository root holds the current cross-cutting contracts:

- [`PRODUCTION_SPEC.md`](../PRODUCTION_SPEC.md) — product and operating contract.
- [`ARCHITECTURE_SPEC.md`](../ARCHITECTURE_SPEC.md) — technical architecture.
- [`IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md) — implementation sequence.
- [`IMPLEMENTATION_STATUS.md`](../IMPLEMENTATION_STATUS.md) — current verified status and handoff.
- [`DEPLOYMENT_HANDOFF.md`](../DEPLOYMENT_HANDOFF.md) — private Linux deployment procedures.

Supporting material is grouped by purpose:

- [`dashboard/`](dashboard/) — operator-dashboard product, design, and rehearsal records.
- [`../research/`](../research/) — Simulation Query protocols, codebook, study status, and reviews.
- [`../rehearsals/`](../rehearsals/) — model configurations and chronological rehearsal evidence.
- [`../benchmarks/`](../benchmarks/) — bounded evaluations and model-review records.
- [`maintenance/`](maintenance/) — repository-organization records.

Raw rehearsal databases and private call artifacts remain under the ignored
`.rehearsal-data/` tree. They are evidence, not disposable build output, and
must not be deleted or rewritten during ordinary repository cleanup.
