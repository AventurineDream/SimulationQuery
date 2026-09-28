# Porch MAGIC diary claim audit — v01

**Date:** 2026-09-18  
**Status:** Live isolated rehearsal completed; runtime receipt `FAIL`, quality
status `HUMAN_REVIEW_REQUIRED`.  
**Evidence root:** `.rehearsal-data/season-1-porch-magic-diary-v08-claim-audit-20260918/`  
**Receipt:** `.rehearsal-data/season-1-porch-magic-diary-v08-claim-audit-20260918/state/magic-diary-rehearsal-report.json`

## Purpose

Test a sentence-level diary boundary without changing the normal production
default. In this opt-in rehearsal, the runtime deterministically splits each
private diary into numbered claim candidates. The reviewer must return exactly
one structured audit for each candidate as `SUPPORTED`, `SUBJECTIVE`, or
`UNSUPPORTED`, with accepted-scene evidence IDs for supported claims. The
runtime checks coverage, duplicate and unknown candidate IDs, evidence ranges,
and unsupported classifications. An unsupported claim overrides a top-level
`ACCEPT`; diary text remains withheld unless the complete review is accepted.

## Automated verification

- Focused diary and boundary tests: **85 passed**.
- Full local suite: **362 passed**.
- Python compilation and `git diff --check`: passed.
- The new deterministic claim splitter, tagged/native claim-audit parsing,
  complete-coverage checks, and fail-closed override each have test coverage.

## Live mechanical result

- Same isolated porch configuration and model pair as v06/v07; forced target
  outcome `setback`.
- The scene completed at the eight-turn limit with zero cheetah turns, no
  actor-output failure, and no scene error.
- Forced Intellect roll: `2d6 = 2 + 3`; MAGIC score `4` gives modifier `+1`,
  for total `6`, matching the `setback` target. Runtime adjudication and its
  observable consequence were persisted into the next beat.
- The day closed successfully, and no diary body leaked into scene prompts.

The receipt's `FAIL` is downstream diary quality/acceptance, not a mechanical
scene failure.

## Diary and claim-audit result

| Character | Diary result | Words | Writer evidence refs | Claim audit | Fidelity result |
| --- | --- | ---: | --- | --- | --- |
| Mara | written, attempt 1 | 337 | 1, 6, 7, 12, 13, 19, 26, 16, 14 | 15/15 covered; 4 unsupported | `REJECTED` |
| Eli | written, attempt 1 | 373 | 6, 7, 8, 14, 26 | 18/18 covered; 0 unsupported | `ACCEPTED` |
| Sage | private after malformed/short correction | 246 | — | not reviewed | not reviewed |
| Rory | private after short/autonomy-invalid correction | 353 | — | not reviewed | not reviewed |

Mara's audit identified four unsupported candidates. One cited scene evidence
for the cheetah's fresh scar but presented that detail as Mara's direct
observation even though it was revealed after the failed MAGIC challenge. The
other findings covered an unsupported family-history claim, interpretive
language presented as externally verifiable, and an unsupported inference
about Eli's private state. The existing top-level reviewer also emitted three
evidence-reference findings, and the runtime persisted the claim-level issues
separately in the private review artifact and fidelity event.

Eli's reviewer returned a complete 18-item audit: every candidate was either
supported by cited scene evidence or marked as subjective, with no unsupported
claim. This is the first rehearsal result showing a written diary passing the
new per-claim coverage layer, although it is not evidence that the model's
semantic classifications are always correct.

Sage's first diary envelope was malformed and its correction was only 246
words. Rory's first diary was 170 words; its 353-word correction was rejected
by the existing other-character-autonomy validator. Both remained private and
were correctly excluded from fidelity review.

## Interpretation and next experiment

The claim-audit boundary increased diagnostic resolution. v07 produced a
diary-level evidence/order finding; v08 identified the specific candidate
claims that caused Mara's rejection while allowing Eli's complete review to
pass. The runtime also proved that a model cannot silently turn a top-level
`ACCEPT` into direction-safe status when its claim audits contain
`UNSUPPORTED` entries.

The main unresolved risk is calibration, not plumbing. Some interpretive or
subjective sentences were classified as `UNSUPPORTED`, so the next study
should create a small human-labeled claim set and measure false positives and
false negatives before enabling this gate outside rehearsals. This live sample
is stochastic and does not establish a causal improvement over v07.

No live season, publication state, remote checkout, or prior rehearsal root was
changed.
