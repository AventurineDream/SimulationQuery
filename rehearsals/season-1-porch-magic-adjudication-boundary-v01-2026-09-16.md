# Porch MAGIC adjudication boundary — v01

**Date:** 2026-09-16  
**Status:** Implemented and locally verified; live-model validation is recorded separately.

## Decision

Mechanical MAGIC adjudication belongs to the runtime, not to director-authored prose or
structured plan fields. After an accepted actor action, the runtime validates the immutable roll
ledger and derives the outcome tier, goal status, and goal answer from the precommitted success
criterion.

The director receives the derived result as private state and supplies only the playable
consequence inputs:

- `magic_effect_detail`: one short observable consequence, clue, complication, or opening;
- `magic_cost_type`: one tangible cost type for `costly_success` only.

The runtime validates those inputs against the derived tier, requires a short observable detail,
rejects unsupported result claims, and compiles the exact accepted detail into the visible beat.
Pressure, choices, and canon must remain compatible with the consequence but do not need to copy
its sentence.

## Boundary details

- `MagicAdjudication` is derived by `adjudicate_magic_roll` from a validated `MagicRollResult`.
- Invalid rolls do not partially mutate game state.
- A pending adjudication forces the structured director-plan path, even when ordinary beats use
  single-pass directing.
- `DirectorPlanEnvelope` no longer exposes `magic_result_ack`, `magic_goal_status`, or
  `magic_goal_answer`.
- Legacy fields are stripped while replaying old JSON/tagged artifacts so stale model-authored
  adjudication cannot override a recorded roll.
- `DirectorPlanAccepted` persists the runtime adjudication beside the accepted plan for audit and
  replay.
- The live rehearsal report now checks runtime adjudication persistence and consequence inputs,
  rather than asking whether a model copied an outcome acknowledgement.
- Forbidden-language retries identify the exact matched terms from the rejected plan or actor turn,
  prohibit their inflections and close medical synonyms, and direct the model toward observation-only
  wording while preserving the one-retry limit.

## Verification

- Focused MAGIC/scene-runner suite: **75 passed** after the boundary revision and retry update.
- Full suite excluding the pre-existing date-sensitive scheduled-resume fixture:
  **345 passed, 1 deselected**.
- `compileall`: passed.
- `git diff --check`: passed.
- Live harness `--help` smoke check: passed.
- The initial strict-copy live gate is recorded in
  [the v01 live validation note](season-1-porch-magic-adjudication-boundary-live-v01-2026-09-16.md).
- The revised three-branch live gate is recorded in
  [the v02 live validation note](season-1-porch-magic-adjudication-boundary-live-v02-2026-09-16.md).

The remaining full-suite fixture is
`test_explicit_scheduled_resume_reopens_only_the_stopped_run`; it uses an earlier scheduled date
and reports `COMPLETED` instead of its hard-coded `SCHEDULED` expectation under the current
workspace date. No scheduling code was changed here.

## Next gate

The runtime boundary and bounded safety retry are ready for the next isolated experiment. If diaries
are introduced, keep them as the only new variable and retain the current safety guards. The live
follow-up still has ordinary model-output variance outside this contract, so do not use a single
interrupted branch as evidence that diary handling is responsible for a failure.
