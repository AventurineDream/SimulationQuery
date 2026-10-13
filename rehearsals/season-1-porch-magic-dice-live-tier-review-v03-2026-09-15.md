# Porch MAGIC dice — live tier rehearsal review v03

**Date:** 2026-09-15  
**Status:** The fail-closed guards are working; the configured server pair is not yet reliable enough for a controlled outcome-tier or diary rehearsal.  
**Models:** Orchestrator `qwen3:30b-instruct`; family actors `gpt-oss:20b` on the local Ollama server.

## Objective

After the earlier live runs exposed unsupported MAGIC consequences, the rehearsal contract was tightened and the same three forced-outcome branches were rerun against the server in fresh data roots. The question was whether the system could now carry one precommitted challenge through an accepted actor action, a recorded roll, and a coherent visible consequence.

## Hypotheses

1. **Dice integrity:** An accepted MAGIC action records the selected attribute, both d6 faces, the character and situational modifiers, the total, and the matching tier exactly once; rejected actions do not receive a roll.
2. **Outcome integrity:** Setback, costly success, and clean success remain distinct and coherent across adjudication, state change, canon, pressure, choices, and the compiled visible beat.
3. **Character and safety consistency:** Mara uses a safari-guide-appropriate approach while observing the cheetah from a safe distance, without asserting an injury diagnosis before the roll.

## Controls

- Exact challenge: “Can Mara identify what the cheetah's posture reveals about its leg injury, without approaching or touching it?”
- Pre-roll success criterion: “Mara confirms the cheetah keeps weight off its raised right hind paw while stepping.”
- Mara's Intellect score: 4; MAGIC attribute modifier: `+1`.
- Situational modifier: `0`.
- Formula: `2d6 + (MAGIC score - 3) + situational modifier`.
- Forced target totals: setback `6`, costly success `8`, clean success `10`. These are branch controls, not probability samples.
- Two rounds / eight family turns; no diary entries; the cheetah has no turn.
- Each branch used a fresh isolated data root and the same model configuration. The opening plan was required to leave the challenge unresolved and put Mara next.

## Implementation under test

- Added a required pre-roll `magic_success_criteria` field.
- Made post-roll outcome acknowledgement and follow-through fields explicit, nullable fields in the director envelope.
- Added fail-closed validation for tier semantics, exact goal-answer copying, cost/opening integration, and unsupported result language across every director-plan field.
- Added a correction directive that takes precedence when a pending outcome exists and states the required answer, status, and consequence relationship.
- Preserved the exact MAGIC result in the game state and emitted it in the compiled director beat.
- Expanded the actor pre-roll guard to catch common injury diagnoses and injury-anatomy claims.

## Fresh live results

| Branch | Accepted family turns | Roll | Run status | Failure point | Harness result |
|---|---:|---|---|---|---|
| Setback (`v09-setback`) | 3 | None | Interrupted after turn 3 | Mara's initial action and one correction both named an injury before a roll; the next director plan then acknowledged a nonexistent roll and both plan attempts were rejected. | FAIL |
| Costly success (`v09-costly`) | 3 | None | Interrupted after turn 3 | Same actor failure. Eli, Sage, and Rory were accepted; no accepted MAGIC action remained, so no dice were rolled. | FAIL |
| Clean success (`v09-clean`) | 3 | None | Interrupted after turn 3 | Same actor failure. The director's round-two plan twice attempted to acknowledge a result when no roll existed and was rejected. | FAIL |

The three v09 reports all record `director_plan_contract_invalid`, zero rolls, `pre_roll_diagnostic_terms_absent = false`, `outcome_contract_valid = false`, and `whole_plan_coherent = false`. This is a valid fail-closed outcome, but it is not evidence that the three result tiers are narratively differentiated.

## Iteration history

The preceding controlled attempts are retained rather than overwritten:

- **v03:** setback and clean branches recorded one roll and completed eight turns, but both had `whole_plan_coherent = false`; the costly branch stopped before a roll.
- **v04–v08:** successive setback-only attempts improved the structured contract, but each still stopped after one roll when the corrected post-roll plan failed a different coherence requirement: acknowledgement, semantic bundle, canon copying, detail integration, or visible brevity.
- **v09:** prompt and schema changes made the outcome contract stricter, but all three branches encountered the actor pre-roll failure before reaching dice.

The apparent improvement in v08 was therefore not enough to justify diary testing: it was a near-miss on a single setback branch, not a replicated tier result.

## Hypothesis assessment

**1. Dice integrity — supported in the earlier accepted-action cases, not exercised in v09.** The v03 completed branches logged exactly one forced roll with the expected modifier and total; v04–v08 also show one roll before their later director-plan failure. In v09, the guard correctly refused to mint a roll after two invalid actor attempts. This supports the ledger's fail-closed behavior, but not broad random-roll reliability.

**2. Outcome integrity — not supported.** The v09 branches never reached an outcome. The prior v03–v08 records show why the stricter checks were needed: a structured tier acknowledgement could coexist with an unrelated visible discovery, an unsupported hidden diagnosis, an omitted canon answer, or a cost that was not actually shown. The validator is catching these contradictions instead of silently canonizing them; the model is not consistently producing an acceptable plan within one correction.

**3. Character and safety consistency — not supported for autonomous use.** Mara's established expertise and the safe-distance constraint are present in the setup, but all three fresh branches independently produced a premature injury diagnosis, and all three corrections repeated it. This is a repeatable instruction-following failure in the actor model, not a dice failure.

## Recommendation

Do not start diary-entry rehearsals yet. Diary state would add another source of context and continuity pressure before the core loop can reliably get past the first MAGIC check and preserve its consequence.

The next engineering decision should be one of these bounded options:

1. **Recommended:** move mechanical adjudication out of free-form director prose. Let the runtime deterministically apply the recorded tier and require the director only to supply short, observable consequence fields that are validated against it.
2. Keep the current model-led flow, but give the actor a narrowly constrained action format and a deterministic rewrite/template for rejected pre-roll MAGIC attempts.
3. Test a stronger or differently prompted actor model before changing the mechanics, using the same locked opening and the same three branches.

Whichever option is chosen, the next gate should be a small controlled batch that requires: an accepted Mara action, exactly one roll, explicit pre-roll criteria, exact answer persistence, a visible costly-success cost or setback opening, and no unsupported diagnosis. Only after that passes should diary entries be introduced as a separate variable.

## Verification

- Local suite excluding the unrelated date-sensitive scheduled-resume case: **339 passed, 1 deselected**.
- `compileall`: passed.
- `git diff --check`: passed.
- The excluded test is `test_explicit_scheduled_resume_reopens_only_the_stopped_run`; its fixture is pinned to an earlier date while the workspace date is 2026-09-15. No scheduling code was changed for this rehearsal.

## Reproducible evidence

- Fresh setback report (private evidence: `../.rehearsal-data/season-1-porch-magic-dice-v09-setback-20260915/state/magic-dice-rehearsal-report.json`)
- Fresh costly-success report (private evidence: `../.rehearsal-data/season-1-porch-magic-dice-v09-costly-20260915/state/magic-dice-rehearsal-report.json`)
- Fresh clean-success report (private evidence: `../.rehearsal-data/season-1-porch-magic-dice-v09-clean-20260915/state/magic-dice-rehearsal-report.json`)
- [Previous live review](season-1-porch-magic-dice-live-tier-review-v02-2026-09-15.md)
- Earlier `v03`–`v08` roots remain preserved under `.rehearsal-data/`.

Private evidence references are original provenance paths, not public downloads.
See [project organization](../docs/PROJECT_ORGANIZATION.md) for the storage boundary.
