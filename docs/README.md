# Project documentation map

Start with [project organization](PROJECT_ORGANIZATION.md) for the public/private
storage boundary and [Codex cloud setup](CODEX_CLOUD_SETUP.md) for isolated work.
The root contracts below retain their established paths; status files and dated
reviews record implementation history rather than current private server state.

The repository root holds the current cross-cutting contracts:

- [`PRODUCTION_SPEC.md`](../PRODUCTION_SPEC.md) — product and operating contract.
- [`ARCHITECTURE_SPEC.md`](../ARCHITECTURE_SPEC.md) — technical architecture.
- [`IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md) — implementation sequence.
- [`IMPLEMENTATION_STATUS.md`](../IMPLEMENTATION_STATUS.md) — current verified status and handoff.
- [`DEPLOYMENT_HANDOFF.md`](../DEPLOYMENT_HANDOFF.md) — generic Linux deployment boundary; exact host procedures live in Drive.

Supporting material is grouped by purpose:

- [`narrative-quality/CODEX_REVIEW_2026-09-23.md`](narrative-quality/CODEX_REVIEW_2026-09-23.md)
  — Codex prose candidate, implementation tradeoffs, offline evidence, and peer-review handoff.
- [`dashboard/`](dashboard/) — operator-dashboard product, design, and rehearsal records.
- [`../research/`](../research/) — Simulation Query protocols, codebook, study status, and reviews.
- [`../rehearsals/`](../rehearsals/) — model configurations and chronological rehearsal evidence.
- [`../benchmarks/`](../benchmarks/) — bounded evaluations and model-review records.
- [`../benchmarks/README.md`](../benchmarks/README.md) — benchmark and preparation index.
- [`maintenance/`](maintenance/) — repository-organization records.

Raw rehearsal databases and private call artifacts remain under the ignored
`.rehearsal-data/` tree. They are evidence, not disposable build output, and
must not be deleted or rewritten during ordinary repository cleanup.

The current organization change is recorded in
[the October 12 cleanup record](maintenance/2026-10-12-project-organization.md).
