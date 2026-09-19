# Porch MAGIC adjudication boundary — forbidden-language retry validation v03

**Date:** 2026-09-16  
**Models:** Orchestrator `qwen3:30b-instruct`; actors `gpt-oss:20b` via the configured Ollama
server at `10.0.0.103:11434`.  
**Run shape:** Fresh isolated two-round branches, eight family turns maximum, no diaries, no
cheetah turn, and one forced first-roll tier per branch.

## Change under test

The retry now receives the exact forbidden MAGIC result or attempt terms found in the rejected
content. It is told not to quote those terms, their inflections, or close medical synonyms, and to
rewrite only the affected content in observation-only language. The one-retry and fail-closed
behavior remain unchanged.

## Live evidence

| Root | Branch | Result | Relevant terminal evidence |
|---|---|---|---|
| v03 setback | setback | **PASS** | Roll `2d6 [2,3] +1 = 6`; director retry accepted; runtime setback adjudication persisted and compiled |
| v03 costly | costly success | inconclusive | Actor-side retry repeated `sprain`/`fracture` before the roll; no MAGIC roll was recorded |
| v03 clean | clean success | inconclusive | Roll `2d6 [4,5] +1 = 10`; later renderer failed on an overlong envelope, outside the forbidden-language retry |
| v04 costly | costly success | inconclusive | Mara reached an accepted roll, but Rory later produced an invalid actor output before the run completed |

The v03 setback branch is the cleanest live confirmation of the director-side retry: the initial
post-roll plan used an unsafe term, the correction received the explicit offending-term list, and
the corrected observation-only consequence was accepted and rendered. It also retained zero diary
entries and zero cheetah turns.

The v03 costly failure motivated the actor-side retry update. Its rejected Mara correction repeated
the unsafe terms, demonstrating that the same explicit-term treatment was needed before the roll as
well. The v04 targeted rerun got past Mara and recorded the expected costly-success roll, but its
overall branch ended on an unrelated Rory actor-output failure, so it is not a full end-to-end
reliability pass.

## Interpretation

**Supported:** explicit offending-term guidance improves the bounded retry path in at least one
live director branch, and the local actor/director correction contracts are covered by tests. The
safety guard continues to fail closed when the model does not repair the content.

**Unresolved:** live success rates across all tiers remain confounded by ordinary model-output
variance: pre-roll actor corrections, render length, and malformed actor output each stopped a
branch independently. These should remain separate metrics from forbidden-language retry success.

## Decision

Keep the retry change. Do not widen the validator or add automatic prose sanitization, since either
would risk silently changing player/character meaning. Diaries remain a separate next experiment
after the current live branch reliability is accepted or another bounded retry change is chosen.

## Evidence roots

- [v03 setback](../.rehearsal-data/season-1-porch-magic-adjudication-v03-20260916-setback-server/)
- [v03 costly](../.rehearsal-data/season-1-porch-magic-adjudication-v03-20260916-costly-server/)
- [v03 clean](../.rehearsal-data/season-1-porch-magic-adjudication-v03-20260916-clean-server/)
- [v04 costly](../.rehearsal-data/season-1-porch-magic-adjudication-v04-20260916-costly-server/)
