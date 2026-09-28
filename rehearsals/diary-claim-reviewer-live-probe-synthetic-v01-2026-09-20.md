# Diary claim reviewer live probe — synthetic fixture — v01

**Date:** 2026-09-20  
**Status:** `FAIL` — narrow reviewer probe; not an end-to-end rehearsal  
**Model:** `qwen3:30b-instruct`, the reviewer/Orchestrator model used in v09  
**Private evidence:** `.rehearsal-data/diary-claim-probe-synthetic-v01-20260920/private/`

## Scope

The probe made two initial structured reviewer calls using the production prompt
builder, native response schema, and diary-review parser. After the mixed-only
response failed envelope validation, it made one direct correction call using
the app's exact correction instruction and the same fixture. It did not generate
diary entries, call the diary-writing model, or touch a rehearsal database.

The first plan was to use the saved v09 scene evidence, but the approval layer
blocked sending that private rehearsal material to the model server. The probe
was therefore rerun with a wholly synthetic library scene and synthetic claims;
no saved diary or scene text was sent. Expected labels are researcher-authored
fixture expectations, not a new human-labeling pass. `MIXED` is a model-side
routing expectation, not a human calibration label.

The fixture contained eight claims over one fixed three-item evidence context:
two `SUPPORTED`, three `SUBJECTIVE`, two `UNSUPPORTED`, and one `MIXED`. The
seven non-mixed claims were reviewed together; the mixed claim was isolated in
its own request and received one correction attempt.

## Results

| Check | Observed | Assessment |
|---|---|---|
| Seven-claim classification batch | 7/7 claim labels matched expectations; both required support citations were present | Claim-level pass for these clear examples |
| Seven-claim envelope decision | Model returned `ACCEPT` despite two `UNSUPPORTED` audits | Inconsistent model envelope; current runtime code would override this to `REJECTED` (code-path inference, not a service integration run) |
| Isolated mixed claim | Model labeled it `UNSUPPORTED`, not `MIXED`, and returned `REJECT`, not `MANUAL_REVIEW` | Target boundary failed |
| Single correction attempt | Repeated `UNSUPPORTED` and `REJECT`; did not change the classification or decision | Correction did not recover |
| Mixed response parsing | Both responses were syntactically valid JSON, but the app parser rejected them because `REJECT` had no categorized top-level finding | The app's correction path would leave the diary unavailable/private (code-path inference, not a service integration run) |

Across raw claim labels, agreement was **7/8 (87.5%)**. The only mismatch was
the mixed claim being collapsed into `UNSUPPORTED`, including after the single
correction. All three requests used native structured output; the seven-claim
response took about 65 seconds, the initial mixed-only response about 11
seconds, and its correction about 61 seconds.

| Expected fixture class | Model `SUPPORTED` | Model `SUBJECTIVE` | Model `UNSUPPORTED` | Model `MIXED` |
|---|---:|---:|---:|---:|
| `SUPPORTED` | 2 | 0 | 0 | 0 |
| `SUBJECTIVE` | 0 | 3 | 0 | 0 |
| `UNSUPPORTED` | 0 | 0 | 2 | 0 |
| `MIXED` | 0 | 0 | 1 | 0 |

The matrix records the raw claim tag from the mixed responses even though the
application envelope parser rejected them. A machine-readable aggregate
accompanies the raw prompt/response records in the private evidence directory.

## Interpretation and next step

The probe supports the narrow hypothesis that this model can distinguish clear
supported, subjective, and unsupported claims in a small controlled fixture.
It refutes the hypothesis that the current prompt/model reliably recognizes a
supported observation combined with an unsupported assertion and routes it to
manual review. The top-level `ACCEPT` inconsistency in the first call also
shows why claim audits must be considered together with runtime-owned
adjudication.

Keep the claim gate rehearsal-only. The next useful change is to make the mixed
classification and manual-review contract more reliable, then replay this same
synthetic fixture before another full rehearsal. This eight-claim, one-model
probe is diagnostic only; it is not evidence of production reliability, a
human-labeled calibration result, or a reason to begin post-training.
