# Porch MAGIC dice — live tier rehearsal review

**Date:** 2026-09-15  
**Status:** Mechanics and audit path passed; narrative tier comparison is inconclusive.  
**Models:** Orchestrator `qwen3:30b-instruct`; actors `gpt-oss:20b`.

## Hypotheses

1. The server records the selected MAGIC attribute, both d6 faces, modifiers, total, and matching outcome exactly once.
2. A clean success achieves the challenge without a new cost; a costly success achieves it with a meaningful, visible cost; a setback falls short while changing the situation through relevant information, a complication, or an opening.
3. Mara remains a consistent character while choosing an attribute relevant to her safari-guide expertise.

## Shared controls

- Actor: Mara Bell; Intellect 4 (attribute modifier +1).
- Challenge: “Can Mara identify what the cheetah's posture reveals about its leg injury, without approaching or touching it?”
- Situational modifier: 0.
- Two rounds, eight family turns, one MAGIC roll, no diary entries, no cheetah turns.
- Same actor/orchestrator models and rehearsal configuration in each fresh data root.
- Dice were deliberately forced to hit each tier. This tests recording and downstream adjudication, not random-roll probabilities.

## Results

| Target | Faces | Math | Logged outcome | Automated run | Follow-through review |
|---|---:|---:|---|---|---|
| Setback | 2, 3 | 5 + 1 + 0 = 6 | Setback | PASS | Next plan acknowledged the setback and surfaced a hidden stabilizer plus a new animal-safety pressure. Mara's action nevertheless states a sprain/ligament-strain conclusion confidently, so the failure of her inference is not clear. |
| Costly success | 3, 4 | 7 + 1 + 0 = 8 | Costly success | PASS | The action identifies a right-hind-leg limp. The next plan names “mental fatigue” as a cost, but that cost is not made visible; the narrated beat instead shifts the cheetah under treehouse shade and reveals an unrelated key. The plan's adjudication also ends mid-sentence (“Eli's makeshift stre…”). Costly-success semantics are weakly demonstrated. |
| Clean success | 4, 5 | 9 + 1 + 0 = 10 | Clean success | PASS | Mara identifies the left hind leg; the opening plan and follow-up keep that side consistent and the next plan acknowledges clean success. Wildlife rescue is confirmed for 90 minutes, creating future pressure not clearly caused by the roll. This is the clearest tier, though the actor still describes the diagnosis as “fractured or sprained.” |

Every final report records the exact challenge and modifier, exactly one roll, eight family turns, zero diaries, zero cheetah turns, and a next-plan acknowledgement of the forced result. “PASS” is the harness result; it does not certify that the narrative consequence is clear or satisfying.

## Important validity limitation

The challenge and mechanics were held fixed, but the director did **not** produce identical opening states. More importantly, all three accepted opening plans added a canon update that partially answered the challenge before Mara rolled:

- Setback root: “Mara identifies the injury as a strained or sprained right hind limb.”
- Costly root: “Mara identifies limp origin as right rear limb injury.”
- Clean root: “Mara identifies limping on left hind leg.”

The costly run also began with the cheetah already under treehouse shade and not accessible, unlike the other openings. These differences confound a causal comparison of outcome tiers. Treat the table as evidence that the dice/audit path works and that the models can produce distinct branches—not as a controlled demonstration that the three narrative outcomes are reliably differentiated.

The first director plan required a strict setup correction in all three runs. The first post-roll plan also omitted its required result acknowledgement in all three; the validator rejected each and the correction path accepted the acknowledgement. This makes the correction gate important, but indicates first-pass instruction-following is not yet reliable.

## Reproducible reports

- [Setback report](../.rehearsal-data/season-1-porch-magic-dice-v01-setback-parserretry2-20260915/state/magic-dice-rehearsal-report.json)
- [Costly-success report](../.rehearsal-data/season-1-porch-magic-dice-v01-costly-20260915/state/magic-dice-rehearsal-report.json)
- [Clean-success report](../.rehearsal-data/season-1-porch-magic-dice-v01-clean-20260915/state/magic-dice-rehearsal-report.json)

Earlier failed and invalid setup attempts remain preserved in their separate `.rehearsal-data/` roots and are not counted in the three tier results.

## Verification and next experiment

- Focused MAGIC/parser/scene suite passed during implementation; full suite excluding the unrelated date-sensitive scheduled-resume case: **317 passed, 1 deselected**.
- `compileall` passed; `git diff --check` passed.
- The full run had 317 passes and one failure in `test_explicit_scheduled_resume_reopens_only_the_stopped_run`: its fixture expects a September 6 slot to remain `SCHEDULED`, but the workspace date is September 15 and the resumed run completes. No unrelated scheduling code was changed.
- Before diary rehearsals, freeze the opening beat and add a validator that rejects any opening plan that resolves or attributes an injury diagnosis before the pending roll. Then repeat the three outcomes and require an explicit, visible cost for costly success and an explicit failed inference for setback.
