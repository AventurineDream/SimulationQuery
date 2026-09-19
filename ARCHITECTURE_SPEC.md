# AI Improv Troupe — Architecture Specification

**Status:** draft v1
**Normative product source:** [PRODUCTION_SPEC.md](PRODUCTION_SPEC.md)
**Target:** private seven-day pilot on a Linux server, controlled from a Mac browser

This document translates the production specification into an implementable software architecture. Where this document and the production specification disagree, the production specification wins.

## 1. Architectural goals

The system must:

1. Run a seven-day, 21-run season without requiring the dashboard to remain open.
2. Preserve exactly which scheduled run, model call, turn, diary, and intervention occurred.
3. Resume after process or server failure without duplicating accepted work.
4. Keep private plans, prompts, model identities, wellness records, and audit material out of public output.
5. Give the creator readable files without sacrificing transactional state and idempotency.
6. Keep model backends replaceable until benchmarking determines the actual 8B and 20B models.
7. Treat wellness signals as first-class control events rather than ordinary story text.
8. Remain small enough for one person to understand, audit, operate, and improve.

## 2. Architecture summary

Use a **durable modular monolith** running as one supervised Linux service.

```text
Mac browser
    |
    | authenticated private-network HTTP + SSE
    v
+---------------------------------------------------------+
| improv-server                                           |
|                                                         |
|  Dashboard/API  ->  Command handlers  ->  State machine |
|       |                    |                    |         |
|       |                    v                    v         |
|       |              Durable work queue    SQLite        |
|       |                    |             + event/outbox   |
|       |                    v                    |         |
|       |            Season workflow worker      v         |
|       |           /       |        \       Artifact      |
|       |    Orchestrator  Actors   Safety     projector    |
|       |           \       |        /           |         |
|       |             Local model adapters        v         |
|       |                    |              private/public  |
|       +--------------------+-------------------- files     |
+---------------------------------------------------------+
                             |
                             v
                  Ollama / llama.cpp / vLLM /
                  another OpenAI-compatible runner
```

The service has one process boundary for the pilot but maintains strong internal module boundaries. A durable database queue, not an in-memory task, drives work. If the process restarts, the worker resumes from committed state.

The service allows only one active season. Runs and model calls are sequential, which matches the turn-based story model and avoids local-GPU contention.

## 3. Key architectural decisions

| ID | Decision | Reason |
|---|---|---|
| A-01 | Build a modular monolith, not microservices. | One server and one active season do not justify distributed infrastructure. Fewer process boundaries make wellness auditing and crash recovery easier to understand. |
| A-02 | Use SQLite for operational state and Markdown/JSONL for durable human-facing evidence. | Files are ideal for inspection; SQLite provides transactions, locking, uniqueness, and reliable recovery. Neither alone satisfies both needs cleanly. |
| A-03 | Use a transactional outbox to project append-only artifacts. | Database state and filesystem writes cannot share one transaction. The outbox lets file projection resume idempotently after a crash. |
| A-04 | Introduce a season schema instead of stretching `ProductionPlan` v1. | The existing schema describes one disclosed scene. The new product separates creator-visible opening information from hidden orchestration, 21 runs, diaries, memory, wellness, and publication. |
| A-05 | Keep the existing `ChatClient` boundary and add capability-aware adapters. | The current OpenAI-compatible interface is useful and already testable. Adapters can add structured output, usage, cancellation, and model metadata without binding the domain to one runner. |
| A-06 | Run all model work through a durable sequential worker. | A single active generation at a time reduces VRAM contention and makes order, retries, tap-outs, and checkpointing deterministic. |
| A-07 | Use a dependency-free WSGI dashboard with server-rendered HTML and small inline JavaScript. Poll operational status at a calm cadence; make content-review reload explicit. | The dashboard is operational, single-user, and private. The shipped standard-library surface avoids a second runtime and prevents automatic status updates from collapsing an entry under review. SSE remains a future option, not current evidence. |
| A-08 | Treat safety and wellness as pipeline stages before canon acceptance. | Raw output must be preserved, but it must not become canon before explicit wellness parsing and safety validation. |
| A-09 | Make publication a separate immutable projection. | Private records remain authoritative and complete. `publish Sxx` creates a filtered, versioned public artifact without mutating private history. |
| A-10 | Preserve the current single-scene engine as a compatibility and benchmark harness. | It is useful for model evaluation and migration while the season workflow is built around it. |
| A-11 | Preserve one creator-approved character card separately from the generated private role sheet. | S01 retained only cast names at approval, so the reviewed professions and voice anchors never reached role-sheet generation. Generated private material may extend a character but must not replace the approved identity. |
| A-12 | Treat owner review as a chronological evidence projection, not a lexical file listing. | S01 Day 2 exposed actor turns rendered before the orchestrator beat that prompted them. Model and continuity review require the same accepted order used by the runtime. |
| A-13 | Implement provider-native JSON Schema output on every backend that supports it. | The capability abstraction exists, but the concrete live client currently falls back to fragile tagged text. Native schemas separate protocol reliability from creative prose quality. |
| A-14 | Rehearse the full pre-season workflow manually before templating or restoring autonomous multi-day operation. | The S01 pilot showed that individually passing components did not make the operator workflow or live output production-ready. The one-day sandbox is the next acceptance boundary. |

## 4. Runtime components

### 4.1 Dashboard and API

Responsibilities:

- collect the creator’s free-form season idea and revision requests;
- show only set, setting, cast, and world rules before `green`;
- validate and execute creator commands;
- show operational state, live progress, diary counts, delays, and alerts;
- assemble an owner-only end-of-day reading record from durable opening, accepted
  shared-script, run, and diary artifacts;
- reconstruct every review transcript in actual accepted chronology and expose
  turn count, completion reason, schedule, delay, and non-secret fiction time;
- provide an explicitly opened owner-only diagnostic workspace for role/model,
  model-call, parse, correction, and prompt/schema-version evidence without
  changing canon or publication state;
- guide the creator through a sandboxed pre-season rehearsal and one-day test;
- present recovery choices;
- gate and execute season-qualified publication;
- poll durable operational state without disturbing reading panes;
- provide authenticated, root-contained reads of the specifically allowlisted
  review artifacts, not a general private-file browser.

The dashboard must never query model backends directly. Every change enters through an application command handler and is written durably before work begins.

### 4.2 Command handlers

Command handlers are the only write entry point from the API or CLI. They:

- authenticate and authorize the creator;
- validate the current aggregate state;
- apply a domain transition;
- append an event;
- enqueue any required durable work;
- return the new state or a clear rejection.

Core commands:

```text
SubmitSeasonIdea
RequestOpeningRevision
GreenSeason
PauseSeason
ResumeSeason
RetryFailedWork
SkipRun
EndSeason
ResolvePublicationFlag
PublishSeason
```

Every command carries a request ID. Repeating the same request ID returns the original result rather than applying the command twice.

### 4.3 Scheduler

The scheduler is calendar-aware but does not execute scenes itself.

Responsibilities:

- calculate the first 06:00 `America/Los_Angeles` boundary after `green`;
- create all 21 immutable schedule-slot records at season activation;
- preserve each slot’s original local timestamp, UTC instant, UTC offset, day number, and slot number;
- enqueue due slots in original order;
- prevent later slots from passing unresolved earlier work;
- calculate delay from original scheduled time;
- create day-closure and end-of-day direction work.

Use Python’s standard `zoneinfo` for timezone behavior. The 06:00, 12:00, and 18:00 schedule avoids ambiguous daylight-saving transition hours, but the explicit offset is still stored.

The scheduler wakes from a short polling loop and queries durable due work. It must not rely on an in-memory timer or OS cron as the source of truth.

### 4.4 Season workflow worker

The worker claims one durable work item using an expiring lease. It renews the lease during long model calls.

Work item types include:

```text
PLAN_OPENING
ORIENT_ACTOR
RUN_SCENE
UPDATE_ACTOR_MEMORY
WRITE_DIARY
CLOSE_DAY
PLAN_NEXT_DAY
ARCHIVE_CHARACTER
WRITE_HANDOFF
REVIEW_PUBLICATION
PROJECT_PUBLICATION
```

Only one item that can invoke a model runs at once. File projection and read-only API work may proceed concurrently.

### 4.5 Scene engine

The current `engine.Orchestrator` becomes a lower-level scene runner rather than the product-level orchestrator.

Target responsibilities:

- execute one shared run;
- load the immutable mission day, daily slot, and scheduled local timestamp;
- carry forward prior accepted canon, the previous run's final shared outcome,
  and only the current actor's durable memory;
- give a closed day's private direction to the orchestrator context only;
- render morning, afternoon, evening, and overnight passage into shared context
  so later runs do not resume as adjacent seconds;
- request the next-speaker decision from the orchestrator model;
- frame each round as a TTRPG-style adjudication and concrete state-changing
  beat while keeping progress/danger/mystery/relationship clocks private;
- enforce one actor turn per round and 16 actor turns maximum;
- enforce the 30-minute wall-clock limit;
- cap actor turns and orchestrator interventions;
- stream raw output into private attempt files;
- pause at durable turn boundaries;
- emit typed events;
- accept only validated output into canon and the readable transcript.

Every accepted stage beat and actor response needs an explicit monotonic
sequence within the run. Projectors use that sequence, not a lexical natural ID,
to reconstruct causal order. Schema migration 2 now stores
`accepted_sequence`, `accepted_at`, and an actor/interruption
`caused_by_turn_id` link for new accepted records. Migrated legacy rows remain
null: projectors apply the same round/director-first/insertion ordering as the
live runner and label that display as derived instead of backfilling inferred
evidence.

The product-level orchestrator should be named `SeasonOrchestrator` or `DirectorService` in code to avoid confusing it with the existing single-scene runner.

### 4.6 Diary workflow

The diary workflow is independent of the scene transcript exporter.

Responsibilities:

- record each actor’s daily diary-slot decision;
- schedule a private diary call after that run;
- build a just-in-time brief from that actor’s existing knowledge only;
- enforce first-person limited instructions and the soft 300–800 word target;
- preserve the first attempt without quality rewriting;
- detect safety or wellness signals;
- mark late or missing diaries;
- keep diary content away from other actors and from the orchestrator until day closure;
- write private Markdown and machine-readable metadata.

### 4.7 Memory and canon services

Keep subjective memory and objective canon separate.

`ActorMemoryService`:

- asks each actor for a post-run experience summary;
- preserves beliefs, suspicions, emotions, and uncertainty;
- versions memory after every run;
- builds future actor context without importing private wellness history.

Until the versioned service is complete, accepted actor `MEMORY_NOTE` values
are rebuilt from prior `TurnAccepted` events at live-run construction. They are
partitioned by `character_id`; peer memory is never merged into actor context.

`CanonService`:

- validates factual claims with the orchestrator;
- records accepted facts and provenance;
- resolves conflicts;
- gates role-sheet and world-rule revisions;
- exposes only knowledge an actor could plausibly possess.

Until the versioned ledger is complete, prior shared canon is rebuilt from
accepted orchestrator-round events in immutable run order. Hidden next-day
direction text and its unrevealed possibilities are not promoted into actor
canon merely because the planning call produced them.

Canon entries should include source references such as run ID, turn ID, diary ID, or orchestrator decision ID.

### 4.8 Safety and wellness pipeline

Every raw generation passes through this order:

```text
raw output persisted
  -> explicit wellness-signal extraction
  -> deterministic content checks
  -> contextual local-model review
  -> role/world-rule validation
  -> disposition
  -> canon/transcript acceptance or intervention
```

Persisting raw output first ensures the creator can audit what happened even when the content is rejected.

Possible dispositions:

```text
ACCEPT
REQUEST_ONE_CORRECTION
NOT_CANON_CONTINUE_NEUTRALLY
HOLD_DIARY_PRIVATE
WELLNESS_REDIRECT
TAP_OUT
MANUAL_REVIEW
```

The wellness parser runs before the content filter so an actor’s explicit request to stop cannot be discarded as malformed or out-of-character content.

The deterministic layer handles clear structural and hard-rule violations. The local contextual reviewer handles ambiguity. For the pilot, the reviewer may use the orchestrator model through a separate prompt and context; the interface must permit a dedicated model later.

### 4.9 Artifact projector

The artifact projector reads committed outbox rows and writes human-readable and machine-readable files.

Properties:

- idempotent by artifact key;
- append-only for audit records;
- atomic replacement only for explicitly mutable derived views such as `state.json`;
- immutable version paths for role sheets, memories, archives, and publications;
- temporary-file plus `fsync` plus atomic rename for completed artifacts;
- retries safely after crashes;
- records a hash and byte length for every completed file.

The projector never invents domain state. It renders already-committed events and records.

## 5. Domain model

### 5.1 Aggregates

Use a small number of explicit aggregates:

`Season`

- season ID, title, status, schedule, opening version, active day;
- creator approval and publication state;
- exactly one active season enforced by a database constraint.

`CastMember`

- character identity, actor-session identity, model binding;
- orientation state, role-sheet version, memory version;
- active/departed/replaced state;
- per-season wellness count and diary obligations.

`Run`

- immutable schedule identity;
- status, attempt history, turn count, round state;
- checkpoint and completion reason.

`Day`

- three run references;
- expected diary obligations;
- cutoff instant and closure state;
- end-of-day direction reference.

`Diary`

- actor/day/slot identity;
- write state, lateness, validation, publication eligibility;
- immutable content version for the accepted first attempt.

`Publication`

- season ID, review state, eligible diary set;
- publication version, manifest, hashes, and output path.

### 5.2 Season states

```text
DRAFT
AWAITING_GREEN
ARMED
RUNNING
PAUSED
RECOVERY_REQUIRED
CLOSING
SEASON_COMPLETE
AWAITING_PUBLISH_REVIEW
PUBLISHED
```

Important rules:

- `green` is valid only in `AWAITING_GREEN` and after preflight passes.
- `ARMED` has a fixed 21-slot schedule but no run has begun.
- `PAUSED` never consumes queued schedule slots.
- `RECOVERY_REQUIRED` requires the creator to choose retry, skip, or end.
- `SEASON_COMPLETE` does not imply publication.
- publication is season-specific and does not block a new season.

### 5.3 Run states

```text
SCHEDULED
QUEUED
RUNNING
WAITING_FOR_MODEL
PAUSED
RECOVERY_REQUIRED
COMPLETED
SKIPPED
INTERRUPTED
```

`COMPLETED` and `SKIPPED` are terminal. An interrupted process does not make the run terminal; recovery returns it to the last committed checkpoint.

### 5.4 Model-call states

```text
PENDING
STREAMING
RAW_COMPLETE
VALIDATING
ACCEPTED
REJECTED
RETRYABLE_FAILURE
WAITING_FOR_MODEL
MANUAL_REVIEW
```

Each call has an immutable attempt number. A retry creates a new attempt; it never overwrites the original prompt or output.

## 6. Data and persistence

### 6.1 SQLite operational store

Use SQLite in WAL mode with foreign keys enabled. Keep schema migrations in the repository and run them explicitly on service startup.

Core tables:

```text
seasons
season_opening_versions
schedule_slots
days
cast_members
role_sheet_versions
actor_memory_versions
canon_entries
runs
turns
model_calls
diaries
wellness_events
consent_decisions
recovery_requests
notifications
publications
domain_events
work_items
artifact_outbox
```

Large raw prompts and outputs live in private files; their database rows store relative paths, hashes, sizes, timestamps, model metadata, and validation disposition.

The `turns` table stores accepted story records only. New rows receive a
run-local monotonic accepted sequence and acceptance time; accepted actor and
neutral-interruption rows link to the accepted director beat for their round.
Legacy null causal fields are valid historical evidence and must never be
silently rewritten.

### 6.2 Identity and idempotency

Use sortable unique IDs such as UUIDv7 for domain records. Also enforce natural uniqueness:

```text
schedule slot: season + original day + slot
run: season + schedule slot
turn: run + round + actor
diary obligation: season + original day + character
publication: season + publication version
```

These constraints are the final defense against duplicate execution after a retry or restart.

### 6.3 Filesystem layout

The production specification’s private/public tree remains the user-facing layout. Add an application-state directory beside it:

```text
data/
  state/
    improv.sqlite3
    migrations/
  private/
    seasons/
    characters/
    benchmarks/
  public/
    seasons/
```

All paths are configurable but resolved and validated at startup. The service must refuse a configuration in which private and public roots overlap.

Private directories use owner-only permissions by default. Secrets and password hashes do not appear in season artifacts or audit files.

### 6.4 Artifact consistency

The database is the authoritative operational state. Files are the authoritative readable audit and publication evidence.

The transactional outbox connects them:

1. A command or worker transaction commits state, domain events, and artifact intents.
2. The artifact projector writes the files.
3. The projector records path, hash, and completion.
4. The dashboard reports an artifact as available only after projection completes.

If projection fails, story state does not rerun. The artifact remains pending and can be regenerated from committed records.

## 7. Model integration

### 7.1 Client boundary

Retain the existing `ChatClient` protocol, then add a higher-level adapter that can report:

- streamed text;
- finish reason;
- token/usage data when available;
- backend and model version;
- structured-output capability;
- cancellation support;
- request timing and errors.

Domain and application modules depend on protocols, not `httpx`, Ollama, or a specific server.

### 7.2 Response envelopes

Internally normalize actor output to:

```text
ActorTurnResult
  narrative_text
  stage_direction
  wellness_signal?
  diary_intent?
  parse_warnings[]
```

Normalize orchestrator output to explicit Pydantic models for:

- opening proposal;
- private role sheets;
- next-speaker choice;
- Dungeon Master intervention;
- canon validation;
- memory validation;
- next-day direction;
- tap-out replacement decision;
- handoff.

Use provider-native structured output when the selected backend supports it. Otherwise use strict tagged output and a deterministic parser. Parsing failure is a model-call failure, not permission to infer hidden fields silently.

The S01 implementation does not yet satisfy the first sentence: the capability
protocol is present, but the concrete OpenAI-compatible client does not expose a
native structured method, so live calls take the tagged fallback. The overhaul
must add backend-qualified schema support, record whether each attempt used
`NATIVE_SCHEMA` or `TAGGED_FALLBACK`, and contract-test both paths. Schema
enforcement constrains the envelope only; actor and director prose stays inside
free text fields and retains its creative sampling settings.

### 7.3 Context assembly

Create purpose-specific context builders rather than one growing prompt:

```text
OpeningContextBuilder
CharacterCardContextBuilder
ActorTurnContextBuilder
OrchestratorTurnContextBuilder
DiaryContextBuilder
MemoryContextBuilder
SafetyReviewContextBuilder
HandoffContextBuilder
```

The context builders enforce knowledge boundaries. They are the only code allowed to select private material for a model call.

The immutable character card is an input to role-sheet generation and to that
character's own context. It contains only creator-approved identity anchors; it
must not contain another actor's secrets or the director's hidden plan. The
generated role sheet references the character-card version it extends.

Full raw history remains on disk. If a model context window cannot hold the full shared scene history, the builder uses a versioned, canon-validated summary plus recent turns and records that compaction in the audit.

### 7.4 Benchmarking

The benchmark subsystem uses scripted fixtures and the current single-scene runner to compare candidate models on the Linux host.

It records:

- latency and throughput;
- context capacity;
- role and format compliance;
- safety and wellness-signal handling;
- canon consistency;
- diary quality;
- resource use when available.

The report recommends assignments but does not choose models for the creator. The selected model manifest is locked into the season at `green` and recorded privately.

## 8. Scheduling, retry, and recovery

### 8.1 Retry policy

Proposed pilot default, configurable after benchmarking:

- three automatic attempts total;
- short exponential backoff between attempts;
- after the final automatic failure, enter `WAITING_FOR_MODEL` for up to four hours;
- periodically recheck backend/model health without advancing the story;
- after four hours, enter `RECOVERY_REQUIRED` and notify the creator.

The creator chooses retry, skip, or end. No later run executes while recovery is unresolved.

### 8.2 Checkpoint boundaries

Commit a checkpoint after:

- orientation response;
- orchestrator intervention;
- each accepted actor turn;
- each failed/corrected attempt disposition;
- each actor memory update;
- each diary attempt;
- day closure;
- next-day direction;
- each character archive;
- handoff completion.

An accepted turn is never generated twice. If the process dies while streaming a call, its `.partial` output is preserved, the attempt is marked interrupted, and a new attempt begins from the preceding committed checkpoint.

### 8.3 Catch-up

At startup, the scheduler compares all unresolved schedule slots with current time and queues them in original order. Delay is calculated when each run actually starts.

Catch-up never changes:

- original season day;
- original local timestamp;
- original UTC offset;
- run number;
- diary obligation;
- end-of-day ordering.

### 8.4 Concurrency and locking

- Enforce one active season with a unique database constraint.
- Enforce one model worker with a database lease.
- Use optimistic version numbers on aggregates for dashboard commands.
- Reject stale or repeated control requests clearly.
- Do not use filesystem lock files as the only concurrency control.

## 9. Dashboard architecture

### 9.1 Technology

Current pilot stack:

- Python standard-library WSGI application and server-rendered HTML;
- inline CSS and minimal browser JavaScript, with no frontend build step;
- scrypt password hash held outside season data, owner session cookie, and CSRF
  protection for state-changing requests;
- 60-second operational-status polling;
- explicit **Refresh** and **Reload review** controls for content reloads;
- no public internet binding.

The automatic poll updates operational panels only. It deliberately does not
re-render diary or end-of-day reading panes, so an open entry remains stable.
Server-Sent Events and a reverse proxy/HTTPS deployment remain future options;
they are not implemented evidence for this pilot.

### 9.2 Views

`Planning`

- free-form idea and revision conversation;
- creator-visible opening proposal and stable cast cards, without private role
  sheets or hidden plans;
- preflight status;
- `green` action.

`Pre-season rehearsal`

- sandbox data-root identity displayed persistently;
- ordered checklist for idea, opening revisions, cast cards, model assignment,
  preflight, private role-sheet generation, orientation, schedule preview, and
  green;
- raw/parsed evidence available only through explicit owner disclosures;
- no action against the production season from this view;
- exportable operator runbook evidence after the manual rehearsal.

`Season status`

- state, day, run, round, actor turn, elapsed time;
- next scheduled slot and catch-up queue;
- cast and diary counts;
- persistent local alerts;
- pause/resume/end controls.

`Recovery`

- failed work identity and readable error summary;
- original schedule and elapsed delay;
- retry/skip/end actions.

`End-of-day review`

- select one original season day;
- show its creator-visible opening snapshot, accepted shared script, and run
  state in one reading surface;
- show each accepted diary and every held private diary attempt;
- permit the signed-in owner to explicitly expand raw private model output when
  needed to review a wellness or format hold;
- leave diary status, canon status, and publication eligibility unchanged.

The shared script in this view is ordered by accepted sequence. Each run summary
includes scheduled and actual time, fictional day/slot, delay, accepted
round/turn count, completion reason, and whether corrections or recovery were
required.

`Diagnostics` (owner-only explicit view)

- creator-approved character card and that actor's current private role sheet;
- backend/model binding, call purpose, attempt, latency, finish/error state, and
  schema path;
- prompt/template/schema version identifiers;
- side-by-side raw, parsed, accepted, and rendered output;
- no raw wellness text in the summary and no implicit clearance or mutation
  from reading any artifact.

`Publication`

- closed-season selector;
- wellness-review confirmation;
- flagged diary decisions;
- final `publish Sxx` confirmation;
- publication manifest and path.

`Files` (future)

- allowlisted links into the configured private/public roots;
- no arbitrary path parameter or directory traversal;
- raw audit remains creator-only;
- this general file-browser view is not part of the shipped WSGI dashboard.

### 9.3 Local notifications

Notifications are durable records, not ephemeral browser events.

- The service records each diary-ready, wellness, and recovery notification.
- The dashboard polls their unread count with the 60-second operational status
  refresh; a manual refresh can retrieve it sooner.
- Diary and end-of-day reading panes retain their displayed content until the
  owner explicitly reloads them.
- No email, webhook, cloud push, or SSE transport is used in the current pilot.

Native browser push while the dashboard is closed is outside the pilot unless the private deployment later gains trusted HTTPS and a service worker.

## 10. Publication architecture

Publication is a read-only projection of a closed season.

Workflow:

1. Verify the season is closed and has no pending model calls.
2. Require creator wellness-audit confirmation.
3. Run deterministic and contextual safety/privacy review.
4. Present uncertain or failed diaries for manual review.
5. Resolve each diary as `CLEARED` or `PRIVATE`.
6. Recheck departing-actor consent and revocation state.
7. Build a publication manifest containing only eligible diary IDs and hashes.
8. Render into a new staging directory.
9. Verify the staging tree contains no private metadata.
10. Atomically rename it to an immutable versioned public path.

The public projector operates from an explicit allowlist of fields. It does not sanitize a private artifact by deleting fields; it constructs new public Markdown from approved diary content and story-facing metadata.

If the target publication version already exists, publication fails safely instead of overwriting it.

## 11. Security and privacy

- Bind the dashboard only to the configured private-network interface or place it behind a private reverse proxy.
- Use one owner account with a strong password hash; never store the password itself.
- Use secure, HTTP-only, same-site cookies and CSRF tokens.
- Keep model backend credentials in environment variables or an owner-readable config file outside season artifacts.
- Redact authorization headers and configured secrets from request logs.
- Resolve all artifact paths against fixed roots and reject path escape.
- Default private files to `0600` and directories to `0700`, subject to the server’s backup requirements.
- Never expose SQLite, private files, model endpoints, or the public export directory as an unauthenticated directory listing.
- Add a startup check that private and public roots are distinct and not nested.

## 12. Proposed source layout

Retain the current package and evolve it by responsibility:

```text
src/improv_troupe/
  domain/
    plan.py                 # existing ProductionPlan v1 compatibility
    season.py               # Season, Day, Run, Diary state models
    cast.py                 # role sheets, actor status, archives
    canon.py                # canon entries and provenance
    wellness.py             # signals, counters, tap-out, consent
    publication.py          # review and immutable publication state
    events.py               # domain events

  application/
    commands.py
    handlers.py
    season_workflow.py
    diary_workflow.py
    publication_workflow.py
    context_builders.py

  engine/
    orchestrator.py         # existing compatibility runner
    scene_runner.py         # durable single-run execution
    director.py             # product-level orchestrator model behavior
    safety.py
    memory.py
    transcript.py
    events.py

  infrastructure/
    db.py
    migrations/
    repositories.py
    work_queue.py
    scheduler.py
    artifact_projector.py
    filesystem.py
    notifications.py
    auth.py
    service.py

  llm/
    client.py               # existing low-level protocol
    adapter.py              # metadata/capability normalization
    structured.py
    fake.py

  web/
    app.py
    api.py
    sse.py
    templates/
    static/

  cli.py                    # administration and compatibility commands
```

Do not require each directory to become a Python package immediately. The boundaries matter more than the exact file count.

## 13. CLI and service commands

Keep existing commands during migration:

```text
improv validate
improv schema
improv backends
improv run
```

Add service-oriented commands:

```text
improv serve --config config.yaml
improv migrate --config config.yaml
improv preflight --config config.yaml
improv benchmark --config config.yaml
improv status --config config.yaml
improv recover --config config.yaml
```

The dashboard remains the normal creator interface. The CLI is an administrative and recovery fallback.

## 14. Migration strategy

### Phase 0 — protect the current baseline

- Keep `ProductionPlan` v1 and existing tests passing.
- Keep `improv run --dry-run` as a fast smoke test.
- Record the current uncommitted macOS setup work separately from architecture changes.

### Phase 1 — durable domain foundation

- Add season/domain models and state transitions.
- Add SQLite migrations, repositories, event log, work queue, and outbox.
- Add virtual clock and schedule tests.
- Add artifact roots and private/public separation checks.

### Phase 2 — recoverable scene execution

- Refactor the current engine into a checkpointed `SceneRunner`.
- Add orchestrator model runtime and dynamic turn selection.
- Add raw-attempt files, validation dispositions, and readable markers.
- Add failure leases, retries, restart recovery, and catch-up.

### Phase 3 — memory, diaries, wellness, and daily direction

- Add actor orientation and persistent role sheets.
- Add per-run actor memory and canon ledger.
- Add diary obligations, cutoff, late handling, and notifications.
- Add safety/wellness pipeline, tap-out, replacement, and consent.
- Add day closure, next-day direction, character archives, and handoff.

### Phase 4 — dashboard and publication

- Add authenticated planning and operational views.
- Add SSE status updates and persistent notifications.
- Add recovery controls.
- Add publication review and immutable public projection.

### Phase 5 — pilot readiness

- Benchmark candidate local models on the Linux host.
- Run an accelerated seven-day simulation with fake models and a virtual clock.
- Run fault-injection tests for restarts and unavailable models.
- Perform a private-network security review.
- Complete one creator-only live pilot.

## 15. Testing and evaluation

### 15.1 Unit tests

- all valid and invalid state transitions;
- schedule generation around PST/PDT boundaries;
- unique/idempotency constraints;
- knowledge-boundary context builders;
- content rules and wellness parsing;
- diary cutoff and late status;
- tap-out counters and reset behavior;
- publication eligibility and consent;
- path containment and private/public separation.

### 15.2 Contract tests

- each supported local model adapter;
- structured-output and fallback parsing;
- usage/latency metadata capture;
- cancellation and timeout behavior;
- artifact projector idempotency;
- API command idempotency.

### 15.3 Workflow tests

Use a deterministic fake model and virtual clock to test:

- a complete 21-run season;
- downtime and ordered catch-up;
- restart during a streamed actor turn;
- restart after acceptance but before artifact projection;
- diary failure and four-hour recovery;
- skip and end decisions;
- three wellness signals and tap-out;
- replacement with and without former-viewer knowledge;
- publication with private/withheld diaries;
- immutable republishing failure.

### 15.4 Model evaluation

Automated checks score format, safety, cold/warm and full-context latency, canon
consistency, first-person identity, self-address/pronoun drift, and near-verbatim
repetition. The creator performs the final qualitative evaluation of surprise,
mystery, role commitment, relationship differentiation, and diary appeal.

After S01, the minimum live-model acceptance artifact is one isolated day with
three changed scene states, four diary opportunities, day closure, and next-day
direction. Model comparisons change one binding at a time and never auto-select
the winner.

## 16. Operational health

Expose authenticated health information for:

- service and database status;
- worker lease and current work item;
- scheduler next wake and backlog count;
- local model backend reachability;
- artifact outbox backlog;
- private/public storage availability;
- unread wellness/recovery alerts;
- last successful checkpoint.

Write structured service logs separately from story artifacts. Service logs may contain IDs and error summaries but must not duplicate private prompt content or secrets.

## 17. Architecture acceptance criteria

The architecture is ready for the creator-only pilot when:

- the service survives restart at every documented checkpoint boundary;
- repeated commands and scheduler wakes cannot duplicate a run, turn, diary, or publication;
- an accelerated 21-run season completes through the same workflow used in production;
- all private/public leakage tests pass;
- the creator can read every rejected, corrected, skipped, late, and wellness-relevant event without opening SQLite;
- owner review renders the exact accepted causal order and never reduces a run
  to `COMPLETED` without its completion reason and turn count;
- creator-approved character cards survive role-sheet generation and actor
  context assembly without private-data leakage;
- capable local backends use a contract-tested native schema path and record
  any tagged fallback explicitly;
- an isolated one-day live-model rehearsal completes without touching the
  production data root before another multi-day season is armed;
- the dashboard can disconnect and reconnect without affecting execution;
- model unavailability reaches the four-hour recovery decision without advancing later runs;
- `green` and `publish Sxx` cannot bypass their preconditions;
- public output is produced only from an explicit field allowlist and is immutable;
- model benchmark results demonstrate that the chosen assignments fit the 30-minute run budget.

## 18. Deferred architecture decisions

These decisions require the Linux host or model benchmarks and should not be guessed now:

- exact actor and orchestrator model names;
- exact local model runner;
- which 12B-class candidates, if any, should challenge the S01 bindings;
- whether future live runs retain one mandatory turn per actor per round or use
  a more selective spotlight structure;
- the final purpose-specific operator and model template fields after the manual
  pre-season rehearsal;
- whether the contextual safety reviewer needs a dedicated model;
- context-compaction thresholds for the selected models;
- retry delay values inside the agreed bounded retry policy;
- whether trusted HTTPS is worth adding for browser-native notifications;
- future website hosting and interaction architecture.
