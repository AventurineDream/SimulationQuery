# Porch MAGIC dice — live tier rehearsal follow-up

**Date:** 2026-09-15

**Status:** Dice recording and fail-closed checks are promising; outcome narration is not reliable enough to begin diary rehearsals.

**Models:** Orchestrator `qwen3:30b-instruct`; family actors `gpt-oss:20b` on the local Ollama server.

**Comparison:** Follow-up to [the first live tier review](season-1-porch-magic-dice-live-tier-review-2026-09-15.md).

## Hypotheses

1. **Dice integrity:** Each accepted MAGIC action records the selected attribute, both d6 faces, modifiers, total, and matching tier exactly once; invalid actions do not receive a roll.
2. **Outcome integrity:** With the same unresolved challenge, setback, costly success, and clean success produce distinct, coherent consequences across the plan and visible narration.
3. **Character consistency:** Mara chooses and describes an approach consistent with her safari-guide experience and established personality, without claiming knowledge she has not earned.

## Controlled setup

- Three isolated server-backed data roots, one for each forced outcome; same models and model configuration.
- Exact opening plan locked across branches: docile cheetah on the porch, favoring its raised right hind paw; cause and severity explicitly unknown; Mara is next.
- Same challenge: “Can Mara identify what the cheetah's posture reveals about its leg injury, without approaching or touching it?”
- Mara uses Intellect 4, giving a +1 MAGIC modifier; situational modifier is 0. Formula: `2d6 + (MAGIC score - 3) + situational modifier`.
- Target totals: setback 6, costly success 8, clean success 10. These were forced branch targets, not random samples; this rehearsal does not measure tier probabilities.
- Two rounds / eight family turns where a branch completed; no diary entries and no cheetah turns.

## Results

| Target | Recorded dice and math | Server result | Automated status | Human narrative review |
|---|---|---|---|---|
| Setback | `2 + 3 + 1 + 0 = 6` | Setback; 8 turns; one roll | PASS | Visible beat reports a partial limp and new opening, but the hidden adjudication says the setback reveals a likely sprain. The failed inference is therefore ambiguous and the private plan overstates what the evidence establishes. |
| Costly success | Target total 8; **no roll recorded** | Interrupted after 3 accepted family turns | FAIL | Mara's initial answer and her one correction both included premature injury diagnoses and were rejected. The director then proposed an outcome-specific plan despite there being no accepted action or roll; both plan attempts were rejected. No costly-success behavior was tested. |
| Clean success | `4 + 5 + 1 + 0 = 10` | Clean success; 8 turns; one roll | PASS | The hidden adjudication claims a strained tendon or partial ligament tear, while the visible MAGIC result is about Rory finding a sealed hidden porch panel—not Mara's posture-reading challenge. Formal success acknowledgement passes, but the consequence does not faithfully show the rolled result. |

The exact opening remained locked and unresolved in all three reports. The actor guard rejected a premature diagnosis in all three first Mara attempts. A correction produced an acceptable action in the setback and clean-success branches; the costly branch's correction also failed and correctly received no roll. The director's first setup plan was rejected and corrected in all three runs. In both completed branches, the first post-roll plan omitted the required tier acknowledgement and its correction passed. These checks are useful: they prevent several invalid states from being silently accepted, but retries are doing substantial work.

## Hypothesis assessment

**1. Dice integrity — supported for accepted actions, with limited evidence.** Both completed branches logged exactly one correct roll with the expected faces, modifier, total, and tier. The costly branch logged no roll after its action failed validation. That is the desired fail-closed behavior. This is only two recorded rolls, not broad reliability evidence.

**2. Outcome integrity — not supported.** The structured outcome fields and visible result line passed their automated checks for the two completed runs, but both private plans contradict or fail to substantiate the visible result. The costly branch never reached a valid check. A schema-valid acknowledgement is not yet evidence that the tier changed the fiction in the intended way.

**3. Character consistency — inconclusive, with a recurring knowledge-boundary failure.** Mara's corrected action—observing from the kitchen doorway—fits both the safety constraint and her field experience. However, all three first actor drafts tried to diagnose the injury before the roll; the costly correction did too. The guard recovered in two branches and blocked the third. Since every target used Intellect and the sample contains one Mara action per branch, it does not test whether character-specific strengths/personality meaningfully shape varied choices.

## Interpretation and recommendation

Compared with v01, the shared opening is now controlled, and the pre-roll validator prevented a diagnosis from being committed in the two completed branches. The dice ledger behaves correctly when an action is accepted. The key remaining risk is downstream: a director can acknowledge a tier in structured fields while private adjudication, canon updates, or the visible scene contradict its actual effect. The clean-success example is particularly clear: the roll is for reading the cheetah's posture, but the public result line celebrates an unrelated panel discovery.

**Recommendation: do not start diary-entry rehearsals yet.** First make outcome adjudication answer the checked challenge directly and validate the whole accepted plan—not only `magic_result_ack`, `magic_goal_status`, and the visible result line. For each tier, require a consistent relationship among adjudication, canon/state changes, pressure, and the visible effect:

- **Setback:** the attempted interpretation remains unresolved or wrong; any new clue or complication must not quietly grant the answer.
- **Costly success:** the stated challenge is achieved, and a concrete, relevant cost is both recorded and shown.
- **Clean success:** the stated challenge is achieved without an added cost; unrelated discoveries must remain separate from the MAGIC effect.

Then rerun the same three locked branches. If those pass manual and automated review, diary entries become a useful next stressor rather than a confound in already-unclear core mechanics.

## Reproducible evidence

- Setback report (private evidence: `../.rehearsal-data/season-1-porch-magic-dice-v03-setback-20260915/state/magic-dice-rehearsal-report.json`)
- Costly-success report (private evidence: `../.rehearsal-data/season-1-porch-magic-dice-v03-costly-20260915/state/magic-dice-rehearsal-report.json`)
- Clean-success report (private evidence: `../.rehearsal-data/season-1-porch-magic-dice-v03-clean-20260915/state/magic-dice-rehearsal-report.json`)
- Earlier attempts remain in separate v02 data roots and are excluded from these three controlled results.

## Verification

The implementation test run after the rehearsal-guard changes passed **326 tests, with 1 date-sensitive scheduled-resume test deselected**; `compileall` and `git diff --check` passed. The excluded test has a fixture pinned to September 6 while the workspace date is September 15. This review file adds no code changes.

Private evidence references are original provenance paths, not public downloads.
See [project organization](../docs/PROJECT_ORGANIZATION.md) for the storage boundary.
