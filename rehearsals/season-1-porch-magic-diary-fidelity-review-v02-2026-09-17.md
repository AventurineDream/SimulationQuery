# Porch MAGIC diary fidelity review — v02

**Date:** 2026-09-17  
**Status:** Live isolated rehearsal completed; runtime receipt `PASS`, quality
status `HUMAN_REVIEW_REQUIRED`.  
**Evidence root:** `.rehearsal-data/season-1-porch-magic-diary-v04-setback-20260917/`  
**Receipt:** `.rehearsal-data/season-1-porch-magic-diary-v04-setback-20260917/state/magic-diary-rehearsal-report.json`

## Purpose

Exercise the new one-correction diary-fidelity boundary against the same live
server pair and forced `setback` tier as v03, keeping the scene and model
configuration matched while changing only the isolated evidence root.

## Mechanical result

- Scene completed at the eight-turn limit with no cheetah turns.
- The forced Intellect roll was `2d6 = 2 + 3`, MAGIC modifier `+1`, for a
  total of `6`, matching the `setback` target.
- Runtime-owned adjudication matched the roll and was persisted into the next
  director plan.
- Four private diaries were written and accepted: Mara 521 words, Eli 583,
  Rory 503, and Sage 478.
- The diary bodies remained private and none leaked into scene prompts.
- The day closed successfully.

## Fidelity-retry result

The new retry was exercised live. Mara, Rory, and Sage each returned a
malformed first review envelope. The runtime recorded each first response as
`STRUCTURED_OUTPUT_INVALID`, issued exactly one correction linked by
`correction_of_call_id`, and accepted the corrected envelope. Eli's first
review envelope was structurally valid and required no correction.

Final decisions after correction:

- `Rory`: `ACCEPTED`.
- `Eli`: `REJECTED` for invented events and unsupported claims about Mara's
  private state.
- `Mara`: `REJECTED` for an unsupported claim about Eli's private feeling.
- `Sage`: `REJECTED` for an unsupported claim about Eli's private motivation.

The fail-closed context gate therefore withheld three diary bodies from future
direction while allowing Rory's accepted diary through. This is the intended
mechanical behavior. It is not a clean narrative-quality pass because the
reviewer still finds recurring cross-character mind-reading in the diaries.

## Findings and next hypothesis

The correction patch improves reviewer-envelope reliability, but it does not
solve actor diary fidelity. The live evidence supports a narrower hypothesis:
the next patch should constrain diary generation itself to observed action,
spoken dialogue, and the writer's own internal state, with a small explicit
example of prohibited cross-character inference. The reviewer should remain
independent and fail-closed while that actor-prompt change is tested.

No live season, publication state, remote checkout, or raw prior rehearsal root
was changed.
