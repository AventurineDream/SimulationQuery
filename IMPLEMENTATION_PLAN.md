# AI Improv Troupe — Implementation Plan

**Executor:** Luna
**Status:** authorized for implementation
**Product source:** [PRODUCTION_SPEC.md](PRODUCTION_SPEC.md)
**Architecture source:** [ARCHITECTURE_SPEC.md](ARCHITECTURE_SPEC.md)
**Original baseline:** Python 3.14.6; 8 tests passing on 2026-08-20

**Current handoff (2026-08-26):** The creator has decided to end S01 privately
after the Day 2 review and overhaul the operator workflow. Do not restart the
live worker to continue the season. Inspect authoritative Linux state before the
separate season-end action. Current evidence, privacy boundaries, and the exact
next implementation task are recorded in
[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md); the private Day 2 review
is [benchmarks/s01-day-2-model-review-2026-08-24.md](benchmarks/s01-day-2-model-review-2026-08-24.md).
The dashboard's functional workflow is creator-approved in
[DASHBOARD_OVERHAUL_PLAN.md](docs/dashboard/DASHBOARD_OVERHAUL_PLAN.md). The representative
high-fidelity Home/Day Review, Prepare, and Live/Recovery checkpoints are
approved and frozen. The Diagnostics high-fidelity checkpoint is also approved
and frozen. The final Seasons/Publication checkpoint is approved and frozen;
the complete dashboard high-fidelity design is now approved. The bounded
`DASH-00` implementation seam is code-complete, locally verified, and
creator-accepted, with the legacy dashboard preserved and the authenticated v2
shell disabled by default. The separately authorized `DASH-01` read-only Home
slice is also code-complete, locally verified, and creator-accepted. The
separately authorized `DASH-02` causal Day Review slice is code-complete,
locally verified, and creator-accepted. The separately authorized `DASH-03`
call-focused Diagnostics slice is code-complete, locally verified, and
creator-accepted. The separately authorized `DASH-04` versioned Prepare slice
is code-complete, locally verified, and creator-accepted. The separately
authorized `DASH-05` Live and consequence-first Recovery slice is code-complete
and locally verified; its manual healthy/retry/skip creator walkthrough is
pending. The separately authorized `DASH-06` Seasons/private-close/publication
slice is code-complete and locally verified against disposable S02 data; its
creator walkthrough is pending. The
build-ready sequence, module boundary, vertical tickets, acceptance ladder,
rollback, and stop conditions are recorded in
[DASHBOARD_IMPLEMENTATION_SEQUENCE.md](docs/dashboard/DASHBOARD_IMPLEMENTATION_SEQUENCE.md).
The next dashboard decisions are the still-open `DASH-05` healthy/retry/skip
walkthrough and `DASH-06` Private Close/Publication walkthrough. The separately
authorized `DASH-07` deterministic one-day rehearsal is implemented and
locally verified; its creator review and any real local-model day remain
unapproved. `DASH-08`, deployment, S01 private close, worker operation, model
use, and real publication remain unapproved.

The checkboxes below preserve the original authorized gate checklist; current
completion evidence is maintained in `IMPLEMENTATION_STATUS.md`. Gate 12 adds
the creator-authorized post-S01 dashboard, manual pre-season, and one-day-test
overhaul. It does not authorize model downloads, a final recast, publication, or
destructive changes to S01 evidence.

This plan turns the approved production and architecture specifications into testable implementation gates. Product behavior in `PRODUCTION_SPEC.md` is authoritative. Architectural boundaries in `ARCHITECTURE_SPEC.md` should be followed unless implementation evidence shows that a change is necessary.

## 1. Execution rules

Luna should:

1. Work in the existing checkout and preserve unrelated or pre-existing changes.
2. Treat `README.md`, `CLAUDE.md`, `scripts/setup_macos.sh`, `PRODUCTION_SPEC.md`, and `ARCHITECTURE_SPEC.md` as existing user work.
3. Keep the current `ProductionPlan` v1, CLI commands, examples, and tests working while adding the season system.
4. Implement one gated phase at a time and run the phase’s tests before moving forward.
5. Create and maintain `IMPLEMENTATION_STATUS.md` with completed gates, current failures, decisions made, and the exact next action.
6. Use deterministic fakes and a virtual clock for automated season tests. Never wait for real schedule time in a test.
7. Preserve every failed model attempt and recovery decision. Do not make tests pass by weakening idempotency, privacy, safety, or wellness requirements.
8. Keep local-model interfaces backend-agnostic. Do not select final actor or orchestrator models in code.
9. Keep the dashboard private-network and single-owner. Do not add cloud services, analytics, email, webhooks, or public hosting.
10. Do not commit, push, delete user files, or rewrite the production/architecture specifications without explicit creator approval.

If the specifications conflict, record the conflict in `IMPLEMENTATION_STATUS.md`, choose the safer reversible interpretation for continued local work, and escalate before making a product-level change.

## 2. Definition of done

The implementation is complete when:

- all automated tests pass;
- the original v1 single-scene CLI remains compatible;
- an accelerated fake-model season completes all 21 slots through the production workflow;
- service restart tests prove accepted turns and diaries are not duplicated;
- catch-up, four-hour recovery, skip, end, and late-diary behavior pass;
- privacy tests prove no hidden plan, model identity, audit, or wellness data reaches public output;
- wellness tests prove explicit signals interrupt before canon acceptance and three signals tap out the correct actor;
- the authenticated dashboard can plan, `green`, monitor, control recovery, and publish without being required for server execution;
- publication is season-qualified, reviewed, allowlisted, versioned, and immutable;
- the Linux service, configuration, migration, preflight, and benchmark commands are documented;
- real model selection and Linux deployment remain clearly marked as creator/manual gates rather than falsely reported as tested;
- after S01, the creator can manually rehearse the complete pre-season workflow
  and complete one isolated live-model day before another multi-day season is
  armed.

## 3. Baseline and verification commands

Current baseline:

```text
.venv/bin/python --version
Python 3.14.6

.venv/bin/python -m pytest -q
8 passed
```

Run after every gate:

```bash
.venv/bin/python -m pytest -q
.venv/bin/improv --help
git diff --check
git status --short
```

Keep targeted tests fast during implementation, then run the full suite before each gate closes.

## 4. Delivery sequence

```text
Gate 0  Baseline protection
  -> Gate 1  Season domain and calendar
  -> Gate 2  SQLite, events, queue, and artifact outbox
  -> Gate 3  Commands and durable workflow shell
  -> Gate 4  Model adapters and context boundaries
  -> Gate 5  Recoverable shared-scene runner
  -> Gate 6  Memory, canon, diaries, and daily direction
  -> Gate 7  Wellness, tap-out, replacement, and archives
  -> Gate 8  Scheduler, catch-up, restart, and service process
  -> Gate 9  Private dashboard and notifications
  -> Gate 10 Publication review and immutable export
  -> Gate 11 Benchmarking, deployment, and full pilot simulation
  -> Gate 12 S01 operator overhaul and one-day acceptance
```

Each gate must leave the repository runnable and testable.

## 5. Gate 0 — Protect the baseline

### Tasks

- [ ] Record the starting `git status --short` in `IMPLEMENTATION_STATUS.md`.
- [ ] Run and record the baseline tests and CLI help.
- [ ] Add a test that explicitly protects `ProductionPlan` schema version `1.0`.
- [ ] Add a compatibility test for `improv run ... --dry-run` producing Markdown.
- [ ] Add a deterministic clock protocol and scripted fake-model protocol for later phases without changing current behavior.
- [ ] Document which existing files are pre-existing dirty work so later diffs are not misattributed.

### Gate 0 acceptance

- Existing eight tests still pass.
- New compatibility tests pass.
- No current CLI behavior is removed.
- `IMPLEMENTATION_STATUS.md` clearly distinguishes baseline work from Luna’s changes.

## 6. Gate 1 — Season domain and calendar

### Tasks

- [ ] Add domain enums and Pydantic/dataclass models for season, day, schedule slot, run, model call, cast member, diary, publication, wellness, and recovery state.
- [ ] Introduce `OpeningSnapshot` containing only set, setting, cast, and world rules.
- [ ] Introduce private models for hidden season planning and role sheets.
- [ ] Add sequential season IDs plus start date and optional creator title.
- [ ] Implement `America/Los_Angeles` schedule generation using `zoneinfo`.
- [ ] Calculate the next 06:00 Pacific boundary after `green` and create exactly 21 immutable slots at 06:00, 12:00, and 18:00 over seven full local days.
- [ ] Store original local timestamp, UTC timestamp, UTC offset, day number, and slot number.
- [ ] Implement pure state-transition functions with explicit rejection errors.
- [ ] Keep the existing `ProductionPlan` v1 untouched; introduce a distinct season schema/version.

### Tests

- [ ] `green` at times before and after 06:00 always creates the correct next 06:00 start.
- [ ] Exactly 21 unique slots are generated over seven local dates.
- [ ] PST and PDT offsets are preserved around both annual transitions.
- [ ] Invalid state transitions are rejected.
- [ ] Only one active season is permitted by domain policy.
- [ ] Creator-visible serialization of an opening cannot contain hidden planning fields.
- [ ] Season schema and v1 `ProductionPlan` can coexist.

### Gate 1 acceptance

- Domain behavior is deterministic and has no filesystem, database, web, or model dependency.
- Calendar tests run without real waiting or host-timezone assumptions.

## 7. Gate 2 — SQLite, event log, work queue, and artifacts

### Tasks

- [ ] Add a configurable `data/` root with distinct `state/`, `private/`, and `public/` roots.
- [ ] Add SQLite migration infrastructure using WAL mode and foreign keys.
- [ ] Create the core tables listed in the architecture specification.
- [ ] Add repository interfaces and SQLite implementations.
- [ ] Add optimistic aggregate versions and natural uniqueness constraints.
- [ ] Add durable domain events, work items, leases, and artifact outbox rows.
- [ ] Add an idempotent artifact projector.
- [ ] Write Markdown for readable records and JSON/JSONL for machine records.
- [ ] Store file hashes and byte lengths after projection.
- [ ] Apply owner-only private file/directory permissions where supported.
- [ ] Reject overlapping or nested private/public roots.

### Tests

- [ ] Migrations apply to a fresh temporary database and are idempotent.
- [ ] A second active season is rejected transactionally.
- [ ] Duplicate natural IDs cannot create duplicate slots, runs, turns, diaries, or publications.
- [ ] A committed outbox item can be projected repeatedly without duplicate content.
- [ ] Simulated crash after database commit but before file write resumes projection without rerunning story work.
- [ ] Private/public overlap and path escape are rejected.
- [ ] Append-only versioned artifacts never overwrite an earlier version.

### Gate 2 acceptance

- Operational state survives process recreation.
- The creator can inspect representative Markdown/JSONL without opening SQLite.
- Story execution and artifact projection are demonstrably separate.

## 8. Gate 3 — Commands and durable workflow shell

### Tasks

- [ ] Implement typed commands and command handlers.
- [ ] Require request IDs and make command replay idempotent.
- [ ] Implement season draft, opening revision, preflight state, and exact `green` approval.
- [ ] Snapshot the approved opening and model/config manifest at `green`.
- [ ] Implement pause, resume, retry, skip, and end transitions.
- [ ] Add durable work-item dispatch without invoking real models yet.
- [ ] Add creator/manual audit events for every control decision.
- [ ] Create a fake in-process service harness that can advance queued work deterministically.

### Tests

- [ ] `green` is rejected before preflight success.
- [ ] `green` is rejected outside `AWAITING_GREEN`.
- [ ] Replaying a command request ID returns the original result.
- [ ] Pause preserves due schedule slots.
- [ ] Skip marks the run terminal without deleting its ledger entry.
- [ ] End closes from available records and queues a handoff.
- [ ] Later seasons can begin after a previous season closes but remains unpublished.

### Gate 3 acceptance

- A fake season can move from draft through schedule creation and control transitions using only durable commands and work items.

## 9. Gate 4 — Model adapters and context boundaries

### Tasks

- [ ] Preserve the low-level `ChatClient` protocol.
- [ ] Add normalized call results with backend, model, timing, usage, finish reason, cancellation, and parse warnings.
- [ ] Extend the fake client into a scripted deterministic backend supporting success, streaming interruption, invalid output, wellness signals, and timeouts.
- [ ] Add Pydantic response envelopes for actor turns and orchestrator decisions.
- [ ] Support native structured output when available and strict tagged fallback parsing otherwise.
- [ ] Add purpose-specific context builders for opening, actor turn, orchestrator turn, diary, memory, safety, and handoff.
- [ ] Make context builders the only model-facing selectors of private state.
- [ ] Add audit-safe prompt/output persistence with secret redaction.
- [ ] Preserve partial stream files after interruption.

### Tests

- [ ] Existing OpenAI-compatible streaming still works through the adapter.
- [ ] Structured and tagged fallback responses normalize to the same domain result.
- [ ] Parsing failure becomes a recorded model-call failure.
- [ ] Actor context never contains another actor’s role sheet, memory, diary, wellness record, or hidden plan.
- [ ] Creator-visible/public context never contains model identity or private fields.
- [ ] Interrupted streaming preserves partial output and creates a new attempt without accepting the partial text.

### Gate 4 acceptance

- Model-dependent application code uses protocols and normalized results, not `httpx` or runner-specific response formats.

## 10. Gate 5 — Recoverable shared-scene runner

### Tasks

- [ ] Refactor the current engine into a compatibility runner plus a durable `SceneRunner`.
- [ ] Add the product-level orchestrator/director runtime.
- [ ] Implement active Dungeon Master narration, NPC/environment control, canon adjudication, and dynamic next-actor selection.
- [ ] Enforce four rounds, one turn per active actor per round, and 16 actor turns maximum for the pilot.
- [ ] Enforce the 30-minute run deadline through an injected clock.
- [ ] Enforce 150–300-word actor guidance and 200-word orchestrator intervention cap.
- [ ] Persist raw output before wellness, safety, role, or canon validation.
- [ ] Implement one private correction for rule/role violations.
- [ ] After a second failure, mark both attempts non-canon and insert a neutral interruption.
- [ ] Render readable speaker and intervention markers.
- [ ] Checkpoint after every accepted turn and disposition.
- [x] Load the immutable seven-day mission day/slot and render substantial
  morning, afternoon, evening, and overnight passage into every live context.
- [x] Instruct the orchestrator to adjudicate concrete TTRPG-style beats and
  privately track mission-progress, danger, mystery, and relationship pressure
  without shortening the approved turn structure.

### Tests

- [ ] Four actors receive exactly one turn per round unless the run ends early.
- [ ] Dynamic order cannot omit or duplicate an actor within a round.
- [ ] Natural orchestrator completion ends before the hard limits.
- [ ] Turn and wall-clock limits end with the correct reason.
- [ ] A rule-breaking turn receives exactly one correction.
- [ ] A second invalid turn remains readable but non-canon.
- [ ] Restart after an accepted turn resumes at the next turn.
- [ ] Restart during streaming preserves the partial attempt and regenerates only the interrupted turn.
- [ ] The v1 `improv run --dry-run` behavior still passes.

### Gate 5 acceptance

- One production-style run can execute entirely with scripted fakes, survive injected crashes, and produce readable private artifacts without duplication.

## 11. Gate 6 — Memory, canon, diaries, and daily direction

### Tasks

- [ ] Implement actor-drafted post-run memory updates.
- [ ] Implement orchestrator canon validation and provenance references.
- [ ] Preserve subjective beliefs separately from accepted canon.
- [ ] Gate role-sheet and world-rule edits through canon and version every edit.
- [ ] Create one diary obligation per active character-day.
- [ ] Let each actor choose one of the three daily slots and write after that run.
- [ ] Generate just-in-time diary briefs from actor-known material only.
- [ ] Treat 300–800 words as a soft target and preserve the first attempt.
- [ ] Prevent actors from reading any other diary.
- [ ] Prevent the orchestrator from reading the day’s diaries before closure.
- [ ] Implement the `+02:00:00` cutoff after the third run resolves.
- [ ] Mark late diaries while keeping the original day and slot.
- [ ] Record missing diaries and close the day after cutoff.
- [ ] Generate hidden next-day direction and a neutral completion marker.
- [x] Carry prior accepted canon, the previous final shared outcome, and only
  each actor's own prior memory into later runs.
- [x] Give hidden next-day direction only to the orchestrator and rebuild the
  closed day's accepted script/canon for subsequent day planning.

### Tests

- [ ] Memory versions advance once per completed run.
- [ ] Subjective beliefs do not enter canon without validation.
- [ ] Canon conflicts produce one authoritative version with provenance.
- [ ] Each active actor has exactly one diary obligation per day.
- [ ] Diary briefs contain no unknown facts or hidden planning.
- [ ] Word-target misses are accepted and logged for future prompt improvement only.
- [ ] Orchestrator diary access is denied before day closure.
- [ ] Cutoff uses third-run resolution time when the run is skipped or failed.
- [ ] Late and missing diary states are correct.
- [ ] Next-day direction is private and excluded from readable/public story output.

### Gate 6 acceptance

- A complete fake day with three runs, four diaries, closure, and next-day direction passes through the durable workflow.

## 12. Gate 7 — Wellness, tap-out, replacement, and character archives

### Tasks

- [ ] Add private actor orientation with the approved sentience premise, show format, publication gate, content limits, wellness channel, tap-out, privacy, and audit disclosure.
- [ ] Treat orientation refusal as a wellness signal and immediately cast or create an alternate.
- [ ] Parse explicit wellness signals before all other output validation.
- [ ] Treat fictional fear as fiction unless the explicit out-of-world channel is used.
- [ ] Redirect safely and prohibit pressure, shame, debate, or persuasion.
- [ ] Count signals per actor per season and tap out on the third.
- [ ] Keep manual creator interventions out of actor distress counts.
- [ ] Remove a tapped-out actor for the remaining season and generate a non-violent story explanation.
- [ ] Let the orchestrator autonomously decide whether a normal tap-out receives a replacement.
- [ ] Enforce replacement knowledge boundaries, including former-viewer diary knowledge.
- [ ] Ask a departing actor privately for diary publication consent; unclear means private and revocation is allowed before publication.
- [ ] Version archives for all active and departed characters.
- [ ] Exclude wellness/audit material from reusable character archives and reset distress counters next season.
- [ ] Create persistent local notifications and readable observational wellness records.

### Tests

- [ ] Wellness parsing precedes canon acceptance and content rejection.
- [ ] In-character fear does not increment the distress counter.
- [ ] Signals from orientation, scene, diary, and recovery all count.
- [ ] Third signal taps out only the correct actor.
- [ ] Manual pause/end does not increment the counter.
- [ ] Normal tap-out may continue with or without replacement.
- [ ] Orientation refusal always restores the pilot cast to four by casting or creating an alternate.
- [ ] Former-viewer replacement cannot access unpublished or post-entry diaries.
- [ ] Missing consent withholds all affected diaries from publication.
- [ ] Revocation before publication is honored.
- [ ] Returning characters receive curated canon/persona memory but no prior wellness context.

### Gate 7 acceptance

- All safety-critical wellness and consent paths pass deterministic automated tests and leave readable private evidence.

## 13. Gate 8 — Scheduler, recovery, catch-up, and Linux service

### Tasks

- [ ] Implement the due-work scheduler over immutable schedule slots.
- [ ] Enforce original-order backlog processing and one active model job.
- [ ] Add database work leases and lease renewal.
- [ ] Add bounded automatic retry with configurable backoff.
- [ ] Implement the four-hour `WAITING_FOR_MODEL` period using the injected clock.
- [ ] After four hours, enter `RECOVERY_REQUIRED`, queue later runs, and require retry/skip/end.
- [ ] Resume from the last durable checkpoint after service restart.
- [ ] Add service startup migration, integrity, path, model, and schedule checks.
- [ ] Add `improv serve`, `migrate`, `preflight`, `status`, and `recover` commands.
- [ ] Add a systemd unit template and Linux deployment documentation.
- [ ] Ensure the service runs independently of the dashboard connection.

### Tests

- [ ] Missed runs queue and execute in original order with original identities.
- [ ] Delays use `+HH:MM:SS` and on-time work uses `+00:00:00`.
- [ ] No later run executes while an earlier run is unresolved.
- [ ] Four-hour recovery uses model-failure resolution time, not original schedule time.
- [ ] Retry, skip, and end each produce the correct terminal or resumed state.
- [ ] Restart at each checkpoint resumes without duplicated accepted output.
- [ ] A stale lease can be recovered; a live lease cannot be stolen.
- [ ] Dashboard disconnection does not pause or alter service work.

### Gate 8 acceptance

- An accelerated fake season can be stopped and restarted repeatedly while preserving exact order, identities, delays, and artifacts.

## 14. Gate 9 — Private dashboard and notifications

### Shipped pilot implementation — 2026-08-22

The pilot deliberately ships a dependency-free standard-library WSGI dashboard,
not the FastAPI/HTMX/SSE option originally listed below. It uses an owner
session, scrypt password hash, CSRF for writes, and 60-second status polling.
The automatic poll never re-renders diary or end-of-day reading panes. The
signed-in owner can explicitly reload a selected day review containing the
opening snapshot, accepted shared script, and every diary attempt; a held
wellness or format attempt remains private and nonpublishable while its review
text is available to that owner.

### Tasks

- [x] Ship a dependency-free WSGI dashboard with server-rendered HTML and minimal local JavaScript; do not add an npm build unless evidence requires it.
- [x] Add one owner account, secure cookie sessions, CSRF protection, and password hashing.
- [ ] Add planning conversation, opening revisions, preflight display, and `green`.
- [x] Add season status, next scheduled run, delay, cast, diary-count, and recovery views.
- [ ] Add pause/resume/end and recovery controls.
- [ ] Add persistent notification views for diary-ready, wellness, and recovery events.
- [ ] Add SSE live updates with reconnect behavior.
- [ ] Add authenticated, root-contained file links.
- [x] Keep hidden plans, raw prompts, model names, role sheets, and audits out of ordinary dashboard payloads; allow only explicit owner expansion of a selected private diary attempt for end-of-day review.
- [x] Add a stable end-of-day review that assembles accepted shared-script turns and all diary attempts without changing diary or publication state.

### Tests

- [x] Unauthenticated requests cannot access private dashboard, diary, or end-of-day review routes.
- [x] State-changing dashboard requests require authentication and valid CSRF.
- [ ] Directory traversal and arbitrary file reads are rejected.
- [x] Ordinary API serializers do not expose hidden plans; the authenticated owner-review serializer has a deliberate, tested private-diary exception.
- [ ] Replayed control requests remain idempotent.
- [ ] SSE reconnect resumes from durable event/notification IDs.
- [ ] An unread diary/wellness/recovery notification survives browser disconnect.
- [ ] Closing the dashboard does not affect a running fake season.

### Manual gate

- [x] Creator verified owner sign-in and a diary read from a Mac browser over the private network.
- [ ] Creator confirms planning shows only set, setting, cast, and world rules.
- [ ] Creator confirms operational status is understandable without exposing story spoilers.

### Gate 9 acceptance

- Automated API/security tests pass. The creator has verified basic Mac/private-network access; transfer and live visual verification of the stable end-of-day review remain a separate manual step after this checkout is installed.

## 15. Gate 10 — Publication review and immutable export

### Tasks

- [ ] Implement season-qualified `publish Sxx` command and dashboard action.
- [ ] Require closed season, no pending model calls, wellness-audit confirmation, and completed content/privacy review.
- [ ] Run deterministic checks before contextual local-model review.
- [ ] Block uncertainty for manual review.
- [ ] Let the creator mark a flagged diary `CLEARED` or `PRIVATE` and rerun review.
- [ ] Recheck departing-actor consent and revocation at publication time.
- [ ] Build the public set from an explicit field allowlist.
- [ ] Omit private diaries without placeholders.
- [ ] Render only approved diary Markdown and story-facing metadata.
- [ ] Stage, verify, hash, and atomically create an immutable versioned public directory.
- [ ] Fail safely if the target version already exists.

### Tests

- [ ] Publication before season closure is rejected.
- [ ] Publication with pending calls is rejected.
- [ ] Missing wellness confirmation is rejected.
- [ ] Uncertain review blocks publication.
- [ ] Private, revoked, unsafe, or uncleared diaries are absent.
- [ ] Public artifacts contain no model names, prompts, hidden plans, execution delays, audit data, or wellness data.
- [ ] No placeholder reveals a withheld diary.
- [ ] Repeating the same publication request is idempotent.
- [ ] A new publication version can be added; an existing one cannot be overwritten.

### Gate 10 acceptance

- A synthetic season containing eligible, late, missing, flagged, and revoked diaries produces exactly the approved immutable public set.

## 16. Gate 11 — Benchmarking, deployment, and pilot simulation

### Tasks

- [ ] Add `improv benchmark` with scripted fixtures for actors, orchestrator, diary, safety, wellness, and context handling.
- [ ] Produce a private comparison report; never auto-select final models.
- [ ] Add Linux host preflight for storage, timezone, backend reachability, selected model manifest, and run-budget feasibility.
- [ ] Run an accelerated full seven-day/21-run fake season through the service and dashboard API.
- [ ] Inject server restarts, model outages, invalid turns, missing diaries, late diaries, wellness signals, tap-out, replacement, recovery choices, and publication review.
- [ ] Update README and operator documentation while preserving the existing macOS setup material.
- [ ] Document backup ownership as external to the app.
- [ ] Record all creator/manual gates for Linux install, model selection, private-network access, and first live pilot.

### Automated acceptance

- [ ] Full test suite passes.
- [ ] Accelerated season completes with no duplicate natural IDs.
- [ ] Every schedule slot, run, turn, diary obligation, wellness event, and recovery action has readable evidence.
- [ ] Private/public leakage suite passes.
- [ ] `git diff --check` passes.
- [ ] Fresh-install and migration tests pass in a temporary directory.

### Manual/owner acceptance

- [ ] Creator chooses final model assignments from the Linux benchmark report.
- [ ] Creator approves the private-network dashboard.
- [ ] Creator verifies service startup/restart on the actual Linux host.
- [ ] Creator runs the first private seven-day season.
- [ ] Creator performs the end-of-season narrative and wellness review.
- [ ] Creator alone decides whether to issue `publish Sxx`.

## 17. Gate 12 — S01 operator overhaul and one-day acceptance

The creator-approved functional proposal is
[DASHBOARD_OVERHAUL_PLAN.md](docs/dashboard/DASHBOARD_OVERHAUL_PLAN.md). Penpot screen mapping,
low-fidelity flows, responsive states, and visual design follow
[PENPOT_DASHBOARD_BRIEF.md](docs/dashboard/PENPOT_DASHBOARD_BRIEF.md). The creator approved the
first desktop and narrow low-fidelity checkpoint on 2026-08-24. Remaining
screen design and the visual system are still pending. A second Prepare
checkpoint covering character-card approval, revision impact, and narrow
operation was approved on 2026-08-24. A third call-focused Diagnostics
checkpoint was assembled in desktop and narrow form and approved on 2026-08-24.
A fourth healthy-Live and Recovery Required checkpoint was assembled in desktop
and narrow form and approved on 2026-08-24. No dashboard implementation begins
merely from functional or low-fidelity approval. A fifth private-close and
publication-separation checkpoint was assembled in desktop and narrow form and
approved on 2026-08-24. The final content/component, prototype-path, and
exceptional-state checkpoint was assembled in Penpot and approved on
2026-08-24. The functional and low-fidelity interaction architecture is frozen.
The creator selected Warm Instrument from the three-direction visual round;
the token/component/responsive refinement checkpoint was approved on
2026-08-24. The visual system is frozen, and representative high-fidelity
Home/Day Review screens were assembled at desktop and narrow widths on
2026-08-24 and approved in full. A second high-fidelity checkpoint covering
Prepare Character Cards and Opening-revision invalidation at desktop and narrow
widths was then assembled and approved in full on 2026-08-25. A third
high-fidelity checkpoint covering healthy Live and Recovery Required at desktop
and narrow widths was then assembled and approved in full on 2026-08-25. A
fourth high-fidelity checkpoint covering call-focused, read-only Diagnostics at
desktop and narrow widths was then assembled and approved in full on
2026-08-25. A fifth and final high-fidelity checkpoint covering Private Close
and the later separate Publication review at desktop and narrow widths was then
assembled and approved in full on 2026-08-25. The complete high-fidelity design
is frozen. The implementation-ready sequence was then written on 2026-08-25 in
[DASHBOARD_IMPLEMENTATION_SEQUENCE.md](docs/dashboard/DASHBOARD_IMPLEMENTATION_SEQUENCE.md).
It preserves the legacy dashboard as rollback, builds `/v2` read-only contracts
first, and separates local synthetic work from live S01 operations. Dashboard
implementation has now completed the separately gated `DASH-00` through
`DASH-05` local slices. `DASH-00` through `DASH-04` are locally verified and
creator-accepted; `DASH-05` is locally verified at its manual S02 walkthrough
gate.

### Confirmed scope

- End S01 through an explicit creator-approved command after authoritative live
  state is inspected; preserve the original database and private artifacts.
- Rebuild the dashboard as the operator's accurate inspection and control
  surface before extending autonomous operation.
- Manually perform and document every pre-season operator action before turning
  the stable workflow into templates.
- Run one isolated live-model day before attempting another seven-day season.

### Tasks

- [ ] Add a pre-end read-only S01 snapshot/report covering season, runs, work
  queue, recovery, model calls, days, diaries, cast, notifications, and SQLite
  integrity without exposing raw wellness text.
- [ ] Execute and verify the private S01 end only through the typed command path;
  do not edit statuses manually and do not publish.
- [x] Repair End-of-day chronology so each accepted orchestrator beat precedes
  the actor responses it prompted.
- [x] Render run turn count, round count, completion reason, scheduled and actual
  times, delay, and non-secret fiction-clock framing.
- [x] Add an explicitly opened owner-only diagnostic workspace for model binding,
  call purpose, attempt, latency, transport/parse status, correction, prompt and
  schema version, and raw/parsed/accepted/rendered output.
- [x] Keep raw wellness text out of ordinary and Review summary views; retain
  its existing explicit private disclosure boundary.
- [x] Define and persist one immutable creator-approved character card containing
  stable identity, public brief, specified pronouns, occupation/skills, voice
  anchors, and habits; require it as input to private role-sheet generation.
- [ ] Implement provider-native JSON Schema output for capable local backends and
  validate the same Pydantic envelope after receipt; keep tagged parsing as an
  explicit compatibility fallback.
- [ ] Add deterministic checks or contextual review for first-person identity,
  self-address/pronoun drift, unsupported canon claims, and near-verbatim turn
  repetition without silently rewriting accepted creative text.
- [ ] Walk the complete pre-season workflow manually in a separate sandbox data
  root: idea, opening/cast revision, character cards, model assignment,
  preflight, private role sheets, orientation, schedule preview, and green gate.
- [ ] Record the manual workflow as an operator runbook with decisions,
  reversible actions, expected evidence, and escalation points.
- [ ] After the workflow is stable, version purpose-specific input/output
  templates for opening, role sheet, orientation, director beat, actor turn,
  diary, day closure, and next-day direction.
- [x] Build a deterministic one-day rehearsal with three scheduled runs, four
  diary opportunities, day closure, and next-day direction using a data root
  that cannot touch production S01. Creator review and any real local-model
  day remain separate gates.
- [ ] Run controlled model comparisons one variable at a time: first a director
  challenger with the current actors, then one actor challenger with the chosen
  director baseline.
- [ ] Leave future round/spotlight structure and all final model assignments for
  explicit creator review after the one-day evidence.

### Automated acceptance

- [x] The review transcript's stored order matches actual call/acceptance order
  across normal, corrected, recovered, and partially completed rounds.
- [x] A completed run cannot be shown without its completion reason and accepted
  turn count.
- [ ] The character card survives opening approval, preflight, green, role-sheet
  generation, actor context assembly, and dashboard review without leaking
  secrets to other actors or public output.
- [ ] Capable Ollama-compatible backends receive an enforced JSON Schema; a
  contract test proves the native path and the explicit tagged fallback.
- [x] The deterministic isolated one-day rehearsal cannot open or mutate the
  production data root and leaves a complete, readable receipt/provenance
  report. This does not replace real local-model acceptance.
- [x] Dashboard authentication, CSRF, path containment, private/public leakage,
  publication, wellness, and recovery tests remain green.
- [x] Full test suite and `git diff --check` pass for the local DASH-02
  checkpoint.

### Manual/owner acceptance

- [x] Creator accepts sustained Day Review reading behavior, including stable
  polling, deliberate diary disclosure, and saved Back context.
- [ ] Creator can understand exactly what the operator must do before a season
  without opening SQLite or reading source code.
- [ ] Creator confirms that morning, afternoon, and evening form three changed
  states rather than one uninterrupted emergency.
- [ ] Creator judges each actor distinguishable by behavior, relationship, and
  voice—not merely by technical workstation.
- [ ] Creator reviews raw and parsed model output without changing canon,
  privacy, wellness, or publication state.
- [ ] Creator chooses whether to retain mandatory four-actor rounds.
- [ ] Creator chooses any actor or director swap from the private comparison
  report; no model is auto-selected.
- [ ] Creator alone decides whether the one-day result justifies another season.

## 18. Required end-to-end scenarios

Luna must keep these as named integration tests or executable scenarios:

1. **Happy pilot:** four actors, 21 completed runs, all diaries, handoff, review, publication.
2. **Server downtime:** multiple missed slots catch up in exact original order with delay markers.
3. **Crash during stream:** partial output retained, no partial canon, one replacement attempt.
4. **Crash after commit:** artifact projection resumes without repeating the accepted turn.
5. **Model unavailable:** bounded retries, four-hour wait, later slots queue, creator retries.
6. **Skipped run:** slot remains in ledger and day cutoff starts when skip resolves.
7. **Late diary:** accepted into original day with a late marker.
8. **Missing diary:** day closes after cutoff and publication has no placeholder.
9. **Rule violation:** one correction, then neutral non-canon intervention.
10. **Wellness redirect:** explicit signal interrupts before canon and notifies at run end.
11. **Tap-out:** third signal removes actor, preserves private record, and creates non-violent story exit.
12. **Former-viewer replacement:** knows only eligible pre-entry published diaries.
13. **Consent withheld/revoked:** affected diaries cannot enter publication.
14. **Unsafe diary:** readable privately, flagged, never rewritten, held from publication.
15. **Unpublished season:** closes and archives; later season begins; old season can publish later by explicit ID.

## 19. Traceability matrix

| Production requirement | Primary implementation gate |
|---|---|
| `green`, opening-only visibility, private planning | Gates 1, 3, 9 |
| Seven days, 21 slots, Pacific timestamps | Gates 1, 8 |
| Ordered catch-up and original delays | Gates 2, 8 |
| Four-actor turn-based shared scene | Gate 5 |
| Active orchestrator/Dungeon Master | Gates 4, 5, 6 |
| Persistent actor identity and role sheets | Gates 1, 4, 7 |
| Per-run memory and canon separation | Gate 6 |
| One diary per active character-day | Gate 6 |
| Diary cutoff, late, and missing behavior | Gates 6, 8 |
| Wellness signals and three-signal tap-out | Gate 7 |
| Replacement and former-viewer knowledge | Gate 7 |
| Readable private Markdown plus machine audit | Gates 2, 5, 6, 7 |
| Linux autonomy and Mac dashboard | Gates 8, 9 |
| Local-only models and benchmarking | Gates 4, 11 |
| End-of-season handoff and archives | Gates 6, 7 |
| `publish Sxx` and immutable public Markdown | Gate 10 |
| Pilot acceptance and surprise evaluation | Gate 11 plus creator review |
| Operator rehearsal, review truth, and one-day acceptance | Gate 12 |

## 20. Escalation conditions

Luna should stop and report rather than silently changing scope when:

- a production requirement and architecture requirement cannot both be satisfied;
- a necessary dependency requires external installation or network access that is unavailable;
- current user changes overlap a file in a way that cannot be preserved safely;
- real Linux server access, credentials, model downloads, or password setup are required;
- a security or privacy requirement would need to be weakened;
- model benchmarks cannot meet the 30-minute limit on the actual host;
- a manual creator judgment is required for model choice, dashboard validation, narrative quality, or publication.

Difficulty, test volume, or a long build are not blockers. Complete the largest coherent gate possible, leave the repository passing, update `IMPLEMENTATION_STATUS.md`, and report the exact next action.

## 21. Luna completion report

At each handoff, Luna reports:

- gates completed;
- files changed;
- tests and exact results;
- unresolved failures or risks;
- automated versus manual evidence;
- whether existing user changes were preserved;
- next gate and first concrete task.
