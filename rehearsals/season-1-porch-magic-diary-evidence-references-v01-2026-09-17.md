# Porch MAGIC diary evidence references — v01

**Date:** 2026-09-17  
**Status:** Live isolated rehearsal completed; runtime receipt `PASS`, quality
status `HUMAN_REVIEW_REQUIRED`.  
**Evidence root:** `.rehearsal-data/season-1-porch-magic-diary-v06-setback-20260917/`  
**Receipt:** `.rehearsal-data/season-1-porch-magic-diary-v06-setback-20260917/state/magic-diary-rehearsal-report.json`

## Purpose

Move diary fidelity one step out of free-form prose. The diary envelope now
requires `evidence_refs`: unique, one-based IDs into the exact accepted scene
supplied to that writer. The runtime rejects references outside that scene,
records accepted references in the `DiaryWritten` event, and treats malformed
diary envelopes as private with the existing one-attempt correction path.

The patch also exposes an `accepted_scene_evidence` list in the writer brief,
updates the tagged fallback format, records the v6 prompt/context provenance,
and makes strict day rehearsal repairable after `DiaryEvidenceInvalid`.

## Automated verification

- Focused diary and boundary tests: **84 passed**.
- Full local suite: **361 passed**.
- `git diff --check`: passed.
- New coverage proves missing/duplicate/non-integer references fail closed,
  out-of-scene IDs become `PRIVATE` with `DIARY_EVIDENCE_REF_INVALID`, and a
  valid correction remains linked to the rejected call.

## Live result

- Same isolated porch configuration and model pair as v04/v05; forced target
  outcome `setback`.
- Scene completed at the eight-turn limit with zero cheetah turns and no
  actor-output failure that stopped the scene.
- Forced Intellect roll: `2d6 = 2 + 3`; MAGIC score `4` gives modifier `+1`,
  for total `6`, matching the `setback` target. Runtime adjudication and the
  observable consequence were persisted into the next beat.
- All four diaries were accepted and day closure completed:

  | Character | Attempt | Words | Evidence references |
  | --- | ---: | ---: | ---: |
  | Mara | 1 | 446 | 8 |
  | Eli | 1 | 505 | 7 |
  | Sage | 2 | 336 | 3 |
  | Rory | 1 | 337 | 5 |

- Sage's first envelope was malformed; the private correction succeeded and
  remained linked to the original rejected call. No `DiaryEvidenceInvalid`
  event occurred in this run: every accepted reference set was within the
  26-line accepted scene.
- Diary bodies stayed in private artifacts, and the receipt reports no diary
  text leaked into scene prompts.

## Fidelity result

The evidence-reference contract improved provenance at the envelope boundary,
but it did not make the diary prose safe for future direction by itself:

- Mara: `REJECTED` for an unsupported private-state inference about the
  cheetah's attention.
- Eli: `REJECTED` for invented/causally mislocated scene details.
- Sage: `REJECTED` for invented action and unsupported private-state claims.
- Rory: `UNAVAILABLE` after both the initial and one correction review
  envelopes were malformed.

The quality gate therefore withheld all four diaries from future direction.
This is not a controlled claim that v06 is worse than v05: the live model
sample is stochastic. Descriptively, the matched receipt moved from v05's
`1/4` reviewer-safe diaries to v06's `0/4`, while v06 newly proves that
structured evidence references are persisted and range-checked.

## Interpretation and next experiment

The patch successfully creates a machine-readable traceability layer, but the
current fidelity reviewer does not yet consume those references when judging
individual sentences. The next bounded intervention should use the references
to drive reviewer-side evidence selection or candidate-sentence checks, then
repeat the same one-day run with the same target and preserve this record as
the baseline.

No live season, publication state, remote checkout, or prior rehearsal root was
changed.
