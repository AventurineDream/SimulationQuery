# Diary claim reviewer live probe — synthetic fixture — v02

**Date:** 2026-09-20  
**Status:** `MODEL CLASSIFICATION FAIL; CONSERVATIVE RUNTIME ROUTE PASS ON REPLAYED OUTPUT`  
**Model:** `qwen3:30b-instruct`, the v09 reviewer/Orchestrator model  
**Private evidence:** `.rehearsal-data/diary-claim-probe-synthetic-v02-20260920/private/`

## Scope

This replay used the same eight-claim synthetic library fixture as v01, the
production prompt builder, native structured response schema, parser, and
runtime claim-routing helper. It made two live requests to the configured
Ollama server: a seven-claim clear-boundary batch and the isolated mixed claim.
The response parser now accepts a `REJECT` envelope when a claim audit itself
provides the unsupported/mixed reason, so the model's mixed response did not
trigger a correction request. No diary, saved rehearsal scene, or rehearsal
database was sent to or changed on the server.

Expected labels remain researcher-authored fixture expectations, not human
calibration labels. `MIXED` is a model-side routing expectation, not a new human
label.

## Live model results

| Check | Observed | Assessment |
|---|---|---|
| Seven clear claims | 7/7 labels matched; required citations were present | Pass for these examples |
| Clear-batch model decision | `REJECT`; runtime decision `REJECTED` | Pass |
| Mixed claim label | Model returned `UNSUPPORTED`, with no evidence citation, rather than `MIXED` | Fail |
| Mixed claim model decision | `REJECT`, with an unsupported-claim audit and a top-level private-state finding | Parsed successfully; still not the required model route |
| Request count | Two native-schema calls; about 72 seconds and 12 seconds | No correction call |

Raw label agreement remains **7/8 (87.5%)**, the same as v01. The stronger
contrastive prompt did not resolve the mixed-claim classification failure.

## Runtime route after the live result

The live response's issue names only the unsupported seasonal-closure clause;
the diary candidate also contains the accepted-scene statement that Mina placed
the blue umbrella beside the library steps. The model omitted that supporting
evidence reference. To avoid converting this kind of apparent partial support
into an automatic rejection, the runtime now conservatively checks whether an
`UNSUPPORTED` candidate contains an exact normalized accepted-scene statement.
If so, it preserves the model's raw audit but routes the diary to
`MANUAL_REVIEW`. A model-provided `MIXED` audit also routes to manual review,
even when another candidate is unsupported.

Reapplying the v02 server outputs to the new production runtime helper routes
the clear batch to `REJECTED` and the mixed candidate to `MANUAL_REVIEW`. This
is recorded in `postpatch-runtime-route-assessment-v01.json`; it is an offline
re-evaluation of the saved server responses, **not another live model call**.
The exact-overlap route is covered by a `DiaryService` integration test. It does
not relabel the model's `UNSUPPORTED` result as `MIXED`, and its conservative
text-match heuristic does not cover paraphrased evidence.

## Interpretation and next step

The server probe continues to support the narrow conclusion that this model
handles the clear `SUPPORTED`, `SUBJECTIVE`, and `UNSUPPORTED` examples in this
small fixture. It still fails the target mixed-claim classification. The
runtime now catches this exact verbatim-overlap case and safely defers it to a
human, but the broader mixed boundary is **not established as reliable**. Keep
the claim gate rehearsal-only; collect human-labeled boundary cases and test
paraphrases before treating prompt changes or post-training as justified.

This eight-claim, one-model probe is diagnostic only. It is not an end-to-end
diary rehearsal, a human calibration result, or production-reliability
evidence.

## Verification

- Full local suite: **366 passed**.
- Focused diary/reviewer boundary tests: **89 passed**.
- Python source compilation and `git diff --check`: passed.
