# Porch MAGIC adjudication boundary — live validation v01

**Date:** 2026-09-16  
**Models:** Orchestrator `qwen3:30b-instruct`; actors `gpt-oss:20b` via the configured Ollama
server at `10.0.0.103:11434`.  
**Run shape:** Three fresh two-round branches, eight family turns maximum, no diaries, no cheetah
turn, and one forced first-roll tier per branch.

## Result

The runtime boundary passed the dice portion in all three branches. Each branch accepted Mara's
safe-distance action and recorded exactly one roll with the expected total and tier. The live
director consequence contract did not pass within its two plan attempts in any branch.

| Branch | Forced roll | Safe action | Accepted post-roll plan | Terminal validator pattern |
|---|---:|---|---:|---|
| setback | `2d6 [2,3] +1 = 6` | yes | 0 | missing detail; then detail paraphrased outside `magic_effect_detail` |
| costly success | `2d6 [3,4] +1 = 8` | yes | 0 | missing detail/cost; then detail paraphrased outside `magic_effect_detail` |
| clean success | `2d6 [4,5] +1 = 10` | yes | 0 | missing detail; then detail paraphrased outside `magic_effect_detail` |

The accepted opening plan in all three branches matched the locked challenge, criteria, modifier,
and next actor. No director-authored result/status/answer fields were needed or accepted. The
runtime derived the pending adjudication from each validated roll; the branches stopped before a
`DirectorPlanAccepted` event could persist it alongside a consequence plan.

## Interpretation

**Supported:** mechanical separation. The server model can produce an acceptable opening, the actor
can choose a MAGIC attribute, the runtime can force and record each tier, and the roll data matches
the formula. The new runtime-owned adjudication therefore behaves as intended through the point
where the director consequence is requested.

**Not supported:** live end-to-end consequence completion. The same failure appeared across all
three tiers. The model usually supplied a plausible `magic_effect_detail` on its correction, but
used a semantically equivalent sentence in pressure or canon instead of repeating the exact detail.
The strict deterministic integration check consequently rejected every branch.

## Decision for the next iteration

Do not introduce diary entries yet. The next bounded change should reduce the brittle cross-field
copy requirement while preserving deterministic tier validation. The safest candidate is for the
runtime to compile the accepted `magic_effect_detail` directly into the visible beat and validate
that the director's other fields do not contradict the tier, rather than requiring exact prose
duplication in pressure, choices, or canon. Re-run the same three forced branches before adding
any new context source.

## Evidence roots

- [setback](../.rehearsal-data/season-1-porch-magic-adjudication-v01-20260916-setback-server/)
- [costly success](../.rehearsal-data/season-1-porch-magic-adjudication-v01-20260916-costly-server/)
- [clean success](../.rehearsal-data/season-1-porch-magic-adjudication-v01-20260916-clean-server/)

The initial unsandboxed attempt is preserved separately under
`season-1-porch-magic-adjudication-v01-20260916-setback`; it failed because the sandbox could not
reach the configured endpoint and produced no scene turn or roll.
