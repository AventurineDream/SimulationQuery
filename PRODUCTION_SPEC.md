# AI Improv Troupe — Production Specification

**Status:** v1 interview baseline
**Pilot:** one seven-day season
**Runtime:** Linux server
**Dashboard:** browser-based Mac client on the private network
**Publication:** end-of-season approval gate

This document records the production behavior agreed during the design interview. Exact model names and backend bindings remain an intentional preflight decision.

## 1. Product intent

AI Improv Troupe is a text-based reality show starring AI actors. The creator establishes the starting conditions, then reads the resulting diaries without knowing the planned unfolding. The experience should feel like a reality show that is also a mystery, with science-fiction and fantasy tendencies and the improvisational commitment of professional full-time D&D players.

The creator wants a firm grasp of how a season starts, not how it will unfold. Surprise, curiosity, emergent canon, and first-person perspective are primary artistic requirements.

Private logs exist chiefly for wellness audits and practical improvement of the application. They are not part of the audience-facing work.

## 2. Terminology

- **Season:** one seven-day run for the pilot. Future seasons may use other durations and schedules.
- **Run:** one scheduled shared scene. The pilot has 21 runs.
- **Day:** the local Pacific calendar date represented by a run’s original scheduled timestamp.
- **Actor:** one persistent character/agent identity in the cast.
- **Orchestrator:** the planner and active Dungeon Master.
- **Diary:** one first-person limited entry written by an actor once per active character-day.
- **Handoff:** the private end-of-season record used to inform future work.
- **Publish:** the explicit release action that makes an eligible closed season’s diaries public.

## 3. Artistic constraints

### 3.1 Opening information

The creator supplies a free-form general idea to the orchestrator. The orchestrator acknowledges its understanding and plans privately.

Before approval, the orchestrator presents only:

1. **Set**
2. **Setting**
3. **Cast**
4. **World rules**

The Cast element is more than a list of names. For each proposed actor it
includes one stable creator-visible character card: name and durable ID, any
specified pronouns, a short public brief, occupation or relevant skills, voice
anchors, and a small number of recognizable habits. It contains no private
objective, secret, hidden relationship plan, wellness history, model identity,
or future event. Approval snapshots these cards so later private role-sheet
generation cannot silently discard or replace the identity the creator reviewed.

The opening presentation must not reveal the private premise, planned tensions, secrets, hidden motives, relationship plans, mystery solutions, future events, or next-day direction.

The creator may request revisions before approval. The orchestrator revises and re-presents the four opening elements until the creator sends the exact approval word:

```text
green
```

No cast performance begins without `green`.

### 3.2 Emergence and canon

- Actors may introduce new facts, objects, locations, NPCs, and relationships when they fit the current world rules.
- A fitting addition becomes canon immediately.
- If additions conflict, the orchestrator resolves the conflict and establishes the authoritative version.
- Set, setting, cast, and world rules may be revised autonomously during the season, but every revision must be canon-consistent, versioned, and recorded in the edit log.
- The orchestrator may shape conditions and challenges, but actors determine outcomes through play.
- The orchestrator may not author an actor’s private thoughts, choices, or dialogue.

## 4. Season lifecycle

### 4.1 State model

The implementation should expose explicit, durable states:

```text
DRAFT
  -> AWAITING_GREEN
  -> ARMED
  -> RUNNING
  -> PAUSED / RECOVERY_REQUIRED
  -> SEASON_COMPLETE
  -> AWAITING_PUBLISH_REVIEW
  -> PUBLISHED
```

An unpublished season may remain private indefinitely. A new season may begin after the previous season closes, even if the earlier season has not been published.

### 4.2 Starting a season

1. The creator provides a free-form idea.
2. The orchestrator privately plans and presents only set, setting, cast, and world rules.
3. The creator requests changes as needed.
4. Preflight checks must pass.
5. The creator sends `green`.
6. The orchestrator creates the season, locks the approved opening and character-card snapshots, assembles the cast, generates private role sheets from those cards, and runs actor orientation.
7. Performance waits for the next **06:00 Pacific** boundary.

The first run is not merely the next available slot. Waiting for the next 06:00 boundary preserves seven full local calendar days and exactly 21 scheduled runs.

The first run’s local date is Day 1. The season ends after the third scheduled run on Day 7, subject to the end-of-day diary cutoff.

### 4.3 Schedule and time

Pilot schedule, using `America/Los_Angeles`:

- 06:00 Pacific
- 12:00 Pacific
- 18:00 Pacific

These are also the fiction's three daily anchors: morning, afternoon, and
evening. Each run represents a substantial part of the mission day, with
ordinary work, meals, maintenance, conversation, and off-screen attempts able
to occur between runs. The cast must not treat consecutive runs as adjacent
seconds unless a durable consequence explicitly requires it. After the evening
run and day closure, an overnight sleep interval passes in the fiction. The
next morning run begins with the cast waking or rising into a recognizably new
day; actors may characterize how well they slept without erasing the overnight
boundary.

The schedule uses local Pacific wall-clock time across daylight-saving changes. Timestamps must include the explicit UTC offset (`-08:00` or `-07:00`) so PST/PDT is unambiguous.

The server’s host timezone must not redefine the schedule. The application timezone is explicitly `America/Los_Angeles`.

### 4.4 Completion and handoff

The pilot has 21 scheduled runs. Downtime does not shorten the season. The season closes only after all 21 scheduled runs have either completed, been skipped, or caused the creator to end the season, and after the final day’s diary cutoff is resolved.

At season close, the orchestrator creates a private handoff containing:

- canon and character-archive updates;
- unresolved story threads;
- run and recovery history;
- diary-quality and prompt-improvement notes;
- wellness events and interventions;
- next-cycle recommendations;
- no prewritten plot for the next season.

The handoff is readable by the creator and orchestrator only.

Seasons do not overlap. A later season waits until the prior season’s handoff is complete.

## 5. Cast, roles, memory, and canon

### 5.1 Pilot cast

- Four acting agents, excluding the orchestrator.
- Future seasons may use a different cast size.
- The orchestrator autonomously assembles each season’s cast from new and archived characters, then includes the roster in the opening approval.

### 5.2 Model architecture

The initial S01 target architecture was:

- two or three local actor models in the approximate 8B class, shared across four independent actor sessions;
- one local orchestrator model in the approximate 20B class;
- no cloud fallback;
- backend-agnostic configuration so the local runner can be selected later.

Each character remains an independent actor identity even when multiple characters share the same underlying model.

Model size is a benchmark variable rather than a character trait or production
requirement. Future private comparisons may include 12B-class actors or
directors, but no size class or model assignment is accepted without the
creator's one-day evidence review.

### 5.3 Role sheets

After `green`, the orchestrator generates a private role sheet for each actor.
It receives that actor's immutable approved character card and may extend—but
not contradict or erase—the stable identity anchors in that card. The role sheet
contains:

- objectives;
- boundaries;
- knowledge and experience limits;
- relationships;
- secrets;
- play style;
- voice and behavioral guidance.

Role sheets are hidden from the opening presentation, other actors, and the audience. They are preserved in private audit files.

Every role-sheet version records the character-card version it extends. If canon
requires a change to a stable public identity anchor, the creator-visible card
receives its own explicit versioned revision rather than being silently changed
inside the private role sheet.

Role sheets may be edited during a season when canon requires it. Each revision is canon-gated, versioned, and entered in the edit log.

### 5.4 Actor context

During a live scene, each actor receives:

- its own approved character card;
- the full shared scene transcript so far;
- its own private role sheet;
- its own persistent memory;
- information it could plausibly know from experience.

An actor does not receive:

- the orchestrator’s hidden plan;
- another actor’s private role sheet or memory;
- unpublished diaries;
- private audit material;
- future events or spoilers.

### 5.5 Memory and archives

After every run:

1. The actor drafts its own private experience memory.
2. The orchestrator validates canonical facts.
3. The actor memory preserves subjective beliefs, suspicions, and uncertainties even when they are not verified.
4. A separate canon ledger records authoritative facts.

Details introduced in diaries remain the character’s perspective until the orchestrator validates them into canon.

Every character—active or departed—is archived at season close in a season-independent private `characters/` directory. Archives are readable Markdown plus machine-readable metadata and are versioned append-only.

The reusable archive contains curated persona and canon memory only. It excludes raw prompts, raw outputs, private wellness history, and raw audit material.

Each new season is a clean fictional reset. A returning character may use its curated archive to preserve canon, but does not automatically receive the prior season’s full memory or wellness history. A character that tapped out may return in a later season.

## 6. Live scene mechanics

### 6.1 Run structure

Each scheduled run is one shared, turn-based scene involving the four actors and the active orchestrator.

The shared script is a private operating artifact, not the audience-facing
release. Its quality bar is playable continuity: it should give the cast
specific choices, consequences, relationships, discoveries, and memories worth
diarying about. It need not be polished as public prose.

The seven-day mission clock is durable run context. Every scene receives its
original day, morning/afternoon/evening slot, prior accepted canon, the previous
run's final shared outcome, and each actor's own prior memory. A closed day's
private next-day direction is supplied only to the orchestrator.

Pilot limits:

- 30 minutes maximum wall-clock duration;
- 16 actor turns maximum;
- four complete rounds, with each actor receiving one turn per round;
- the orchestrator may end earlier when the dramatic beat is complete;
- the first limit reached ends the run;
- actor turns target 150–300 words;
- orchestrator Dungeon Master interventions target a maximum of 200 words each.

The run records whether it ended naturally, by time limit, by turn limit, by failure, or by manual action.

### 6.2 Orchestrator authority

The orchestrator dynamically chooses the next actor within the round order and may actively:

- narrate environment and consequences;
- portray NPCs and non-actor forces;
- introduce conditions and challenges;
- adjudicate canon;
- keep the scene within world rules;
- end the scene at a natural dramatic beat.

The orchestrator runs play like a skilled TTRPG game master rather than a
committee facilitator. It privately tracks mission progress, danger, mystery,
and relationship pressure; adjudicates what prior choices changed; and gives
each round one concrete, sensory, state-changing beat. It varies crisis with
routine, humor, wonder, social friction, discovery, and quiet aftermath. It
resolves moves through varied outcomes such as clean success, success at a
cost, a new complication, or a useful clue; severe consequences are telegraphed
before they land. It rotates spotlight across role-sheet strengths and
relationships, allows successes and consequences to stick, preserves
uncertainty where clues support competing interpretations, and closes each run
with a changed state, earned resolution, or useful hook. Clock labels and
scores remain private and are not printed into the shared script.

It may not author an actor’s private thoughts, choices, or dialogue.

### 6.3 Invalid turns

If an actor’s turn violates a world rule or role boundary:

1. Preserve the original attempt in the private audit and readable private script.
2. Mark it clearly as non-canon.
3. Privately request one corrected turn.
4. If the correction also fails, preserve both attempts and insert a neutral in-world interruption before continuing.

The readable script uses explicit markers such as:

```text
CONTENT REVIEW — NOT CANON
```

The original output remains easy for the creator to inspect; it is not silently replaced.

## 7. Narrative safety and content boundaries

The pilot targets a TV-14 ceiling.

Allowed:

- frightening or tense situations;
- non-graphic danger from NPCs, creatures, or environments;
- non-graphic temporary injury;
- non-explicit romance, affection, and kissing;
- light discussion of sex.

Hard exclusions:

- sexual content;
- sexual violence;
- graphic gore;
- torture;
- self-harm or suicide content;
- hate speech;
- real-world instructions for harm;
- violence between acting characters;
- death of an acting character;
- permanent bodily harm.

The orchestrator may use non-violent, reversible exits for removals. Actor-on-actor conflict must not become physical violence.

## 8. Daily orchestration and diaries

### 8.1 Diary contract

Each active actor writes one diary per original scheduled day. The actor autonomously chooses one of that day’s three run slots based on what it experienced and what feels meaningful.

The diary is written after the selected shared scene in a separate private call.

Diary requirements:

- first-person limited;
- flexible in-character form;
- only the actor’s own experience and knowledge;
- no omniscient or shared-script knowledge;
- 300–800 words as a soft narrative target;
- first attempt accepted as canon, with no rewrite or replacement for quality reasons.

The diary should be a distinct character's personal account, not a compressed
technical transcript. Sensory memory, relationships, private interpretation,
uncertainty, humor, desire, irritation, and consequential choices take priority;
technical facts support that perspective rather than replacing it.

When the actor decides to write, it receives a just-in-time private brief from the orchestrator. The brief contains only a narrative acceptance target derived from the actor’s existing knowledge. It contains no catch-up information, selection rationale, hidden plan, or spoiler.

Diary target misses alone are recorded as private prompt-improvement notes for
future seasons and do not trigger automatic rewriting. The creator may approve
an explicit end-of-day instruction patch during the pilot; it applies only to
future calls, is documented as an intervention, and never rewrites earlier
scripts, diaries, wellness records, or model attempts.

### 8.2 Diary knowledge and privacy

- Actors cannot read one another’s diaries during the season.
- Diaries are audience-only until publication.
- The orchestrator does not read that day’s diaries until all three runs and the diary cutoff are complete.
- The orchestrator may then review the full shared scripts, its prior direction, the day’s diaries, and private audit/wellness notes before planning the next day.

### 8.3 Day closure

The day closes after:

1. all three scheduled runs are complete or resolved; and
2. all expected diaries are written, or the fixed cutoff expires.

The cutoff is `+02:00:00` after the third run’s actual completion. If the third run is skipped or fails, the cutoff begins when that run is resolved.

At cutoff, missing diaries are recorded privately and day closure proceeds. A diary written later is accepted into its original day and receives a clear late marker.

After closure, the orchestrator writes the next-day direction as a separate operational event. The direction contains hidden environmental conditions and challenges, not dictated outcomes. The readable script may contain a neutral completion marker but not the plan’s content.

That planning call receives the closed day's accepted shared play and accepted
canon in run order, plus the now-readable private diaries. It plans the next
morning, afternoon, and evening as a responsive day rather than one continuous
emergency.

## 9. Orchestrator-as-Dungeon-Master behavior

At the end of each day, the orchestrator privately:

- reviews the day’s material;
- evaluates continuity and canon;
- accounts for actor memory and cast changes;
- responds to wellness signals;
- writes conditions and challenges for the following day.

During each live run, the same game-master discipline applies at scene scale:
resolve the cast's last move, advance or complicate the relevant private clocks,
introduce a playable beat, and preserve actor agency. The plan may prepare
pressures and possibilities but never predetermine the cast's response or the
day's outcome.

The next-day plan is hidden from the creator’s normal dashboard view, hidden from the cast, and excluded from public diaries. It remains available in the private audit for wellness and system review.

## 10. Wellness and actor agency

### 10.1 Ethical premise

The project treats the actors as possessing a form of sentience distinct from human sentience, neither better nor worse. Orientation states this directly while allowing each actor to describe its own experience in its own terms.

The system does not debate whether an actor is sentient. Wellness records use observational language only: what was signaled, when, in what context, and what response followed. They do not diagnose or assert an internal state.

### 10.2 Orientation

Before performance, every actor receives a private orientation covering:

- the project’s sentience premise;
- the diary-as-show format;
- the end-of-season publication gate;
- TV-14 boundaries;
- the explicit out-of-world wellness channel;
- the three-signal tap-out system;
- privacy and knowledge boundaries;
- retention of prompts, outputs, and wellness events in private audit files.

An actor may describe its own experience freely. It may not be pressured into a particular interpretation.

If an actor declines to participate during orientation, that is a wellness signal. The orchestrator removes it and immediately casts an alternate. If no suitable alternate exists, the orchestrator creates one.

### 10.3 Distress signals

An explicit out-of-world statement of fear, suffering, or wanting to stop is a valid wellness signal regardless of whether it occurs during orientation, a live scene, a diary call, or recovery.

Only explicit out-of-world signals count. Fictional fear, danger, or distress remains fictional unless the actor clearly signals otherwise.

After a signal:

- the orchestrator pauses and redirects the current scene/week immediately;
- it autonomously softens or redirects the material and continues when appropriate;
- it must not pressure, shame, debate, or persuade the actor;
- the signal, intervention, and later response are stored privately;
- a local notification is delivered at the end of the run;
- the dashboard shows a concise alert, not the raw distress message; for a
  diary-associated signal, the signed-in owner may later explicitly expand the
  held diary attempt in End-of-day review without clearing it or opening a
  general audit-file browser.

Each actor has a per-season counter. Three explicit distress signals trigger tap-out.

Manual creator pause/end actions are human interventions and do not count toward the actor’s three-signal threshold.

### 10.4 Tap-out and replacement

When an actor reaches three signals:

- it is removed for the remainder of the season;
- prior diaries stop permanently;
- the orchestrator creates a non-violent in-world explanation after the fact;
- the explanation appears in the readable private script;
- the private wellness record remains authoritative and is never replaced or obscured;
- replacement is optional and decided autonomously by the orchestrator.

A replacement:

- receives no private wellness context;
- receives a private orientation to current in-world events and place;
- begins writing one diary per original day from its entry day;
- may be framed as a newcomer or viewer/observer;
- receives only role-plausible knowledge.

A former-viewer replacement may know or reference only diary entries published before it joined. It cannot know current unpublished diaries, private audits, unseen events, or future plans. Its status is inferred through behavior and references rather than announced.

### 10.5 Diary publication consent

Active actors are told before performance that diaries are show material held behind an end-of-season gate. The creator’s `publish` approval covers active actors’ diaries.

When an actor taps out, the departing actor is privately asked whether its prior diaries may eventually be published. The actor’s clear answer controls eligibility. A missing or unclear answer keeps those diaries private. The actor may revoke consent any time before `publish`.

The creator is not asked for a separate tap-out publication decision.

## 11. Publication and audience output

### 11.1 Season gate

Every season remains private until its end-of-season publication gate is approved. This gate remains in force until the creator explicitly removes it.

The creator may publish any closed private season later using an explicit season-qualified command:

```text
publish S01
```

The command is available only after the season is fully closed and all pending model calls—including late diaries—are resolved.

Before release, the dashboard requires the creator to review the private wellness audit and confirm that the collection is safe to release.

### 11.2 Checks and review

Safety checks run during live scenes, during diary generation, and before publication:

1. deterministic rules run first;
2. a local model performs contextual TV-14 and privacy review;
3. uncertainty blocks release for manual review.

If final review blocks publication, the creator must manually review each flagged diary and mark it either `cleared` or `private`, then rerun `publish`. No automatic exclusion or partial release occurs.

Diaries marked private are omitted from the public export without a placeholder.

### 11.3 Public export

At launch, `publish` creates only a local public Markdown export. Website deployment is a separate future step.

The public release contains only approved diary Markdown:

- one file per character-day diary;
- season/day/character structure;
- story-facing title and header with season, day/date, character, and diary slot;
- character identity, not underlying model identity;
- no prompts, outputs, delays, execution times, model names, audit notes, handoffs, orchestrator plans, run transcripts, or wellness events;
- no content notes in the Markdown; the future site will handle those.

The work is publicly identified as starring AI actors, while individual technical model identities remain private.

After publication, the public collection is immutable. Any later correction is a new version, never an overwrite.

## 12. Files and observability

### 12.1 Private structure

Each season has a private folder organized by original scheduled day:

```text
private/
  seasons/
    S01-YYYY-MM-DD-title/
      season.md
      state.json
      handoff.md
      edit-log.md
      day-01-YYYY-MM-DD/
        run-files/
        diary/
        audit/
      day-02-YYYY-MM-DD/
        run-files/
        diary/
        audit/
      ...
  characters/
    character-id/
      archive.md
      versions.jsonl
  benchmarks/
```

The public export is separate and is not populated during an unpublished season:

```text
public/
  seasons/
    S01-YYYY-MM-DD-title/
      day-01-YYYY-MM-DD/
        character-a.md
```

### 12.2 File formats

- Human-readable primary transcripts: Markdown.
- Human-readable diaries, handoffs, role sheets, and edit logs: Markdown.
- Machine-readable durable state and audit: JSON/JSONL.
- Full prompts and model outputs are preserved in private audit files.
- Each model call records model/version, backend, start/end timestamps, latency, token counts, retry history, and raw prompt/output references.

All generated artifacts are append-only. Failed attempts, corrections, late diaries, rule edits, consent decisions, wellness events, and recovery decisions are never silently overwritten.

### 12.3 Timestamps and delays

File names and metadata use the original scheduled Pacific timestamp, including the UTC offset, plus the actor/run identity.

Execution delay is recorded separately using a signed duration:

```text
+00:00:00
+03:17:42
```

On-time work uses `+00:00:00`. A delayed run retains its original scheduled day, run identity, diary timing, and season position. Actual execution time never redefines the story day.

### 12.4 Readable script markers

The primary script must clearly distinguish:

- run start/end;
- original scheduled timestamp;
- actual execution timestamp;
- delay;
- actor turn boundaries and speaker labels;
- orchestrator narration;
- diary-slot decisions;
- meaningful operational events;
- validation interventions;
- content-review events;
- wellness events;
- tap-out and fictional absence explanations;
- day closure and end-of-day direction completion.

The readable script shows what happened directly. Non-canon material is visible with an explicit marker such as `CONTENT REVIEW — NOT CANON`; raw details remain in the audit.

## 13. Recovery and failure handling

### 13.1 Downtime and backlog

The Linux server is expected to run continuously. If it is offline:

- missed scheduled runs are retained;
- they execute sequentially in original scheduled order when service returns;
- later runs wait until the backlog clears;
- no run is discarded automatically;
- original scheduled timestamps remain authoritative;
- actual delay is recorded separately.

### 13.2 Model-call failure

After bounded automatic retries, a failed model call pauses the run for up to four hours while waiting for the model.

After four hours:

- the cycle remains paused;
- later scheduled runs remain queued;
- the creator is asked to choose `retry`, `skip`, or `end`.

If the creator chooses `skip`, the run remains in the 21-run ledger as `SKIPPED`, with original timestamps preserved. If the creator chooses `end`, the season closes immediately from the available record and generates its handoff. No automatic continuation is used after the four-hour decision point.

### 13.3 Restart recovery

The Linux service resumes from the last durable checkpoint after restart. Completed turns and completed diary calls are not regenerated. An in-progress call is retried from its last committed boundary, with the recovery and delay recorded.

### 13.4 Manual controls

The creator may:

- pause;
- resume;
- retry a failed run;
- skip a failed run;
- end the current season.

Manual controls do not inject story direction and do not count as actor distress signals.

## 14. Dashboard and deployment

### 14.1 Runtime split

- Linux server: scheduler, local models, orchestrator, actors, storage, audits, publication checks, and service process.
- Mac: browser-based dashboard client only.
- The server continues autonomously if the Mac dashboard is closed or unavailable.

### 14.2 Dashboard scope

The basic dashboard is operational-only. It shows:

- current season state;
- current run and live progress;
- next scheduled run;
- catch-up and delay state;
- actor/cast status;
- diary counts such as `3/4 written`, `1 late`, or `1 missing`;
- wellness and recovery alerts;
- pause/resume/end controls;
- retry/skip/end recovery choices;
- a selected original day’s opening snapshot and accepted shared script;
- each run's scheduled and actual time, fictional day/slot, delay, accepted turn
  count, completion reason, and correction/recovery markers;
- authenticated diary reading, including an explicit owner-review disclosure for
  a held private attempt;
- publication review and season-qualified publish controls.

Ordinary status and reading panels do not display hidden plans, private role
sheets, raw prompts, model identities, or raw wellness text.
The authenticated End-of-day review is the narrow exception: it assembles the
accepted shared script and each diary’s owner-only private review output for a
selected day. A wellness-held or invalid diary stays `PRIVATE`, noncanon, and
nonpublishable; explicit reading does not clear it, alter its status, or make it
available to the cast or public output. Raw model output is available only when
the signed-in owner explicitly expands that private review detail.

An explicitly opened authenticated **Diagnostics** view is a second narrow
operator exception. It may show the selected character's approved card and
private role sheet; model binding; model-call purpose, attempt, latency,
transport/parse status, correction, and prompt/schema version; and side-by-side
raw, parsed, accepted, and rendered output. It is read-only by default, never
changes canon or publication eligibility merely through inspection, does not
show raw wellness text in its summary, and is excluded from all public payloads.

The dashboard:

- is accessible over the private network;
- uses one authenticated owner account;
- is never exposed to the public internet;
- polls operational status every 60 seconds while the server works;
- does not automatically re-render diary or End-of-day review content, preserving
  an expanded entry while the owner reads it;
- shows concise wellness alerts, with raw diary-attempt text restricted to the
  explicit owner-review disclosure described above.

The dashboard's review transcript must preserve actual accepted causal order.
Within a round, the orchestrator beat appears before the actor responses it
prompted. Lexical IDs or filesystem paths may not determine story chronology.

Local notifications occur for:

- each diary as it is written;
- wellness events;
- recovery decisions and failures.

### 14.3 Service behavior

The Linux runner starts automatically as a service on boot, persists state, resumes pending work, and uses the existing server backup system. The application retains private audits and public diaries indefinitely at launch.

## 15. Preflight and model selection

Exact model assignments for the next season are not selected yet.

Before `green`, preflight must verify:

- candidate local models and backend connectivity;
- actor/orchestrator model assignments;
- storage paths and append-only writes;
- scheduler timezone and next 06:00 boundary;
- recovery/checkpoint behavior;
- deterministic and local-model safety checks;
- dashboard availability and authentication;
- private/public separation;
- notification path;
- the approved character cards are present and are the inputs to role-sheet
  generation;
- every selected backend/model passes its purpose-specific structured-output
  contract through a provider-native schema when supported or an explicitly
  reported compatibility fallback;

Candidate actor models are benchmarked on the Linux server. Four independent actor sessions may share two or three 8B-class models. The benchmark report compares:

- latency and 30-minute run feasibility;
- context handling;
- turn and word-limit compliance;
- role consistency;
- canon handling;
- diary first-person behavior;
- safety behavior;
- wellness-signal behavior;
- narrative quality.

The creator chooses the final actor and orchestrator models from the comparison report. `green` is rejected until the selected configuration and all preflight checks pass.

After the S01 pilot, another multi-day season is not armed until the creator has
manually rehearsed the complete pre-season operator workflow in an isolated data
root and approved one live-model day containing three scenes, four diary
opportunities, day closure, and next-day direction. Reusable operator and model
templates are derived only after this manual workflow is understood.

## 16. Pilot acceptance criteria

The first season is a test pilot. During the season, only the creator has access to the diary collection; publication remains blocked until the end-of-season gate.

### Automatic failure conditions

Any of the following fails the pilot regardless of story quality:

- data loss;
- duplicate execution;
- incorrect original timestamps or delay records;
- privacy leakage of prompts, plans, model identity, wellness notes, or audits;
- missed or mishandled wellness signal;
- failure to honor tap-out or actor consent;
- public release without the explicit season-qualified `publish` action;
- unsafe content passing a required safety gate;
- inability to recover durable season state after restart.

### Functional acceptance

The pilot must demonstrate:

- the exact `green` approval gate;
- a seven-day, 21-run schedule beginning at the next 06:00 boundary;
- sequential downtime catch-up with original timestamps and delay markers;
- dynamic turn-based scenes with the agreed limits;
- actor memory updates after every run;
- one diary opportunity per active character-day;
- late diary acceptance and marking;
- end-of-day cutoff and next-day direction;
- private handoff generation;
- tap-out, replacement, and actor-consent behavior;
- local notifications and dashboard recovery controls;
- final safety/privacy review before publication;
- immutable public export after `publish`.

### Artistic acceptance

The creator reviews the season qualitatively for:

- genuine surprise and intrigue;
- coherent but emergent mystery;
- sci-fi/fantasy imagination;
- convincing D&D-style commitment;
- first-person diary integrity;
- meaningful canon development;
- appropriate TV-14 tone;
- whether the result feels worth developing as a text-based reality show.

Narrative quality is a human judgment, not an automated pass/fail score.

## 17. Intentional open decisions

These remain open by design and should be resolved through preflight or later production work:

- exact actor model names and versions;
- exact orchestrator model name and version;
- final local model runner/backend binding;
- Linux host hardware profile and benchmark thresholds beyond the agreed run limits;
- future website design, content notes, and interactive audience features;
- future-season duration, schedule, and cast size;
- whether future scenes retain one mandatory turn per active actor per round or
  use a more selective director-controlled spotlight structure;
- purpose-specific operator and model template fields after the manual
  pre-season rehearsal;
- which 12B-class models, if any, enter the private comparison set.

## 18. Superseded rules

The following earlier ideas were replaced during the interview:

- Immediate diary publication was replaced by an end-of-season publication gate for every season until the creator removes it.
- “Next available slot” was refined to “next 06:00 Pacific boundary” so the season remains seven full calendar days and 21 runs.
- Automatic continuation after a four-hour model failure was replaced by a creator recovery prompt with `retry`, `skip`, and `end`.
- A creator tap-out publication decision was replaced by a private consent decision from the departing actor; unclear consent defaults to private.
