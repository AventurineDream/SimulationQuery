# Porch MAGIC action/result boundary — 2026-09-21

This is a fresh isolated live rehearsal after the retry-cleanup failure. It
implements and tests a narrower contract: an actor's attempted method is a
structured field, the runtime rolls that field, and shared actor prose is
stored separately. An unanswered challenge also remains active after a
rejected turn or neutral interruption; only an accepted MAGIC attempt or an
explicit decline resolves it.

## Implementation

- `ActorTurnEnvelope` now requires `magic_method` whenever `magic_stat` is
  selected, and rejects a method without a stat.
- Tagged and native JSON actor responses support the separate method field,
  including the bounded inline-metadata repair used by local models.
- `MagicRollResolved` now records `action` as the structured method and keeps
  `actor_text` separately, with `attempt_contract: attempted_method_only`.
- Director review rejects a later plan that drops or changes an unresolved
  challenge's text, criteria, actor, or modifier.
- Neutral interruptions no longer count as challenge answers. An accepted
  actor turn with no stat is the explicit-decline path.

## Local verification

The focused parser, boundary, and scene tests passed (**154 tests**). The full
local suite passed (**390 tests**); Python compilation and `git diff --check`
also passed.

## Live rehearsal

Root:
[`season-1-porch-magic-action-result-20260921`](../.rehearsal-data/season-1-porch-magic-action-result-20260921/)

Receipt:
[`magic-dice-rehearsal-report.json`](../.rehearsal-data/season-1-porch-magic-action-result-20260921/state/magic-dice-rehearsal-report.json)

Conditions:

- Orchestrator: `qwen3:30b-instruct`.
- Actors: `gpt-oss:20b`.
- Two rounds, eight family turns, no diaries, no cheetah turn.
- One forced `setback` tier for the first MAGIC roll.

Result: **mechanical PASS**. The run completed `turn_limit` with 8/8 actor
turns, one roll, forced faces `[2, 3]`, Intellect score 4, total 6, and
`setback`. Runtime adjudication matched the roll and the next director beat
compiled the runtime-owned consequence. There were zero diaries and zero
cheetah turns. The first director plan and the second consequence plan each
needed one correction; both corrected plans were accepted.

The receipt confirms the new separation:

- `action`: `Observe weight distribution from the kitchen doorway`
- `actor_text`: persisted independently
- `attempt_contract`: `attempted_method_only`

## Quality boundary still open

This is not a prose-quality PASS. Mara's accepted actor text still contains a
pre-roll observational claim about the paw touching the ground, even though
the runtime did not use that prose for the roll. The setback plan also uses
pain/injury language in its director-supplied consequence fields. The receipt
therefore proves the mechanical action/result boundary and runtime ownership,
but not a fully clean semantic boundary for every visible sentence.

Next bounded test: add a separate review rule for pre-roll actor observations
and unsupported medical/result claims, then run one controlled comparison
without changing the dice or diary conditions. Do not treat this rehearsal as
evidence for diary quality, outcome variance, or production readiness.
