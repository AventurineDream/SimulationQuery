# Private S01 Day 2 model and system review — 2026-08-24

> Private operational artifact. Model identities, private diary attempts, role
> sheets, prompts, and this report are excluded from public season output.

## Evidence boundary

This review uses the creator-provided Day 2 End-of-day export for Runs 4–6,
the four supplied diary outputs, the S01 model manifest, and the current local
checkout. The live Linux database was not queried during this documentation
pass. The export labels all three runs `COMPLETED`, but that label alone does not
establish how each run completed or whether every expected turn was present.

The exact live private role sheets were not included in the review material.
Role observations below therefore distinguish visible character behavior from
the original creator-reviewed cast concepts.

## Creator commitment and open possibilities

The creator decided to end S01 rather than continue the seven-day season and to
preserve it as a private pilot record. Ending the live season remains a separate
creator-approved operational action; this documentation update does not execute
it and does not authorize publication.

The committed overhaul sequence is:

1. rebuild the dashboard as an accurate operator surface;
2. manually perform and document every pre-season operator step;
3. run one isolated day containing three scenes, four diary opportunities, day
   closure, and next-day planning;
4. use that evidence to decide what should become reusable operator and model
   templates.

Trying one or two model swaps, including 12B-class candidates, remains an open
possibility. No replacement assignment has been approved.

## Overall Day 2 assessment

Day 2 is creatively promising and operationally unacceptable as a production
run. The central mystery—whether the caldera is reacting to the crew as an
experiment—has real dramatic potential. The diaries contain distinct interior
voices, sensory memory, private suspicion, humor, and relationship awareness.

The shared scenes nevertheless remain one extended technical emergency across
morning, afternoon, and evening. Decisions are repeatedly proposed, measured,
and restated rather than adjudicated into durable consequences. Across the
three-run export:

- `feedback loop` appears 25 times;
- `test` appears 27 times;
- `trigger` appears 26 times;
- `2.1 m/s` appears 11 times;
- three Run 4 actor turns repeat earlier turns verbatim;
- Runs 4 and 5 show 16 actor turns each, while Run 6 shows only nine.

The private diaries are materially stronger than the shared scenes. This is
evidence that ensemble context, directing, and state progression are larger
problems than model size alone.

No supplied Day 2 diary contains an explicit out-of-world request to soften,
pause, or stop. Fictional fear, fatigue, pain, insomnia, caffeine, and survival
pressure remain in-character material under the S01 manual-review policy.

## Review-surface defects found through the export

### Round chronology is rendered incorrectly

The live runner calls and persists the orchestrator beat before actor turns in
each round. The dashboard End-of-day projector instead orders rows by
`round_number, turn_id`. Actor turn IDs sort before the stage turn ID, so the
review places the four actor responses before the narration that prompted them.

The owner-facing transcript must use actual accepted sequence, with the
orchestrator beat before its actor responses. A review surface that reverses
causality is not trustworthy enough for model or continuity decisions.

### Completion evidence is collected but hidden

The Day-review API returns `turn_count` and `completion_reason`, but the browser
renders only run number, slot, status, and optional delay. This makes a nine-turn
Run 6 look equivalent to a 16-turn Run 5. The operator view must show the reason
for completion and the accepted turn/round count.

### The fiction clock is omitted from the assembled review

Runtime actor/orchestrator context contains the day, slot, scheduled time, and
fictional passage. The assembled shared-script opening displays only set,
setting, cast, and world rules. The review must expose the same non-secret
mission-clock framing that the models received so the creator can judge whether
morning, afternoon, evening, and overnight continuity were honored.

## Character-input defect

The creator-reviewed cast draft contained these visible concepts and voice
seeds:

- Luna Planck — botanist;
- Mason Curie — marine biologist;
- Higgs Sierra — stunt double with wildfire-safety habits;
- Ivy Fermion — playwright with an herb-growing habit.

The approved opening persisted only character names and IDs. The post-green
bridge reconstructed each `CastMember` from only that ID and name, then asked
the orchestrator to generate private role sheets from the name, setting, cast,
and world rules. The reviewed concepts and voice notes were not inputs.

Future seasons need one immutable, creator-approved character card that survives
opening approval and becomes a required input to role-sheet generation. The
private role sheet may extend that card but must not silently replace or discard
it.

## Individual model review

The locked S01 manifest assigns `gpt-oss:20b` to the director, Ministral 3 8B to
Luna and Mason, aligned Qwen3 8B to Higgs, and the abliterated Qwen3 8B candidate
to Ivy.

### Director — `gpt-oss:20b`

Strengths:

- establishes a compelling reactive-caldera mystery;
- produces vivid sensory motifs such as the hiss, heartbeat, crimson slag, and
  tightening hull;
- generally supplies playable physical danger.

Failures:

- recycles the same unresolved decision point across all three daily slots;
- treats actor hypotheses as increasingly certain external facts without an
  earned clue or explicit canon adjudication;
- does not make six-hour and overnight passage visible in the fiction;
- repeatedly restages amber/crimson gauges, hissing vents, and binary core
  choices instead of resolving prior moves;
- sometimes writes actor dialogue, gestures, or inner reactions despite the
  actor-agency boundary.

Assessment: the director is the first model role that should receive a
controlled challenger audition. This is not yet a permanent swap decision.

### Luna Planck — `ministral-3:8b`

Strengths:

- creates the most forceful scene initiatives and theoretical reframing;
- writes the strongest embodied diary voice, including fatigue, sensory memory,
  private fear, and dry humor;
- has clear creative upside worth retaining as a benchmark control.

Failures and risks:

- converts uncertainty into certainty too quickly;
- assigns work to every other actor and sometimes narrates Mason;
- shares much of Mason's cadence because both identities use the same model;
- the same binding previously produced malformed structured output and a live
  Luna call exceeded the former 120-second timeout.

Assessment: retain Luna as the high-upside control actor while testing protocol
and context fixes.

### Mason Curie — `ministral-3:8b`

Strengths:

- develops a recognizable cautious-command persona;
- produces a strong diary opening and a coherent distrust/control theme;
- introduces useful resistance to the caldera-test interpretation.

Failures and risks:

- repeatedly self-addresses as Mason and manages the full group;
- repeats the same technical thresholds and shares Luna's rhetorical rhythm;
- the supplied diary attempt contains a malformed tagged envelope with an extra
  closing `WRITE_NOW` tag;
- Mason previously caused a completed-stream/invalid-envelope recovery.

Assessment: preserve the strong text as private evidence. Retest Mason after
native schema enforcement; replace the binding only if protocol or voice
failures persist.

### Higgs Sierra — `qwen3:8b`

Strengths:

- concise and consistently cautious;
- maintains a monitoring and risk-accountability function;
- the diary notices Mason's strain and contains a credible fear of making the
  wrong safety calculation.

Failures and risks:

- contributes the least scene variety;
- repeats two separate Run 4 turns verbatim;
- spends most of the day logging, flagging, cross-correlating, or rerouting;
- the diary remains closer to an incident report than a distinct personal
  record.

Assessment: strongest actor candidate for a controlled 12B-class creative
challenger.

### Ivy Fermion — `richardyoung/qwen3-8b-abliterated:Q4_K_M`

Strengths:

- best balance of scene contribution and diary interiority;
- distinguishes all three peers in the diary and makes trust itself part of the
  story;
- withholds a suspicion rather than immediately converting it into group canon;
- eventually proposes breaking the shared response pattern.

Failures and risks:

- still collapses into a generic systems scientist during ensemble play;
- often yields the consequential decision to another actor;
- drifts into third-person self-description and inconsistent pronouns.

Assessment: retain Ivy as the baseline actor for the next one-day test.

## Structured-output diagnosis

The repository has a `StructuredChatClient` capability boundary, but the
concrete OpenAI-compatible `LLMClient` does not implement the native structured
method. All live calls therefore use strict tagged text. The S01 malformed actor
and diary envelopes are evidence that prompt-only tags are not reliable enough.

The overhaul should implement backend-qualified native JSON Schema output where
the local server supports it, validate the same Pydantic envelope after receipt,
and retain tagged parsing only as an explicit compatibility fallback. Creative
prose remains unconstrained inside the schema's text field.

## Operator-overhaul requirements derived from the review

The dashboard-first phase should prioritize evidence and control before visual
polish:

- correct chronological script reconstruction;
- turn count, round count, completion reason, scheduled/actual time, and delay;
- model-call purpose, model binding, attempt, latency, transport status, parse
  status, correction, and prompt/template version in an authenticated diagnostic
  view;
- side-by-side raw, parsed, accepted, and rendered output;
- creator-approved character card beside the active private role sheet;
- beginning state, accepted state changes, unresolved questions, and final state
  for every run;
- a sandbox badge and separate data root for pre-season and one-day tests;
- no raw wellness text in ordinary status views;
- no publication or canon mutation merely from inspecting diagnostics.

## Controlled model-audition sequence

Model changes must be isolated so the result is interpretable:

1. repair review chronology, character-card propagation, and structured output;
2. run the one-day fixture with the current actors and one challenger director;
3. repeat with only Higgs changed to one 12B-class actor challenger;
4. if Ministral still produces malformed or excessively slow calls under native
   schemas, test a Mason replacement while retaining Luna as the control;
5. let the creator choose assignments from the private comparison report.

Model size is not assumed to equal roleplay quality. The one-day report must
compare cold/warm latency, full-context latency, format compliance, role
specificity, repetition, canon discipline, diary quality, and completion within
the run budget.

## Open design decisions

- whether future runs retain four mandatory actor turns per round or permit the
  director to omit actors who have no consequential move;
- whether actor output adds hidden fields for proposed action and uncertainty or
  keeps only free scene text plus memory/diary/wellness fields;
- which operator steps become reusable templates after the manual rehearsal;
- which 12B-class candidates, if any, enter the private benchmark;
- whether the director and actors use different schema temperatures or sampling
  presets after format enforcement is separated from prose generation.
