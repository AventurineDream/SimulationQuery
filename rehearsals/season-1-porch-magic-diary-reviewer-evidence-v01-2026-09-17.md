# Porch MAGIC reviewer evidence validation — v01

**Date:** 2026-09-17  
**Status:** Live isolated rehearsal completed; runtime receipt `FAIL`, quality
status `HUMAN_REVIEW_REQUIRED`.  
**Evidence root:** `.rehearsal-data/season-1-porch-magic-diary-v07-setback-20260917/`  
**Receipt:** `.rehearsal-data/season-1-porch-magic-diary-v07-setback-20260917/state/magic-diary-rehearsal-report.json`

## Purpose

Move one more part of diary fidelity out of free-form prompt wording. The
reviewer now receives the writer's claimed evidence references alongside a
numbered copy of the accepted scene. It must report a structured
`evidence_reference_issues` finding when a concrete shared-fiction claim is
uncited, mismatched, or in the wrong causal/event order. The writer's claims
remain untrusted: the reviewer decides whether the cited evidence supports
them. The new reviewer and correction calls use v2 provenance identifiers.

## Automated verification

- Focused diary and boundary tests: **84 passed**.
- Full local suite before the live run: **361 passed**.
- `git diff --check`: passed.
- Coverage proves the reviewer receives numbered accepted-scene evidence and
  the writer's reference receipt, while the new finding category remains
  fail-closed in the structured envelope and tagged fallback parser.

## Live mechanical result

- Same isolated porch configuration and model pair as the preceding diary
  rehearsal; forced target outcome `setback`.
- The scene completed at the eight-turn limit with zero cheetah turns and no
  scene error. The runtime receipt's `FAIL` is the downstream diary-quality
  gate, not a scene-execution failure.
- Forced Intellect roll: `2d6 = 2 + 3`; MAGIC score `4` gives modifier `+1`,
  for total `6`, matching the `setback` target. Runtime adjudication and the
  observable consequence were persisted into the next beat.
- The day closed successfully, and no diary body leaked into scene prompts.

## Diary and reviewer result

| Character | Diary result | Words | Writer evidence refs | Fidelity result |
| --- | --- | ---: | --- | --- |
| Mara | written, attempt 1 | 422 | 6, 7, 8, 12, 13, 14, 18, 19, 23, 24 | `ACCEPTED` |
| Eli | private after two invalid envelopes | — | — | not reviewed |
| Sage | written, attempt 2 | 343 | 6, 15, 16, 19 | `ACCEPTED` after reviewer correction |
| Rory | written, attempt 1 | 382 | 16, 23 | `REJECTED` after reviewer correction |

The reviewer-side evidence finding fired for Rory:

- Evidence ID 16 placed Rory's discovery of the porch crack during setup, but
  the diary implied that he noticed it before that action, changing the event
  order.
- The same review also found unsupported attribution of Rory's private
  motivation and symbolic interpretation. This confirms that the new evidence
  category can expose an event-order error, but it does not by itself solve
  first-person/private-state overreach.

Two initial reviewer envelopes (Sage and Rory) were structurally invalid. Each
used the one bounded correction path successfully; Sage's corrected review was
accepted, while Rory's corrected review was a valid rejection. Eli's malformed
diary and failed correction remained private and was not sent to the reviewer.

The quality gate therefore withheld all diary material from future direction:
`diary_fidelity_safe_for_direction=false`. The accepted Mara and Sage reviews
are useful audit evidence, not authorization to promote their diary text into
canon or later scene context.

## Interpretation and next experiment

The patch worked at the narrow boundary it targeted: the live reviewer used a
numbered scene reference to identify a concrete chronology mismatch and
persisted it as `evidence_reference_issues`. The run still does not establish
that diary prose is safe for automatic direction, because one accepted diary
was rejected and another remained private.

This is not a controlled claim that v07 is better or worse than v06. The local
model sample is stochastic. Descriptively, v07 produced two accepted reviews
from three reviewable diaries, one rejected review with an evidence-reference
finding, and one private diary; v06 had four written diaries, three rejected
reviews, and one unavailable review. The next bounded experiment should test
candidate-sentence or per-claim validation using the same evidence receipt,
rather than adding more general diary prose instructions.

No live season, publication state, remote checkout, or prior rehearsal root was
changed.
