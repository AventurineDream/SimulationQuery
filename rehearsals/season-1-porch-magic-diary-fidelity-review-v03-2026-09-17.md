# Porch MAGIC diary fidelity review — v03

**Date:** 2026-09-17  
**Status:** Live isolated rehearsal completed; runtime receipt `PASS`, quality
status `HUMAN_REVIEW_REQUIRED`.  
**Evidence root:** `.rehearsal-data/season-1-porch-magic-diary-v05-setback-20260917/`  
**Receipt:** `.rehearsal-data/season-1-porch-magic-diary-v05-setback-20260917/state/magic-diary-rehearsal-report.json`

## Purpose

Test the writer-side diary-fidelity prompt patch against the same live server
pair, scene constraints, and forced `setback` tier used for v04. The patch adds
a traceability checklist, concrete allowed/forbidden examples, and an explicit
separation between evidence, role-sheet goals, and plausible inference.

## Mechanical result

- Scene completed at the eight-turn limit with no cheetah turns and no actor
  output failures.
- The forced Intellect roll was `2d6 = 2 + 3`, MAGIC modifier `+1`, for a
  total of `6`, matching the `setback` target.
- Runtime-owned adjudication matched the roll and was persisted into the next
  director plan.
- Four private diaries were written: Mara 335 words, Eli 404, Rory 459, and
  Sage 392. Eli required one bounded diary-format repair.
- The diary bodies remained private and none leaked into scene prompts.
- The day closed successfully.

## Fidelity result

Final decisions:

- `Rory`: `ACCEPTED`.
- `Eli`: `REJECTED` for attributing a collective wildlife-transport call to
  the family when only Eli called.
- `Mara`: `REJECTED` for timing/causal distortions around the call for help.
- `Sage`: `REJECTED` for invented or unsupported action and private-state
  claims.

Three of four first reviewer envelopes were malformed, and each received one
successful provenance-linked correction. The correction path remains reliable.

## Comparison with v04

The writer prompt patch did not improve the automated direction-safety rate:

| Run | Writer prompt | Diaries safe for direction |
| --- | --- | ---: |
| v04 | pre-patch | 1/4 |
| v05 | observed-fidelity examples and self-audit | 1/4 |

The patch also did not introduce a scene or privacy regression. The remaining
failure is not merely private-state language; the models are still rewriting
the shared event sequence and distributing one character's action across the
family. The next intervention should move part of the diary boundary out of
prompt wording and into a structured evidence-selection or candidate-sentence
validation step.

No live season, publication state, remote checkout, or prior rehearsal root was
changed.
