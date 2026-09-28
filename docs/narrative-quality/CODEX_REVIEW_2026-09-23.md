# Codex narrative and prose candidate

Status: **implemented locally; peer review and live prose validation pending**.
No live rehearsal, live model probe, production operation, or publication was run.

The creator commissioned independent Codex and Amaranth solutions, followed by
mutual review and a creator decision on the eventual PR. This is the Codex
candidate, not that combined PR or a claim of shipping readiness.

## Baseline and diagnosis

`codex`, `Amaranth`, and `main` initially pointed to `1531905`. The local checkout
also contained the existing September 18–21 diary, retry, and MAGIC fixes. Those
edits were retained as the working baseline. Its full offline suite passed
390 tests before this pass. They must not be attributed to this candidate when
comparing the two branches.

Source evidence: the [action/result review](../../rehearsals/season-1-porch-magic-action-result-boundary-2026-09-21.md),
the [retry review](../../rehearsals/season-1-porch-retry-cleanup-2026-09-20.md),
and read-only inspection of their saved scene artifacts. The latest accepted
scene still asserted pre-roll observations and unsupported pain/injury. Its
mechanical pass is not a prose pass.

Three structural problems were also visible directly in the code:

- Private planning labels and proposed choices were compiled into the scene.
  A setting keyword became a fabricated location prefix, including `At family:`.
- The renderer had to manufacture sensory atmosphere, without seeing the
  established scene. Functional nouns were treated as exhausted imagery,
  encouraging replacement props and needless novelty.
- The actor brief said every accepted actor line was a resolved move, conflicting
  with the explicit rule that claims and pre-roll observations cannot establish
  a challenge result. The diary writer's prohibition on inferred private states
  was also broader than the reviewer's allowance for clearly marked uncertainty.

## Implementation and tradeoffs

The two-pass director now writes complete state and pressure sentences. The
runtime joins them without planning labels or an invented location prefix.
The existing per-field limits remain 24 words, with 64 across state, pressure,
and the two choices; the prompt now agrees with those actual limits rather
than demanding telegraphic fragments. Actor turn and round limits are unchanged.

Choices remain exact in `DirectorPlanAccepted` and in each actor's new
`SHARED PLAY STATE` context. They are suggestions, distinct from performed
events, and survive replay from the accepted plan. A later single-pass beat
clears old suggestions. This deliberately removes the audience-visible menu
from shared narration. Review that presentation choice with Amaranth; a future
interface could show suggestions separately without making them diary evidence.

The prose pass receives an allowlisted set of visible beat fields and the
accepted scene, excluding the plan's private rationale, objective, clocks,
proposed choices, and any future private fields. It may return an empty
`narration` value when no detail adds anything. Missing, null, malformed, and
markup-containing responses still fail. Optional detail has a checked 35-word
limit and can receive the existing single correction.

Repeated nouns no longer reject a director plan. A six-word phrase overlap can
drop redundant optional detail while preserving the exact plan and raw output.
This is a narrow repetition check, not a semantic quality score. Puppeteering,
overlong detail, and malformed output cannot use that fallback. Complete beat
duplicates still fail the existing exact-repeat check. The older single-pass
path also stops rejecting ordinary nouns but retains its exact-repeat check.

Actor guidance emphasizes the immediate exchange, character-specific attention
and rhythm, disagreement, gestures, and stopping when the move lands. Every
actor sees the shared pending challenge and the latest runtime result. An
attempt, belief, or unsupported observation is explicitly not a discovery;
another actor cannot settle the pending question through incidental prose.
These are prompt improvements, not proof of semantic enforcement.

Diary guidance permits clearly marked interpretations and questions, focuses
on one or two personally significant moments, and discourages a scene recap
or obligatory lesson. Evidence references, privacy, reviewer decisions,
correction limits, and the rehearsal-only claim gate are unchanged. Performer
and fictional-character identities remain distinct.

The exact runtime MAGIC result, goal answer, and consequence remain readable
receipts. This candidate does not beautify a setback into success or change dice
math. Challenge narration no longer contains envelope instructions such as
`omit MAGIC_STAT`; those instructions remain in the actor prompt.

The standalone director-prompt probe uses the same prose composition helper and
marks its result `HUMAN_REVIEW_REQUIRED`. It was tested with scripted responses,
not executed against a model server. Prompt/context versions identify the new
contracts for future comparisons.

## Small composition example

This is an **authored synthetic fixture**, not newly generated model output.
It demonstrates formatting and information boundaries only.

Previous composition for the same plan, without optional atmosphere:

> At kitchen: Three knocks interrupt the argument at the kitchen door.
> Pressure: The caller can hear every word through the thin door.
> Choice A: Answer the door with the coat still on.
> Choice B: Hide the coat before answering.

Current shared prose:

> Three knocks interrupt the argument at the kitchen door.
> The caller can hear every word through the thin door.

The actor still receives both suggestions exactly. Neither answering the door
nor hiding the coat has happened merely because it was offered. Private
information about why the caller recognizes the coat never reaches the renderer.

## Review map

| Area | Implementation | Verification |
| --- | --- | --- |
| Character and diary voice; planning and rendering briefs | `src/improv_troupe/llm/context.py` | Existing context-boundary checks plus renderer allowlist test |
| Prose composition; shared choices; replay; prompt versions | `src/improv_troupe/application/scene_runner.py` | Scripted scene, correction, replay, and MAGIC regression tests |
| Optional detail and markup boundary | `src/improv_troupe/llm/structured.py` | Empty versus missing/null/markup parser cases |
| Phrase reuse rather than noun novelty | `src/improv_troupe/llm/safety.py` | Phrase versus noun checks and first/corrected render provenance |
| Diary prompt provenance | `src/improv_troupe/application/diaries.py` | Existing private diary and claim-gate tests |
| Standalone probe parity | `scripts/probe_director_prompt.py` | Scripted two-call probe; no network |
| New regression cases | `tests/test_narrative_quality.py` | Explicitly mechanical fixtures, not prose ratings |

## Verification and remaining gate

Final local verification is recorded in `IMPLEMENTATION_STATUS.md`. The
regressions cover all actors receiving choices, replay equivalence, clearing
stale choices, unchanged stored prose, renderer privacy, empty-detail parsing,
bounded correction, phrase reuse, and exact MAGIC results for all three tiers.

**Unresolved:** source-faithful pre-roll observations, unsupported injury claims,
distinct live character voices, sustained causal progression, and diary prose
quality still need human review of newly generated text. No deterministic check
here can establish those properties. The existing diary semantic gate is still
unproven. This pass adds no reviewer model calls or calibration claims.

For mutual review, compare causal continuity, distinct voices, responsive
dialogue, economical concrete prose, actor agency, and diary perspective.
Treat invented outcomes, contradicted rolls, private-state leakage, and authored
peer reactions as defects rather than stylistic preferences. Judge both whole
scenes and individual sentences; passing schema checks alone cannot select a
winner. Keep model bindings, world, turn budget, roll conditions, and starting
local fixes matched in a later comparison.

Next action: review both implementations and agree on the candidate or hybrid
before preparing the actual PR. A live comparison remains explicitly gated on
the creator's further prompting.
