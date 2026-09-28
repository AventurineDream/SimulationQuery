# Rehearsal evidence index

This directory is intentionally chronological. Configuration and report files
stay beside their historical names so raw audit references remain stable.

## Current porch-season reliability line

- [`season-1-porch-retry-cleanup-2026-09-20.md`](season-1-porch-retry-cleanup-2026-09-20.md)
  — actor challenge-state and director-render retry fixes, honest batch receipts,
  and separate live scene/correction checks; preserves the failed five-run
  baseline and distinguishes mechanical acceptance from semantic quality.
- `season-1-porch-live-*` — shared live server configuration and manifest. The
  historical `scripts/run_live_porch_rehearsal.py` runs five 16-turn strategies
  without requiring a MAGIC challenge; it cannot establish dice coverage when
  no rolls occur. Use `scripts/run_live_magic_dice_rehearsal.py` for a controlled
  eight-turn dice/adjudication check, or `scripts/run_live_magic_diary_rehearsal.py`
  for the separate diary-quality gate.
- `season-1-porch-magic-dice-*` — deterministic roll and outcome-tier work.
- [`season-1-porch-magic-action-result-boundary-2026-09-21.md`](season-1-porch-magic-action-result-boundary-2026-09-21.md)
  — action/result contract patch and fresh eight-turn live setback rehearsal;
  mechanical receipt passed, while visible prose still needs semantic review.
- `season-1-porch-magic-adjudication-boundary-*` — runtime-owned adjudication.
- [`season-1-porch-magic-diary-claim-boundary-v02-2026-09-19.md`](season-1-porch-magic-diary-claim-boundary-v02-2026-09-19.md)
  — latest live boundary rehearsal; the scene and runtime-owned setback passed,
  but only Rory reached claim review, so the new `MIXED` branch was not live
  exercised.
- [`diary-claim-reviewer-live-probe-synthetic-v02-2026-09-20.md`](diary-claim-reviewer-live-probe-synthetic-v02-2026-09-20.md)
  — replayed the same synthetic fixture after a prompt/schema patch; the model
  still mislabeled the mixed claim, while a conservative exact-evidence-overlap
  runtime fallback routes this observed case to manual review.
- [`diary-claim-reviewer-live-probe-synthetic-v01-2026-09-20.md`](diary-claim-reviewer-live-probe-synthetic-v01-2026-09-20.md)
  — isolated live test of the diary reviewer using synthetic evidence; clear
  claim labels passed, but the mixed-claim classification/manual-review route
  and its single correction retry failed.
- [`season-1-porch-magic-diary-claim-audit-v01-2026-09-18.md`](season-1-porch-magic-diary-claim-audit-v01-2026-09-18.md)
  — preceding live rehearsal; deterministic sentence candidates and structured
  per-claim audits caught four unsupported Mara claims while Eli's complete
  claim audit passed.
- [`season-1-porch-magic-diary-reviewer-evidence-v01-2026-09-17.md`](season-1-porch-magic-diary-reviewer-evidence-v01-2026-09-17.md)
  — latest diary-gated live rehearsal; reviewer-side evidence-reference
  findings are now structured and the run records a concrete event-order catch.
- [`season-1-porch-magic-diary-evidence-references-v01-2026-09-17.md`](season-1-porch-magic-diary-evidence-references-v01-2026-09-17.md)
  — preceding diary-gated rehearsal; writer evidence references are
  range-checked and persisted, while prose fidelity remains open.
- `season-1-porch-magic-diary-fidelity-review-v03-2026-09-17.md` — preserved
  the preceding writer-prompt experiment and its matched comparison.
- `season-1-porch-magic-diary-fidelity-review-v02-2026-09-17.md` — preserved
  the first live validation of the reviewer correction path.
- `season-1-porch-magic-diary-fidelity-review-v01-2026-09-17.md` — preserved
  pre-v02 implementation and first-live-attempt history.

## Simulation Query Pilot 2

Files beginning `sq-pilot2-` preserve selected, validated, retry, context, and
multi-day study configurations. The governing research documents are indexed
in [`../research/README.md`](../research/README.md).

## Historical actor auditions

Files beginning `actor-audition-` preserve the evolving v2-v21 comparison
conditions. They must not be treated as independent trials or collapsed into a
single score; prompt, validator, role, and director conditions changed between
versions.

The corresponding databases and private model-call artifacts live under
`.rehearsal-data/`. That ignored tree is retained research evidence, not cache.
