# AI Improv Troupe dashboard overhaul — functional plan

**Status:** functional model, low-fidelity interaction architecture, Warm
Instrument visual system and all five high-fidelity checkpoints approved and
frozen; the complete dashboard design is approved; implementation-ready
sequence prepared; DASH-00 through DASH-04 are implemented, locally verified,
and creator-accepted; DASH-05 is implemented and locally verified at its manual
S02 creator gate

**Updated:** 2026-08-27

**Owner:** creator

**Scope:** private, single-owner operator dashboard

**Current design gate:** complete; the next dashboard decision is whether to
accept the DASH-05 healthy supervision and recovery rehearsal

This document defines what the dashboard should help the creator understand and
do. The creator approved its functional model through focused decisions on
2026-08-24. Layout, visual styling, component appearance, and high-fidelity
screen design were completed and approved in collaborative Penpot work. The
bounded coding order and acceptance gates are in
[DASHBOARD_IMPLEMENTATION_SEQUENCE.md](DASHBOARD_IMPLEMENTATION_SEQUENCE.md).

The draft is grounded in the current dashboard and APIs, the S01 Day 2 review,
and Gate 12. It did not inspect the live Linux database and does not authorize
ending, restarting, publishing, deleting, or otherwise changing S01.

## 1. Committed sequence and open choices

The creator has committed to this order:

1. plan the dashboard overhaul functionally;
2. design the approved workflow collaboratively in Penpot;
3. implement and verify the dashboard;
4. manually perform the complete pre-season operator workflow;
5. run one isolated live-model day;
6. derive reusable operator and model templates from what the rehearsal proves.

The following remain open creator decisions:

- whether future scenes keep mandatory participation by every actor each round;
- final model assignments and which 12B-class candidates enter testing;
- which steps become templates after the one-day test;
- any explicitly selected private S01 excerpt to add later if synthetic design
  content proves insufficient.

### Approved functional decision — primary mental model

**Decision date:** 2026-08-24

The dashboard will use a **guided studio workflow** as its primary mental model.
Home, preparation, review, private closure, and publication should guide the
creator through one intelligible next step at a time. Denser control-room detail
is intentionally confined to Live and Diagnostics, where simultaneous system
evidence is useful.

This decision did not by itself approve navigation or visual design; navigation
was approved separately below, while layout and visual design remain open.

### Approved functional decision — stable navigation

**Decision date:** 2026-08-24

The dashboard will use six stable primary destinations:

1. **Home**;
2. **Prepare**;
3. **Live**;
4. **Review**;
5. **Diagnostics**;
6. **Seasons**.

They remain visible throughout the lifecycle so the dashboard does not change
its basic map while the creator is learning it. A destination with no current
work remains readable and explains its prerequisite or empty state. Invalid
actions are gated with reasons; the interface does not imply that a hidden page
or disappearing control changed the underlying season state.

This decision approves the functional grouping and labels, not their placement,
appearance, responsive treatment, or Penpot layout.

### Approved functional decision — live story visibility

**Decision date:** 2026-08-24

The Live overview shows one compact **Last accepted beat** excerpt so the creator
can feel where the performance is without opening a reading surface. The full
live transcript opens only through a deliberate action.

While that transcript is open, automatic operational polling must not replace,
scroll, collapse, or reorder the displayed text. Newly accepted material raises
a **New material available** indicator; the creator chooses when to load it.
Refreshing the transcript preserves the creator's reading position and expanded
evidence wherever possible.

The excerpt and transcript contain accepted private story material only. Raw,
rejected, partial, diagnostic, role-sheet, prompt, and wellness material remain
outside this ordinary Live view.

### Approved functional decision — preparation interaction

**Decision date:** 2026-08-24

Prepare uses a **guided checklist with a focused step workspace**, not a rigid
wizard. All preparation steps and their status remain visible. The next
recommended step opens by default, while the creator may freely revisit any
completed or otherwise unlocked step.

Changing an earlier artifact visibly invalidates every dependent approval,
preflight result, generated artifact, or schedule preview. The dashboard shows
what became stale and why. Merely viewing a step or pressing a navigation
control never approves it or advances durable season state.

### Approved functional decision — Cast and Continuity placement

**Decision date:** 2026-08-24

Cast and Continuity will not become a seventh primary destination. Its material
is placed according to the task being performed:

- **Prepare** owns editable creator-approved character cards before green;
- **Review** owns the durable Cast and Continuity record: approved cards, cast
  status, visible canon, unresolved continuity, and memory-version metadata;
- **Diagnostics** owns private role sheets, context, and prompt provenance;
- **Live** shows compact cast status and links to the relevant Review or
  Diagnostics record.

After green, the approved character card remains readable in Review. Any later
change requires an explicit versioned workflow; Live or Diagnostics cannot
silently edit identity or continuity.

### Approved functional decision — first Diagnostics boundary

**Decision date:** 2026-08-24

The first Diagnostics implementation is tightly scoped to explaining one model
call and how its output became—or failed to become—accepted evidence.

It includes:

- search and filters for season, run, character, purpose, status, and attempt;
- backend/model binding, timing/latency, finish state, and transport/parse error;
- `NATIVE_SCHEMA` versus `TAGGED_FALLBACK`;
- character-card, role-sheet, prompt/template, context, and schema version
  identifiers;
- raw, parsed, validated, accepted, and rendered output stages;
- correction attempts and validator findings;
- a link from accepted output to its causal position in Review.

It explicitly excludes model reruns, benchmark/resource graphs, bulk comparison
workspaces, automated model selection, and raw wellness text. Those exclusions
keep Diagnostics read-only and prevent the first slice from becoming a general
model laboratory.

### Approved functional decision — responsive capability

**Decision date:** 2026-08-24

Desktop is the full workspace, but narrow widths remain **operationally
complete** rather than becoming a limited companion view. Responsive design may
change density and sequence, not remove lifecycle or safety capability.

At narrow widths:

- every lifecycle and safety-critical action remains available;
- Prepare presents one focused step at a time while retaining the full
  checklist and invalidation evidence;
- Review remains suitable for sustained transcript and diary reading;
- Diagnostics transforms side-by-side stages into clearly labeled tabs or a
  sequential comparison;
- dense tables become cards or disclosure lists rather than horizontal scroll;
- privacy state, completion evidence, action consequences, and confirmation
  requirements remain visible.

Desktop and narrow layouts share the same durable read models and commands. A
responsive rearrangement cannot change what action is valid or what evidence is
required.

### Approved functional decision — Penpot fixture privacy

**Decision date:** 2026-08-24

Penpot uses a synthetic but structurally realistic rehearsal season by default.
It reproduces useful S01 evidence shapes—including partial runs, repeated turns,
schema failure, correction, recovery, held diaries, and long transcripts—without
copying private diaries, prompts, role sheets, hidden plans, or wellness text.

A specific S01 excerpt may enter the design file only through a later explicit
creator decision. Synthetic content remains the default even though the Penpot
instance is private.

## 2. Current functional baseline

The current authenticated dashboard provides:

- a one-page operational snapshot;
- season, run, work-queue, cast, diary, recovery, and publication counts;
- next scheduled run and unread-notification counts;
- explicit recovery choices when a run is `RECOVERY_REQUIRED`;
- a private diary desk;
- an owner-only end-of-day review;
- explicit content reloads that preserve open reading panes;
- scrypt login, owner sessions, CSRF protection, and private-root containment.

The current surface does not yet provide:

- a guided pre-season workflow;
- a visible production-versus-sandbox identity;
- notification details or a mark-read workflow;
- full pause, resume, private-end, and close-state journeys;
- causal day-review chronology;
- visible turn count, completion reason, actual execution time, or fiction time;
- beginning state, accepted changes, final state, and unresolved questions per
  run;
- character-card continuity from planning through role-sheet generation;
- model-call and structured-output diagnostics;
- a complete publication review journey in the browser;
- a stable place for prior seasons, handoffs, and private archives.

The current design is therefore a useful status page, not yet the complete
operator application.

## 3. Functional north star

At any moment, the dashboard should answer five questions without requiring the
creator to inspect SQLite, the terminal, or raw files:

1. **Where am I?** Production or sandbox, season, lifecycle stage, day, and slot.
2. **What is the system doing?** Worker health, current durable work, model-call
   phase, and freshness of the displayed evidence.
3. **What needs me?** One prioritized attention inbox with the reason and safe
   choices.
4. **What happened?** Causally ordered story, state, diary, and system evidence.
5. **What is the next safe action?** A state-valid action with its consequence
   explained before execution.

The interface should feel like a guided studio workflow with a control room
available when needed, not a database browser and not a wall of metrics.

## 4. Functional principles

### 4.1 Truth before reassurance

- `COMPLETED` is never shown without completion reason and accepted turn count.
- Missing data is labeled unavailable or not recorded, never displayed as zero.
- Scheduled, actual, fictional, and display time remain distinct.
- The dashboard identifies its data root, environment, last successful read,
  and stale/disconnected state.
- Story chronology follows accepted sequence, never lexical IDs or file order.

### 4.2 One durable source of truth

- The dashboard reads the same durable records that drive the worker.
- It never maintains a competing browser-only season state.
- Every mutation uses a typed, replay-safe application command.
- Each completed action returns a durable receipt: request ID, result, timestamp,
  and resulting aggregate version.

### 4.3 Read-only by default

- Opening a page, artifact, transcript, role sheet, diagnostic, or raw output
  never changes canon, privacy, publication eligibility, or wellness state.
- Controls appear only when their command preconditions are satisfied.
- Consequential actions explain what will and will not happen.
- Ending and publishing are always separate actions.

### 4.4 Calm progressive disclosure

- The default surface presents operator meaning, not storage internals.
- Technical provenance lives in an explicitly entered Diagnostics area.
- Raw model material stays collapsed until intentionally opened.
- Automatic polling may update operational indicators but never replace text the
  creator is reading.

### 4.5 Visible privacy boundaries

- Private, diagnostic, held, noncanon, publishable, and published material are
  visibly distinct states.
- Raw wellness text is absent from ordinary pages and diagnostic summaries.
- A special existing owner-only disclosure may expose a selected held attempt,
  but reading it does not accept or clear it.
- Hidden season direction never appears in ordinary actor or review views.

### 4.6 Sandbox cannot masquerade as production

- `SANDBOX` or `PRODUCTION` remains visible in the global shell at all times.
- The active data root and season are inspectable.
- Sandbox fixtures use a separate configured root and cannot issue commands
  against the production root.
- Screenshots and exported rehearsal evidence retain the environment label.

## 5. Lifecycle model

The dashboard should organize work around the season lifecycle rather than one
long page:

```text
No season
   |
   v
Prepare: idea -> opening -> character cards -> models -> preflight
   |                                              |
   | revise                                       v
   +------------------------------------------ Green gate
                                                  |
                                                  v
Live: armed -> running <-> paused -> day closure -> next day
                  |
                  +-> model wait -> recovery choice
                                      | retry / skip
                                      +--------------> running
                                      |
                                      + end
                                        |
                                        v
Private close -> handoff/archive -> optional publication review -> published
```

Review and Diagnostics are evidence views alongside the lifecycle. Opening
either one does not advance it.

## 6. Approved information architecture

The creator approved this stable navigation model:

| Destination | Primary question | Lifecycle availability |
|---|---|---|
| **Home** | What needs me, and what happens next? | Always |
| **Prepare** | Is this season ready to green? | Editable before green; readable afterward |
| **Live** | What is running, waiting, or blocked? | Armed through private close |
| **Review** | What actually happened in the fiction and diaries? | As evidence becomes available |
| **Diagnostics** | Why did the system/model produce this result? | Explicit owner-only mode |
| **Seasons** | What is private, closed, archived, or publishable? | Always |

The shell also carries a global season selector and an attention drawer. The
selected season is one explicit context shared by all destinations; pages never
silently switch seasons.

### Global shell

Always visible:

- product identity;
- `PRODUCTION` or `SANDBOX` environment badge;
- selected season and lifecycle status;
- service connection and evidence freshness;
- worker state;
- unread attention count;
- owner/session menu.

The global shell should not contain destructive actions.

### Attention drawer

The attention drawer combines durable operator notifications, recovery
requests, preflight blockers, incomplete day closure, and failed projections.

Each item shows:

- what happened;
- when and where it happened;
- whether work is still proceeding or blocked;
- the evidence available;
- the valid choices;
- what each choice changes.

Marking a notification read updates `read_at` only. It never deletes the record
or resolves the underlying condition.

## 7. Screen responsibilities

### 7.1 Home — operator briefing

Home is a concise answer-first briefing, not the current collection of every
panel.

Required sections:

1. **Current truth** — environment, season, lifecycle state, day/slot, worker
   state, and last verified update.
2. **Needs you** — the highest-priority unresolved operator item, followed by the
   remaining inbox.
3. **Next safe action** — one state-derived recommendation with a link to the
   relevant workflow; it is not executed from the card.
4. **Season progress** — schedule and day progress without implying creative
   success from completed counts.
5. **Recent durable activity** — commands, state transitions, model failures,
   recovery decisions, day closure, and artifact projection.
6. **Health summary** — database integrity, worker lease, model availability,
   queue, artifact outbox, and storage reachability.

Story text, raw prompts, model identities, and role sheets do not belong on
Home.

### 7.2 Prepare — manual pre-season workspace

Prepare is a guided, revisable checklist with one focused step workspace. All
steps and statuses remain visible; the next recommended step opens by default.
Completed and unlocked steps may be revisited, while dependent later steps are
visibly invalidated when a required earlier artifact changes.

Recommended steps:

1. **Season idea** — capture the premise and create the draft season.
2. **Opening** — review/revise set, setting, cast roster, and world rules.
3. **Character cards** — approve stable identity, specified pronouns, public
   brief, occupation/skills, voice anchors, and habits for each character.
4. **Model assignment** — choose private director and actor bindings from
   benchmark evidence; assignments remain explicit creator choices.
5. **Preflight** — run named checks and show pass/fail evidence individually.
6. **Private preparation** — generate versioned role sheets and orientation,
   showing the approved character card beside the generated extension.
7. **Schedule preview** — show all original dates, Pacific times, fiction slots,
   diary expectations, and the isolated data root.
8. **Green review** — summarize exactly what will be locked, queued, kept
   private, and scheduled before the creator enters the final confirmation.

Every step needs:

- status: not started, draft, blocked, ready for review, approved, invalidated;
- the current artifact version;
- evidence and validation messages;
- an explicit revise or approve action;
- a durable history of replaced versions;
- a clear next step.

Checklist navigation itself is read-only. Approval, generation, preflight, and
green remain separate labeled commands; there is no generic Next action that
mutates the season.

`green` is never bundled with preflight or orientation. It is a separate,
consequential creator decision.

### 7.3 Live — performance supervision

Live shows the autonomous worker without requiring the dashboard to remain
open.

Required sections:

- current season/day/slot and fictional time;
- scheduled time, actual start, elapsed duration, and delay;
- current durable work item and worker lease/heartbeat;
- current run phase, round, accepted turn count, and active model-call purpose;
- next scheduled run and downstream queue;
- diary/day-closure state;
- pause, resume, and private-end controls only when valid;
- a recovery card when progress is blocked;
- one compact Last accepted beat excerpt;
- a deliberately opened full transcript that never redraws while being read;
- a New material available indicator and creator-triggered transcript refresh.

Recovery choices remain `retry`, `skip`, or `end`. The screen must explain that:

- retry preserves earlier attempts and enqueues a new attempt;
- skip preserves the scheduled ledger position and resumes later work;
- end begins private closure and does not publish or delete anything.

### 7.4 Review — story and diary evidence

Review is optimized for sustained reading and qualitative model assessment.
It has three related views:

#### Day

- day/season selector with original date;
- morning, afternoon, and evening run cards;
- scheduled and actual time, delay, status, completion reason, accepted round
  and turn count, corrections, and recovery markers;
- non-secret fiction-clock framing;
- causally ordered transcript with the orchestrator beat before the actor turns
  it prompted;
- beginning state, accepted changes, final state, and unresolved questions;
- explicit missing/partial evidence notices.

#### Diaries

- all character-day obligations and statuses;
- accepted entries and held private attempts clearly distinguished;
- late and missing provenance;
- stable expanded reading state;
- explicit private raw-output disclosure where already permitted;
- no acceptance, wellness clearance, or publication mutation from reading.

#### Cast and continuity

- creator-approved character cards;
- public status and season participation;
- visible canon and unresolved continuity questions;
- actor-local memory version and summary metadata without exposing it to peer
  actors;
- links into explicit Diagnostics for role-sheet or prompt provenance.

Review filters should include day, run, character, status, and evidence type.
They should not change the underlying record.

### 7.5 Diagnostics — explicit evidence laboratory

Diagnostics is a separate owner-only mode with a visible privacy warning. It is
for explaining a result, not operating the story.

Required capabilities:

- filter by season, run, character, call purpose, attempt, status, and error;
- show backend/model binding and locked manifest version;
- show call start/end, cold/warm and total latency, finish reason, usage, and
  transport error;
- show prompt, template, context, role-sheet, character-card, and schema version
  identifiers;
- identify `NATIVE_SCHEMA` versus `TAGGED_FALLBACK`;
- compare raw, parsed, validated, accepted, and rendered output side by side;
- show correction attempts and the rule that triggered them;
- show near-verbatim repetition, first-person identity, pronoun, role, and canon
  review findings without silently rewriting creative text;
- link each accepted output back to its place in Review.

The approved first slice implements the call-focused subset above. Benchmark
graphs, bulk comparisons, resource monitoring, and rerun controls are deferred.

Opening Diagnostics or inspecting an artifact must never rerun a model, accept
text, change canon, resolve recovery, mark wellness reviewed, or publish.

Raw wellness text remains outside the default diagnostics payload. A separately
confirmed owner-only disclosure may show one selected held artifact under the
existing private-review boundary.

### 7.6 Seasons — private closure, archive, and release

Seasons holds the durable list of current and prior seasons. Each season shows:

- lifecycle and privacy status;
- start/end and schedule provenance;
- cast, completed/skipped/partial runs, diaries, and unresolved operator items;
- handoff/archive availability;
- publication versions, if any.

Private close is a guided journey:

1. inspect a read-only snapshot of season, runs, queue, recovery, model calls,
   days, diaries, cast, notifications, and database integrity;
2. explain incomplete work and what private closure will do;
3. confirm the season ID and private-end intent;
4. execute the typed command;
5. show the durable receipt and resulting closure/handoff work;
6. verify the terminal private state.

Publication is a separate later journey:

1. choose one closed season explicitly;
2. review privacy, wellness, consent, and each flagged diary;
3. preview the exact allowlisted public projection;
4. confirm `publish Sxx` separately;
5. show the immutable version and manifest hash.

The normal close action must never default into publication.

## 8. Action-safety tiers

| Tier | Examples | Interaction requirement |
|---|---|---|
| **Read** | open transcript, filter calls, refresh, inspect artifact | Immediate; no mutation |
| **Light** | mark notification read, save an unapproved draft | Clear result and undo/revise path |
| **Workflow** | approve character card, run preflight, pause/resume, retry | Consequence summary plus confirmation |
| **Consequential** | skip run, green season, end season, publish | Typed season/run confirmation, impact preview, command receipt |

Buttons should be disabled with an explanation when a precondition is not met,
not merely hidden. A disabled action can teach the operator what evidence is
missing; an impossible action should not be rendered at all.

## 9. Required system states

Every primary screen must be designed and tested for:

- authenticated and unauthenticated;
- first use / no seasons;
- production and sandbox;
- loading;
- connected and fresh;
- stale but readable;
- disconnected;
- partial or missing evidence;
- invalid or escaped artifact path;
- no active season;
- draft / awaiting green;
- armed / running / paused;
- waiting for model / recovery required;
- closing / complete / awaiting publication review / published;
- command accepted, replayed, rejected, and conflicted;
- narrow viewport and keyboard-only use.

The interface must distinguish “nothing exists,” “nothing is due,” “data is
unavailable,” and “the query failed.”

## 10. Functional data contracts

Exact route names remain an implementation decision, but the dashboard needs
stable read models for:

- global environment and service health;
- season operator summary and lifecycle preconditions;
- pre-season checklist and versioned artifacts;
- schedule, work queue, worker lease, and current run progress;
- notifications and attention items;
- chronological day/run review;
- diaries and private held attempts;
- cast cards, canon, and memory-version metadata;
- model-call diagnostics and transformation stages;
- closure/handoff status;
- publication review and immutable exports;
- durable activity and command receipts.

Chronological turn records need an accepted sequence independent of lexical
`turn_id`. Each run review needs at least:

- run, day, slot, and schedule identity;
- scheduled and actual timestamps;
- fiction-clock label;
- status and completion reason;
- expected and accepted round/turn counts;
- accepted sequence, speaker/purpose, disposition, correction/recovery marker,
  and artifact reference;
- beginning/final state and accepted changes when those ledgers exist.

Every state-changing request needs:

- explicit season context;
- aggregate version or equivalent stale-write guard;
- unique request ID;
- typed command intent;
- stable success/replay/rejection response;
- durable activity record.

## 11. Privacy and visibility matrix

| Information | Home/Live | Prepare | Review | Diagnostics | Public export |
|---|---:|---:|---:|---:|---:|
| Season/run status | Yes | Yes | Yes | Yes | Allowlisted only |
| Creator-approved character card | Summary | Full | Full | Full | Only if explicitly public |
| Model identity | No | Assignment step | No | Yes | Never |
| Private role sheet | No | Explicit preparation review | No | Yes | Never |
| Hidden direction | No | No | No | Explicit provenance only | Never |
| Raw prompt/output | No | Explicit preparation evidence | Selected held diary only | Yes, except wellness default | Never |
| Raw wellness text | No | No | Explicit selected disclosure only | No default payload | Never |
| Accepted script/diary | Summary only | No | Yes | Yes | Allowlisted by release gate |

This matrix is a product boundary, not merely a visual preference.

## 12. Functional implementation slices after Penpot

The approved dashboard should be implemented in vertical slices that remain
usable and testable:

### Slice 0 — operational prerequisite

- inspect authoritative S01 Linux state;
- execute and verify the already approved private season end through the typed
  command path;
- preserve all private evidence and keep publication separate.

This is an operational action, not part of the Penpot or local UI build.

### Slice 1 — trustworthy shell and read models

- global environment/season identity;
- lifecycle-aware navigation;
- freshness, worker, and health truth;
- attention details and mark-read behavior;
- no new consequential controls yet.

### Slice 2 — review truth

- accepted sequence and causal transcript;
- run completion evidence and fiction clock;
- stable day and diary reading;
- partial/missing evidence states;
- cast and continuity view.

### Slice 3 — diagnostics

- model-call list and filters;
- raw/parsed/accepted/rendered comparison;
- schema path, versions, latency, correction, and validation evidence;
- explicit private boundaries.

### Slice 4 — pre-season workspace

- draft/revision checklist;
- character cards;
- model assignment and preflight evidence;
- role-sheet/orientation review;
- schedule preview and green gate;
- separate sandbox identity.

### Slice 5 — live operation and recovery

- live run/work/worker state;
- pause/resume/private-end commands;
- recovery choices with impact summaries and receipts;
- explicit non-refreshing evidence pane.

### Slice 6 — closure, archive, and publication

- private-close snapshot and verification;
- handoff/archive access;
- complete privacy/wellness/consent publication workflow;
- immutable publication receipt.

### Slice 7 — one-day acceptance support

- isolated one-day sandbox fixture;
- operator runbook evidence export;
- complete three-run, four-diary, day-close, next-direction review;
- creator acceptance record;
- no template editor until this slice establishes the stable workflow.

## 13. Functional acceptance scenarios

Before implementation is considered ready for the one-day rehearsal, the
creator must be able to complete these scenarios without the terminal or SQLite:

1. understand a healthy idle system and its next scheduled work;
2. distinguish production from sandbox at every screen;
3. prepare a season from idea through the separate green decision;
4. see why a preparation step is blocked or invalidated;
5. follow a normal run without keeping the browser open;
6. read a day in causal order with completion and time evidence;
7. keep a long diary or transcript open while status polling continues;
8. diagnose malformed structured output without changing the story;
9. distinguish a slow call, transport failure, parse failure, correction, and
   accepted result;
10. resolve recovery through retry, skip, or private end with a durable receipt;
11. mark a notification read without deleting it or resolving its cause;
12. close a season privately without publishing;
13. preview and publish only through a separate season-qualified review;
14. reconnect after stale/disconnected state without losing reading context;
15. complete all critical paths by keyboard at desktop and narrow widths.

## 14. Penpot collaboration plan

The detailed screen inventory and synthetic fixture are maintained in
[PENPOT_DASHBOARD_BRIEF.md](PENPOT_DASHBOARD_BRIEF.md).

Penpot begins only after the functional questions in this draft are resolved.
The design file should contain:

1. **Decisions** — approved functional principles, vocabulary, privacy rules,
   and unresolved questions;
2. **Flow map** — prepare, live/recovery, review/diagnostics, close, and publish;
3. **Content model** — real field inventory and priority, without production
   secrets;
4. **Low-fidelity desktop** — one frame per primary screen and critical state;
5. **Low-fidelity narrow** — the same tasks at the smallest supported width;
6. **Components** — navigation, environment badge, state badge, attention item,
   timeline, transcript turn, evidence disclosure, command confirmation, and
   receipt;
7. **High-fidelity screens** — only after low-fidelity flows are approved;
8. **Prototype paths** — pre-season, normal day review, parse-failure diagnosis,
   recovery, private close, and publication separation;
9. **Handoff** — states, behavior notes, content rules, and responsive behavior.

Recommended collaborative design order:

1. global shell and Home;
2. Day Review, because it carries the strongest S01 evidence;
3. Diagnostics;
4. Prepare;
5. Live and Recovery;
6. Seasons, private close, and Publication;
7. narrow-width and exceptional states;
8. visual language and final component polish.

Use synthetic fixture content in Penpot by default so private S01 diary, role,
prompt, and wellness material does not spread into a design artifact. The
creator may explicitly approve selected S01 excerpts if their realism is worth
that privacy tradeoff.

## 15. Resolved functional decisions before Penpot

The creator approved:

1. a guided studio workflow with control-room density limited to Live and
   Diagnostics;
2. six stable destinations: Home, Prepare, Live, Review, Diagnostics, and
   Seasons;
3. one Last accepted beat on Live plus a deliberately refreshed stable
   transcript;
4. a guided preparation checklist with one focused, revisable workspace;
5. lifecycle-specific Cast and Continuity placement without another primary
   destination;
6. a call-focused, read-only first Diagnostics slice;
7. operationally complete narrow layouts;
8. synthetic Penpot fixture content by default.

These decisions approve the functional screen map for collaborative Penpot
work. They do not approve any particular layout, component appearance, visual
language, prototype, or implementation.

## 16. Approved first Penpot checkpoint

**Decision date:** 2026-08-24

The creator approved the first low-fidelity Penpot checkpoint in full. The
approved foundation includes the nine-page file organization, lifecycle flow,
global-shell information priority, desktop and narrow Home, desktop and narrow
Day Review, and navigation hypothesis A: a stable left rail on desktop and
persistent bottom navigation on narrow screens.

This approval establishes hierarchy, flow, and navigation placement for later
screens. It does not approve visual polish, high-fidelity components, remaining
screen states, or dashboard implementation.

## 17. Approved Prepare Penpot checkpoint

**Decision date:** 2026-08-24

The creator approved the low-fidelity Prepare interaction in full. The approved
pattern keeps all eight preparation steps visible, opens one focused workspace,
keeps checklist navigation read-only, explains approval effects and blocked
prerequisites, previews every downstream invalidation before an earlier
revision is saved, retains replaced versions, and preserves the same evidence
and actions at narrow width.

This approves Prepare's hierarchy and interaction behavior. It does not approve
the visual system, high-fidelity treatment, remaining dashboard screens, or
implementation.

## 18. Approved Diagnostics Penpot checkpoint

**Decision date:** 2026-08-24

The low-fidelity Diagnostics checkpoint contains one desktop and one narrow
call-detail frame. It tests the selected-call list/detail relationship,
identity and binding evidence, timing and artifact versions, the raw-to-rendered
sequence, schema failure and correction evidence, a return to the originating
Review position, and deliberate raw-artifact disclosure. It remains read-only,
uses only the synthetic rehearsal fixture, excludes raw wellness text, and
contains no rerun or model-selection controls.

The creator approved this low-fidelity Diagnostics interaction pattern in full.
The approval does not extend to the visual system, high-fidelity treatment, or
implementation.

## 19. Approved Live and Recovery Penpot checkpoint

**Decision date:** 2026-08-24

The low-fidelity Live and Recovery checkpoint contains healthy-running and
recovery-required frames at desktop and narrow widths. Healthy Live combines
current durable performance truth, worker/queue evidence, one Last accepted
beat, a stable transcript with creator-controlled refresh, and only currently
valid controls. Recovery Required anchors every choice to the last accepted
beat, links to the failed-call explanation, and states the distinct story,
schedule, privacy, and durability consequences of retry, skip, and private end
before submission.

The frames use only the synthetic rehearsal fixture. They do not preselect or
submit a recovery path, execute a command, publish, delete, or imply that
navigation resolves durable state. The creator approved this low-fidelity
interaction pattern in full. The approval does not extend to the visual system,
high-fidelity treatment, or implementation.

## 20. Approved Seasons and Publication Penpot checkpoint

**Decision date:** 2026-08-24

The low-fidelity Seasons checkpoint contains private-close and publication
frames at desktop and narrow widths. Private close begins from a versioned
read-only operational snapshot, preserves incomplete-work truth, explains what
will and will not happen, and requires the season-qualified private-end intent
before a durable receipt and terminal-state verification. Publication begins
later from an explicitly selected private-complete season, repeats privacy,
consent, held-diary, allowlist, and path checks, previews the exact public
projection and structural exclusions, and requires a distinct publish intent
before an immutable version, manifest hash, and receipt.

The frames use only the synthetic rehearsal fixture. They do not execute either
command, expose excluded source data, collapse private close into publication,
or imply that navigation mutates lifecycle state. The creator approved this
low-fidelity interaction pattern in full. The approval does not extend to the
visual system, high-fidelity treatment, or implementation.

## 21. Approved final low-fidelity system Penpot checkpoint

**Decision date:** 2026-08-24

The final low-fidelity foundation checkpoint contains three system boards:

1. **Content & Components** defines the common information order, reusable
   component families, privacy/disclosure defaults, four action-safety tiers,
   and narrow/keyboard rules.
2. **Prototype Paths** defines seven end-to-end journeys and their mutation
   boundaries without submitting any command.
3. **Exceptional States** defines loading, fresh, stale-readable,
   disconnected, partial/missing, no-season, invalid-path, command-conflict,
   and narrow/keyboard behavior.

Together, the boards require every task and exceptional state to name what is
true, what remains readable, what action is valid, what is blocked, and what
would happen next. Operational polling may refresh status chrome but must not
replace an open reading pane, form, selection, disclosure, or scroll position.

The source boards are
[`02-content-components.svg`](../../design/penpot/02-content-components.svg),
[`20-prototype-paths.svg`](../../design/penpot/20-prototype-paths.svg), and
[`20-exceptional-states.svg`](../../design/penpot/20-exceptional-states.svg). They use
only synthetic material and do not execute a command, approve visual styling,
or authorize implementation.

The creator approved this final low-fidelity checkpoint in full. The functional
model and complete low-fidelity interaction architecture are now frozen as the
baseline for visual-language and high-fidelity work. Typography, color,
spacing, shape, iconography, and surface treatment remain open; hierarchy,
workflow consequences, privacy boundaries, stable-reading behavior, and action
safety do not change without a new explicit creator decision.

## 22. Approved visual-language direction — Warm Instrument

**Decision date:** 2026-08-24

Three visual directions apply the same frozen Home/Day Review composition:

1. **A · Warm Instrument** combines a warm paper reading surface with a dark
   operational rail. It is the recommended starting point for long-form reading,
   calm supervision, and creative warmth.
2. **B · Molten Observatory** evolves the existing dark console with restrained
   geologic light used only for focus and consequence. It offers the strongest
   continuity with the current interface and strongest Live/Diagnostics mood.
3. **C · Quiet Archive** uses cool paper, explicit record syntax, minimal
   shadow, and editorial precision. It offers the quietest archive scan but has
   the greatest risk of feeling administrative.

The comparison board and three detail boards define palette, type roles,
surface treatment, shape/rhythm, state colors, action treatment, and one
signature gesture per direction. The assets are
[`30-visual-directions.svg`](../../design/penpot/30-visual-directions.svg),
[`30-direction-a-warm-instrument.svg`](../../design/penpot/30-direction-a-warm-instrument.svg),
[`30-direction-b-molten-observatory.svg`](../../design/penpot/30-direction-b-molten-observatory.svg),
and
[`30-direction-c-quiet-archive.svg`](../../design/penpot/30-direction-c-quiet-archive.svg).

At assembly, this direction round used only synthetic content and did not
itself approve a visual system, final fonts, high-fidelity screens, or
implementation. It awaited the creator's selection or requested hybrid.

The creator selected **A · Warm Instrument**. Its warm paper reading surface,
dark operational rail, calm supervision tone, and creative-field-notebook plus
instrument-panel relationship are now the active visual direction. Molten
Observatory and Quiet Archive remain comparison history. Exact tokens,
component styling, responsive application, final fonts, high-fidelity screens,
and implementation still require later approval.

## 23. Approved Warm Instrument visual system

**Decision date:** 2026-08-24

Three boards refine the selected Warm Instrument direction:

1. **Foundations** proposes exact color roles, type roles and fallbacks,
   spacing, radii, depth, semantic states, focus, motion, and accessibility
   behavior.
2. **Components** applies the system to shell/context, freshness, four action
   tiers, control states, story/evidence, decision impact, typed intent,
   durable receipts, and exceptional states.
3. **Responsive** demonstrates desktop and 390-pixel narrow application without
   reducing safety, privacy, evidence, or consequence capability.

The exact proposed core palette is `#E7E1D5` canvas, `#F3EFE6` paper,
`#FAF7F0` surface, `#26302D` charcoal, `#222724` ink, `#6C6B63` muted, and
`#C56F42` ember. Semantic state pairs and their calculated contrast are defined
on the foundations board. Ember remains a selection and creative/consequence
boundary signal, not a generic health or decorative glow.

The proposed type roles are Inter/system UI, Charter/Georgia authored reading,
and SF Mono/Menlo operational evidence. This checkpoint does not choose font
assets or loading strategy. The proposed responsive switch is a rail at 920
pixels and above and bottom navigation below 920 pixels, subject to real-content
testing.

The assets are
[`30-warm-instrument-foundations.svg`](../../design/penpot/30-warm-instrument-foundations.svg),
[`30-warm-instrument-components.svg`](../../design/penpot/30-warm-instrument-components.svg),
and
[`30-warm-instrument-responsive.svg`](../../design/penpot/30-warm-instrument-responsive.svg).
They use synthetic S02 content and do not create high-fidelity screens, connect
to production state, execute commands, or authorize implementation. This
checkpoint was approved by the creator in full.

The palette roles, typography roles and fallbacks, spacing/radius/depth scales,
semantic states, action tiers, focus and motion rules, ember-boundary gesture,
and desktop/narrow composition rules are now frozen as the baseline for
high-fidelity work. Calculated contrast is design evidence rather than rendered
implementation or human accessibility evidence. Font assets/loading,
keyboard/touch behavior, and accessibility acceptance remain later verification
gates. Any visual-system change requires a new explicit creator decision.

## 24. Approved representative Home and Day Review high-fidelity checkpoint

**Assembly date:** 2026-08-24

Four high-fidelity screens apply the frozen Warm Instrument system to the first
representative product slice:

1. desktop Home tests calm supervision, selected context, freshness, durable
   progress, one Last accepted beat, next slot/cast, and private system notes;
2. desktop Day Review tests a run timeline, stable authored-text reading, private
   diary access, evidence provenance, and deliberate loading of newer accepted
   material;
3. narrow Home preserves the same essential truth and Day Review entry under
   persistent bottom navigation;
4. narrow Day Review preserves run selection, saved position, stable reading,
   provenance, privacy exclusion, and creator-controlled refresh.

The assets are
[`40-home-desktop.svg`](../../design/penpot/40-home-desktop.svg),
[`40-day-review-desktop.svg`](../../design/penpot/40-day-review-desktop.svg),
[`40-home-narrow.svg`](../../design/penpot/40-home-narrow.svg), and
[`40-day-review-narrow.svg`](../../design/penpot/40-day-review-narrow.svg). They were
XML-validated, rendered for visual inspection, and placed on the `40 — High-fi`
Penpot page. They use synthetic S02 content, do not connect to production state,
do not execute commands, and show no raw wellness text. At assembly, this
checkpoint awaited creator review. The remaining workflows and implementation
stayed outside the approval boundary.

**Decision date:** 2026-08-24

The creator approved all four Home and Day Review compositions. Their
calm-supervision hierarchy, responsive navigation, stable authored-text reading,
saved position, creator-controlled refresh, evidence provenance, and private
diary boundary are frozen as the representative high-fidelity reference. This
approval does not authorize implementation, approve unrepresented workflows,
or replace later rendered, interactive, and accessibility acceptance.

## 25. Approved Prepare high-fidelity checkpoint

**Assembly date:** 2026-08-24

Four high-fidelity Prepare screens apply the frozen Warm Instrument system to
the most consequential pre-season interaction:

1. desktop Character Cards keeps the full eight-step checklist beside one
   focused card, explicit prerequisite, durable history, approval impact, and
   separate save/review actions;
2. desktop Opening Revision previews six downstream effects before a save and
   distinguishes stale evidence from relocked Green review;
3. narrow Character Cards preserves the same checklist, focused work, evidence,
   consequences, and actions in a vertically sequenced workspace;
4. narrow Opening Revision preserves all affected steps, the full dependency
   explanation, current approved truth, durable result, and explicit save
   boundary.

The assets are
[`40-prepare-character-cards-desktop.svg`](../../design/penpot/40-prepare-character-cards-desktop.svg),
[`40-prepare-invalidation-desktop.svg`](../../design/penpot/40-prepare-invalidation-desktop.svg),
[`40-prepare-character-cards-narrow.svg`](../../design/penpot/40-prepare-character-cards-narrow.svg),
and
[`40-prepare-invalidation-narrow.svg`](../../design/penpot/40-prepare-invalidation-narrow.svg).
They were XML-validated, rendered for visual inspection, and placed on the
`40 — High-fi` Penpot page. They use synthetic S02 content, connect to no
production state, and execute no command. At assembly, this checkpoint awaited
creator approval.

**Decision date:** 2026-08-25

The creator approved all four Prepare compositions. Their entire-checklist
visibility, focused Character Card work, explicit prerequisites and approval
effects, durable version history, current-approved-truth treatment, downstream
invalidation explanation, and separate navigation/save/review boundaries are
frozen as the Prepare high-fidelity reference. This approval does not authorize
implementation or later workflow changes.

## 26. Approved Live and Recovery high-fidelity checkpoint

**Assembly date:** 2026-08-25

Four high-fidelity Live screens apply the frozen Warm Instrument system to
ordinary autonomous supervision and the creator-decision boundary:

1. desktop healthy Live shows current performance, timing, accepted progress,
   worker/queue truth, day completion, one Last accepted beat, a stable
   transcript, and only valid controls;
2. desktop Recovery Required shows the safe stop, failure stage, durable queue
   effect, exact last accepted beat, and equal unselected retry/skip/private-end
   paths;
3. narrow healthy Live preserves the same story, evidence, timing, queue,
   controls, and stable-reading capability in a vertically sequenced workspace;
4. narrow Recovery Required preserves every consequence, the Diagnostics link,
   queue effect, no-choice state, privacy boundary, and durable-receipt promise.

The assets are
[`40-live-running-desktop.svg`](../../design/penpot/40-live-running-desktop.svg),
[`40-live-recovery-desktop.svg`](../../design/penpot/40-live-recovery-desktop.svg),
[`40-live-running-narrow.svg`](../../design/penpot/40-live-running-narrow.svg), and
[`40-live-recovery-narrow.svg`](../../design/penpot/40-live-recovery-narrow.svg).
They were XML-validated, rendered for visual inspection, and placed on the
`40 — High-fi` Penpot page. They use synthetic S02 content, connect to no
production state, preselect no path, and execute no command. At assembly, this
checkpoint awaited creator approval.

**Decision date:** 2026-08-25

The creator approved all four Live and Recovery compositions. Their calm
autonomous-supervision hierarchy, worker/queue evidence, stable reading,
creator-controlled loading, exact last-accepted causal anchor, failure-stage
evidence, equal unselected recovery paths, and consequence-first decision
boundary are frozen as the Live/Recovery high-fidelity reference. This approval
does not authorize implementation or a recovery command.

## 27. Approved Diagnostics high-fidelity checkpoint

**Assembly date:** 2026-08-25

Two high-fidelity Diagnostics screens apply the frozen Warm Instrument system
to one owner-only, read-only call explanation:

1. desktop Diagnostics keeps the run's call list alongside selected-call
   identity, timing and finish evidence, raw-to-rendered stages, a deliberately
   opened synthetic raw excerpt, validator finding, linked correction attempt,
   version provenance, and causal return to Review;
2. narrow Diagnostics preserves the same explanation as a vertical sequence,
   keeps raw output collapsed behind deliberate disclosure, and retains the
   failure, correction, provenance, and exact accepted return point.

The assets are
[`40-diagnostics-call-desktop.svg`](../../design/penpot/40-diagnostics-call-desktop.svg)
and
[`40-diagnostics-call-narrow.svg`](../../design/penpot/40-diagnostics-call-narrow.svg).
They were XML-validated, rendered for visual inspection, and placed on the
`40 — High-fi` Penpot page. They use synthetic S02 content, connect to no
production state, reveal no private role-sheet contents or raw wellness text,
and execute no command. Reruns, benchmarks, bulk comparison, and automated
model selection remain outside this read-only first slice. At assembly, this
checkpoint awaited creator approval.

**Decision date:** 2026-08-25

The creator approved both Diagnostics compositions. Their call-focused
identity, timing and finish evidence, raw-to-rendered causal sequence,
deliberate disclosure boundary, validator and correction history, version
provenance, exact return-to-Review point, and read-only operating boundary are
frozen as the Diagnostics high-fidelity reference. This approval does not
authorize implementation or model operation.

## 28. Approved Seasons and Publication high-fidelity checkpoint

**Assembly date:** 2026-08-25

Four high-fidelity Seasons screens apply the frozen Warm Instrument system to
the two separate terminal lifecycle journeys:

1. desktop Private Close leads with a versioned operational snapshot, names
   incomplete work, distinguishes effects and non-effects, requires exact
   season-qualified private intent, and previews the durable closure sequence;
2. desktop Publication starts only from a selected `PRIVATE_COMPLETE` season,
   repeats privacy and consent gates, shows the exact allowlisted projection
   beside structural exclusions, and requires a separate publish intent;
3. narrow Private Close preserves the complete snapshot, unresolved-work
   truth, effect boundary, exact intent, and terminal verification sequence;
4. narrow Publication preserves every gate, public preview, exclusion,
   separate intent, immutable version, manifest, and receipt boundary.

The assets are
[`40-seasons-private-close-desktop.svg`](../../design/penpot/40-seasons-private-close-desktop.svg),
[`40-seasons-publication-desktop.svg`](../../design/penpot/40-seasons-publication-desktop.svg),
[`40-seasons-private-close-narrow.svg`](../../design/penpot/40-seasons-private-close-narrow.svg),
and
[`40-seasons-publication-narrow.svg`](../../design/penpot/40-seasons-publication-narrow.svg).
They were XML-validated, rendered for visual inspection, and placed on the
`40 — High-fi` Penpot page. They use synthetic S02 content, connect to no
production state, prefill no intent, expose no excluded source data, and
execute no command. Private close cannot publish; publication cannot alter the
private archive. At assembly, this checkpoint awaited creator approval.

**Decision date:** 2026-08-25

The creator approved all four Seasons and Publication compositions. Their
versioned closure snapshot, unresolved-work preservation, effect and non-effect
boundary, exact private intent, terminal verification, separate release
eligibility, repeated privacy and consent checks, exact allowlisted preview,
structural exclusions, distinct publish intent, and immutable-result evidence
are frozen as the Seasons/Publication high-fidelity reference. This completes
and freezes the dashboard's high-fidelity design. It does not authorize
implementation or either consequential command.

## 29. Scope concern

**Concern:** the dashboard can expand into the planner, control room, model lab,
archive, template editor, and public CMS simultaneously.

**Confidence:** high

**Severity:** high

The recommended boundary is to plan the whole lifecycle now but implement it in
the vertical slices above. The public website remains separate, and the
template editor remains deferred until the manual one-day workflow demonstrates
stable reusable steps.
