# Porch scene retry cleanup — 2026-09-20

Started September 20; final evidence review September 21. All four new
experiments are terminal, with no in-flight model calls remaining.

## Scope and baseline

This is a local runtime patch and isolated live verification, not a production
deployment. Existing diary/claim-calibration work and all private research roots
are preserved. No publication or season restart is authorized by these results.

The preceding five-strategy batch used the historical, unforced
`run_live_porch_rehearsal.py` harness. That harness allows MAGIC challenges but
does not require them. Its database contains **zero accepted challenges and zero
rolls**. This is missing exercise coverage, not evidence that dice logging is
unimplemented: the dedicated MAGIC dice and diary harnesses already record
`MagicRollResolved` events.

Read-only re-evaluation of the baseline database with the new receipt logic:

| Variant | Accepted actor turns | Persisted ending | Receipt |
| --- | ---: | --- | --- |
| R1 — cautious disclosure | 16 | COMPLETED / turn_limit | PASS |
| R2 — secretive kids | 16 | COMPLETED / turn_limit | PASS |
| R3 — twin alliance | 16 | COMPLETED / turn_limit | PASS |
| R4 — Mara adventure | 15 | COMPLETED / round_limit | FAIL |
| R5 — Eli care | 12 | INTERRUPTED / orchestrator_director_contract_invalid | FAIL |

Batch: **FAIL**, 75/80 accepted actor turns, no diaries or cheetah turns,
dice coverage `NOT_EXERCISED`. The original database and report were not rewritten.

Baseline root:
[`season-1-porch-live-20260912-rerun-20260920`](../.rehearsal-data/season-1-porch-live-20260912-rerun-20260920/).

## Diagnoses and changes

1. **Actor challenge state was implicit.** Mara selected a stat without a pending
   challenge in R4 round 2, then repeated it in her correction. Actor prompts now
   state the runtime's current actor-specific challenge or explicitly say there
   is none. The no-challenge retry gives a metadata-only instruction: preserve
   the character's move and remove the stat selection. Following the failed
   live probe below, v9 makes this a small envelope-repair prompt without the
   full play context, and requires the cleaned shared text to remain exactly
   unchanged. Rejection codes survive interruption/resume so the specific
   instruction is retained. The validator still rejects unauthorized stat
   selection; no stat or roll is silently added or removed by the runtime.
2. **Director-render retries used a different acceptance path.** R5 round 4 first
   failed for actor puppeteering. Its correction removed that issue but repeated
   decorative imagery. First attempts could already drop repetitive optional
   flavor and compile the validated plan, but corrections could not. Both now use
   one implementation. Only repetition permits this fallback; the unchanged plan
   is rechecked, raw output is retained, and an event identifies the affected call.
   Continued puppeteering or malformed corrections still stop the scene.
3. **The historical batch could exit successfully after a failed experiment.**
   It now reports per-variant pass/fail, observed dice coverage and persisted
   diary/cheetah counts, and returns a nonzero exit status unless all five
   variants complete their required 16 actor turns within scope. Harness routing
   is explicit in the script and rehearsal index.

## Verification plan and boundaries

- H1: Both first and corrected renders can discard repetitive optional flavor
  without changing the approved plan. Regression tests cover both paths, raw
  audit/provenance, and refusal when repetition remains in the plan.
- H2: Actor prompts distinguish their own pending challenge from absent, consumed,
  or another actor's challenge. A no-challenge correction retains its targeted
  instruction across a transport interruption. Regression tests cover these states.
- H3: A completed-but-short or interrupted batch cannot pass. Receipt tests cover
  the observed 75/80 failure, missing/duplicate variants, unexpected diaries or
  cheetah turns, observed roll counts, and command exit status.
- Live check: one fresh, two-round/eight-actor-turn MAGIC setback rehearsal with
  the existing `qwen3:30b-instruct` Orchestrator and `gpt-oss:20b` actors. The first
  die pair is configured for a controlled tier; this is not an outcome-variance measurement
  or a repetition of the earlier five-strategy batch. No diaries or cheetah turns.

Final local checks for that patch: **387 tests passed** (baseline 366), Python compilation passed,
and whitespace validation passed. Existing malformed-output and continued-
puppeteering tests still fail closed.

Live result: **FAIL**. The database ended `COMPLETED / round_limit` with **7/8
accepted actor turns, zero rolls, zero diaries, and zero cheetah turns**. The
script returned exit code 1. The initial plan omitted the required MAGIC setup;
its single correction was accepted. Mara's first attempt then stated a diagnosis;
its correction retained a forbidden medical term. Both were rejected and one
neutral interruption replaced that slot. The other seven actor turns were
accepted. The configured forced die pair was never used.

Assistant review found an additional semantic failure: the second director
plan credited Mara with confirming the challenged weight-bearing finding,
despite her rejected move and the absence of any roll. Other accepted actors
mentioned general weight shifts, but none supplied an accepted Mara check or
runtime result. This is a substantive unearned-result/attribution problem,
not a model transport failure. A broader action/result contract remains needed.

This full-scene run used the v7 actor prompt and does not exercise the subsequent
v8/v9 refinements below. It also did not trigger a director-render retry or
flavor-drop event: the unified render fallback is regression-tested, not newly
confirmed on the server by this scene.

Live root:
[`season-1-porch-magic-dice-retry-cleanup-20260920`](../.rehearsal-data/season-1-porch-magic-dice-retry-cleanup-20260920/).
Machine receipt:
[`magic-dice-rehearsal-report.json`](../.rehearsal-data/season-1-porch-magic-dice-retry-cleanup-20260920/state/magic-dice-rehearsal-report.json).

## Focused follow-up

The new live failure motivates a separate, bounded v8 prompt test. The
pre-roll correction now asks for **one method and one still-unanswered
question**, ending before any finding; it also rules out reframing a diagnosis
as a cautionary reason for acting. Forbidden-term checks and the one-retry
limit remain intact.

`scripts/run_live_magic_actor_retry_probe.py` isolates this path. It uses the
ordinary scene service with a scripted opening and rejected original, then
sends exactly one correction to the existing actor model. Scripted calls are
labeled `scripted-fixture`, not attributed to either live model. The probe
does not continue into other actor slots when the correction fails. Three
initial local tests verify its success/failure and call-provenance boundaries;
a fourth verifies refusal of even a small textual rewrite in metadata repair.

H4: The method/question instruction permits an accepted attempt and recorded
controlled roll after this synthetic premature-result rejection. One successful
case would be evidence of capability, not a live success-rate estimate.

Probe root:
[`season-1-porch-magic-actor-retry-probe-20260920`](../.rehearsal-data/season-1-porch-magic-actor-retry-probe-20260920/).
Result: **mechanical PASS, semantic attempt-only boundary FAIL on assistant
review**. Exactly one server call supplied the correction, which was accepted
and recorded `2d6 = 2 + 3`, Intellect modifier `+1`, total `6`, setback. However,
the corrected text still asserts gait/contact observations before the roll;
the opening established a raised paw at rest, not these new observations.
The method/question prompt did not fully solve the attempt/result boundary.
No post-roll consequence or diary was tested.

The probe's generated PASS is a mechanical receipt only, not a prose-quality
approval. Its saved output and roll event remain unchanged. The runner now
explicitly labels future receipts `status_scope: mechanical_contract_only` and
`quality_status: HUMAN_REVIEW_REQUIRED` to make that distinction harder to miss.

A companion no-challenge probe tests the metadata-only correction with one
server call and no expected roll:
[`season-1-porch-magic-no-challenge-retry-probe-20260920`](../.rehearsal-data/season-1-porch-magic-no-challenge-retry-probe-20260920/).
Result: **FAIL**. The model removed the stat but replaced the supplied move with
new observations/actions. `CORRECTION_SCOPE_DRIFT` withheld it; zero accepted
actor turns and zero rolls. The guard worked, but the v8 prompt did not repair
the move.

The v9 follow-up removes the scene/performance context from this metadata-only
request, retains the exact rejected text, and applies an exact-text acceptance
check. All other character/safety checks and the one-retry limit remain in
force. The same fixture is replayed once in a separate root:
[`season-1-porch-magic-no-challenge-retry-probe-v02-20260920`](../.rehearsal-data/season-1-porch-magic-no-challenge-retry-probe-v02-20260920/).
Result: **PASS for this targeted repair**, one live correction. The returned
envelope has `magic_stat: null` and text exactly equal to the rejected original;
the runtime accepts one actor turn and records zero rolls. Assistant review
confirmed exact equality directly from the saved output. This is a targeted
comparison, not an independent reliability sample or a rewrite of the failed
first probe.

| Live probe | Prompt | Mechanical receipt | Assistant prose review |
| --- | --- | --- | --- |
| Premature result | v8 | PASS; forced roll totals 6 | FAIL: still asserts pre-roll findings |
| Stat without challenge, original | v8 | FAIL; scope drift, zero rolls | FAIL: character move rewritten |
| Same no-challenge fixture, scoped repair | v9 | PASS; zero rolls | PASS: text preserved exactly |

These are three single-correction calls after explicitly scripted rejections,
not three complete live scenes. All raw calls and reports remain separate.

## Interpretation limits

Local regression success is not a measured improvement in live-model success
rate. A passing eight-turn run would not establish 16-turn reliability, diary
quality, calibrated semantic review, or readiness to ship. The existing diary
quality gate remains a separate unresolved line of work.

The harnesses use a virtual fiction clock. Their model-call timestamps and
latencies are not used here as server performance measurements.

The recommended next design change—separating the actor's attempted method
from shared prose and keeping unresolved challenges active—was implemented and
verified in the follow-up [action/result boundary rehearsal](season-1-porch-magic-action-result-boundary-2026-09-21.md).
That patch establishes runtime ownership of the roll and receipt, but the live
review still found visible pre-roll observations and unsupported pain/injury
language. The next test should target that prose policy in isolation. Expanding
a medical-word list alone cannot establish the semantic boundary. The current
evidence still does not establish a need for post-training.
