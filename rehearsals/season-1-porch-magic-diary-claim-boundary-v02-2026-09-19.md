# Porch MAGIC diary claim boundary — v02

**Date:** 2026-09-19  
**Status:** Live isolated rehearsal completed; scene passed, overall receipt
`FAIL` because the diary set was not accepted.  
**Evidence root:** `.rehearsal-data/season-1-porch-magic-diary-v09-claim-mixed-20260919/`  
**Receipt:** `.rehearsal-data/season-1-porch-magic-diary-v09-claim-mixed-20260919/state/magic-diary-rehearsal-report.json`

## Purpose

Exercise the revised diary claim boundary after the first owner calibration:
clearly marked questions, guesses, metaphors, and uncertainty should remain
`SUBJECTIVE`; materially mixed factual and interpretive sentences should be
eligible for `MIXED` and `MANUAL_REVIEW` rather than automatic rejection.

The run reused the v08 scene shape, manifest, config, and forced setback so the
new claim-boundary prompt was the intended change. The first live attempt
stopped during director planning after two invalid plans. A bounded `--resume`
continued the same isolated root; no second rehearsal root was created.

## Mechanical result

- The scene completed at the eight-turn limit with zero cheetah turns.
- The forced Intellect roll was `2d6 = 2 + 3`; MAGIC score `4` supplied `+1`,
  for total `6`, matching the `setback` target.
- Runtime-owned adjudication persisted the failed success criterion and the
  observable consequence into the next beat.
- The first director plan required four total attempts across the initial run
  and resume; round two required one correction for a missing consequence
  detail. Mara's first actor attempt also required one correction for naming a
  diagnosis before the roll.
- Diary text did not leak into scene prompts, and the day closed.

## Diary result

| Character | Final state | Reviewable? | Relevant failures or result |
|---|---|---:|---|
| Mara | `PRIVATE` | No | 296-word first attempt; correction was structurally invalid |
| Eli | `PRIVATE` | No | First attempt authored another character's reaction; correction was 218 words |
| Sage | `PRIVATE` | No | Both attempts were structurally invalid |
| Rory | `WRITTEN` | Yes | 172-word first attempt; 336-word correction accepted; fidelity review accepted |

Rory's review covered all 15 candidates: eight `SUPPORTED`, seven
`SUBJECTIVE`, zero `UNSUPPORTED`, and zero `MIXED`. The revised subjective rule
was exercised successfully on metaphors, personal recollection, emotional
interpretation, and explicit uncertainty. The live run did not produce a
`MIXED` candidate, so the new manual-review branch remains covered by focused
tests rather than live evidence.

One supported classification remains a human-review candidate: Rory's claim
that the animal's posture was a “silent testament to pain” was accepted against
scene references that establish an injured leg but do not plainly state pain.
This is not treated as a confirmed model error without owner review.

## Interpretation

The mechanical and evidence-isolation path remained intact after the rule
change. The diary generator and structured-envelope reliability remain the
larger bottleneck: only one of four characters reached fidelity review, so this
run cannot establish a production-quality claim classifier. The overall receipt
therefore remains `FAIL`, and no diary set was released to future direction.

The next useful step is to improve diary-generation reliability or run a small
controlled claim-review fixture before spending another long live run on the
semantic boundary. Keep the `MIXED` branch opt-in and rehearsal-only.
