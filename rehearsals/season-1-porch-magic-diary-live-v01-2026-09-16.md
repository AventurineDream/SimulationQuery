# Porch MAGIC diary workflow — live validation v01

**Date:** 2026-09-16  
**Status:** The diary pipeline passed its mechanical and privacy gate; diary prose remains
human-review-only until causal-fidelity checks are added.  
**Models:** Orchestrator `qwen3:30b-instruct`; actors `gpt-oss:20b` via the configured Ollama
server at `10.0.0.103:11434`.

## Hypothesis

If the accepted two-round Porch MAGIC rehearsal is followed by one real private diary opportunity
for each actor, the runtime should create exactly four private diary records, close the day, keep
the diary bodies out of scene prompts, and preserve the existing MAGIC and no-cheetah-turn
invariants.

## Method

This was an isolated follow-up to the accepted no-diary scene. The scene kept the same locked
opening, two rounds, eight family-turn limit, safety validators, and runtime-owned MAGIC result
boundary. The only intended scene-level variable was the addition of the end-of-day private diary
workflow. The forced branch was a setback: `2d6 [2,3] + Intellect modifier 1 + situational
modifier 0 = 6`.

Each of Mara, Eli, Sage, and Rory received the final immediate diary slot. The diary bodies were
written to the private audit archive and omitted from the JSON receipt. The branch was resumed
after two earlier infrastructure/model interruptions; the final diary phase therefore validates
the completed workflow, but is not a clean fresh-run A/B comparison of the renderer fix.

## Result

| Check | Result |
|---|---|
| Scene completion | **PASS** — `turn_limit`, 8 family turns |
| MAGIC roll | **PASS** — one durable setback roll, total 6 |
| Runtime adjudication and visible consequence | **PASS** |
| Cheetah turns | **PASS** — 0; cheetah remains director-narrated |
| Diary records | **PASS** — 4, all `WRITTEN`, slot 1 |
| Diary word counts | **PASS** — Mara 441, Eli 470, Sage 423, Rory 417 |
| Day closure | **PASS** — `PRIVATE_COMPLETE` |
| Private artifact placement | **PASS** |
| Diary body leaked into scene prompts | **PASS** — no leakage detected |
| Resume idempotence | **PASS** — exactly 4 diary rows after resume |

The durable report also preserves the earlier failed attempts rather than erasing them. They are
categorized separately as actor-output, director-plan, and director-render failures; the final
diary category is empty. The renderer envelope limit was raised for the internal compiled beat
while the raw director-render limit remained bounded. That infrastructure correction was required
to reach the diary phase.

## Qualitative review

The mechanical gate is not yet a content-quality gate. A first-person read of the four private
entries found useful character texture, but also likely violations of the diary contract:

- Eli, Mara, and Rory add inferred timing, operator actions, hidden objects, or reordered events
  beyond the accepted scene evidence.
- Sage explicitly describes Rory's private motive and abandonment fear, which is another
  character's inner state and should not be authorable from Sage's diary.
- Rory similarly speculates about Mara's hidden thoughts and a Sage/Mara partnership pressure not
  established in the accepted scene.

These entries remain private and are not being fed back into directing or publication. The report
now labels this distinction as `status=PASS` for the mechanical pipeline and
`quality_status=HUMAN_REVIEW_REQUIRED` for the prose.

## Decision

The private diary plumbing is reliable enough for a second controlled diary branch. Before diary
entries are allowed to update next-day context, add a diary-specific review contract that records
or rejects at least:

1. invented events or time jumps;
2. another character's unobserved private thoughts, motives, or reactions; and
3. causal claims that contradict the accepted turn order.

Keep those findings separate from word-count, safety, privacy, and model-output failures. Then run
matched clean-success, costly-success, and setback diary branches to measure whether diaries
preserve outcome variance without becoming a new source of unsupported canon.

## Evidence

- [live JSON receipt](../.rehearsal-data/season-1-porch-magic-diary-v02-setback-20260916/state/magic-diary-rehearsal-report.json)
- [preserved diary rehearsal root](../.rehearsal-data/season-1-porch-magic-diary-v02-setback-20260916/)
- [earlier interrupted diary branch](../.rehearsal-data/season-1-porch-magic-diary-v01-costly-20260916/)
