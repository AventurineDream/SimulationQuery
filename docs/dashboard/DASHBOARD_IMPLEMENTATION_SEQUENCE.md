# Simulation Query dashboard — implementation sequence

**Status:** `DASH-00` through `DASH-04` implemented, locally verified, and
creator-accepted; separately authorized `DASH-05` implemented and locally
verified at its manual S02 creator gate; separately authorized `DASH-06` is
implemented and locally verified in a disposable S02 fixture, with its creator
walkthrough still open. Separately authorized `DASH-07` now has a deterministic
nonproduction one-day rehearsal and runbook; creator review and any real
local-model day remain open. `DASH-08+`, deployment, S01 private close, and any
real publication have not started.

**Updated:** 2026-08-27

**Owner:** creator

**Product source:** [DASHBOARD_OVERHAUL_PLAN.md](DASHBOARD_OVERHAUL_PLAN.md)

**Design source:** [PENPOT_DASHBOARD_BRIEF.md](PENPOT_DASHBOARD_BRIEF.md)

**Production handoff:** [IMPLEMENTATION_STATUS.md](../../IMPLEMENTATION_STATUS.md)

## 1. Outcome

Replace the current private dashboard with the approved Warm Instrument
operator console while preserving the existing durable service, authentication,
privacy, command, and archive boundaries.

The completed dashboard must let the creator operate the full lifecycle without
opening SQLite or using the terminal:

1. understand current durable truth from Home;
2. prepare and approve a season through a guided workspace;
3. supervise autonomous work without keeping the browser open;
4. read accepted story and private diaries in causal order;
5. explain an individual model call without rerunning it;
6. resolve recovery only after reviewing consequences;
7. close a season privately without publishing;
8. review and create a separate immutable public projection later.

Implementation uses synthetic S02 data until the local dashboard passes its
acceptance gates. No build step in this plan may read, mutate, end, or publish
the live S01 season.

## 2. Authorization boundary

The creator authorized this implementation-ready sequence on 2026-08-25. That
authorization covers planning and durable handoff only.

The creator separately authorized and accepted `DASH-00`, then `DASH-01`, then
`DASH-02`, then `DASH-03`, then `DASH-04`, and separately authorized `DASH-05`. Ticket-specific
authorization does not carry forward across later creator gates.

The following remain separate explicit decisions:

- accepting `DASH-05`, `DASH-06`, or `DASH-07`, or beginning `DASH-08` or any later ticket;
- inspecting authoritative live Linux state;
- ending S01 privately;
- deploying or restarting the dashboard or worker;
- running a real local model;
- publishing any season;
- selecting or downloading replacement models.

## 3. Verified starting point

Current local evidence on 2026-08-25:

- `112 passed` in `6.48s` with `./.venv/bin/python -m pytest -q`;
- `git diff --check` passes;
- the checkout already contains extensive modified and untracked creator work,
  which must remain intact;
- the private dashboard is a dependency-free standard-library WSGI app;
- owner login uses scrypt, in-memory sessions, strict cookies, and CSRF for
  every POST;
- the worker and scheduler remain independent of the dashboard connection;
- current authenticated routes are:
  - `GET /api/status`;
  - `GET /api/diaries`;
  - `GET /api/day-review`;
  - `POST /api/recover`;
  - `POST /api/publish`.

### Current implementation gaps

1. `src/improv_troupe/web/dashboard.py` is approximately 1,100 lines and
   combines routing, authentication, SQL-backed read models, HTML, CSS,
   JavaScript, private artifact reads, recovery, and publication.
2. The status read model does not yet provide the complete Home/Live truth,
   causal accepted-beat summary, completion evidence, or worker freshness
   required by the approved screens.
3. The current diary and day-review payloads can include raw private model
   attempts in the normal authenticated response. The approved design requires
   a separate deliberate-disclosure request and excludes raw wellness text from
   ordinary Review and Diagnostics payloads.
4. Current recovery can submit `retry`, `skip`, or `end` directly. It lacks the
   separate impact review, expected-version check, and durable receipt contract
   shown in the approved design.
5. The preserved legacy publication route can begin review and publish from one
   POST. The v2 Seasons route now supplies the staged private-close receipt,
   exact preview, explicit intent, and immutable-receipt journey; the legacy
   route remains untouched pending a later deployment decision.
6. Prepare and call-focused Diagnostics do not yet have dedicated dashboard read
   contracts.
7. The migration runner currently assumes one `001_initial.sql` migration. It
   must support future numbered migration files before new durable records are
   introduced.
8. Dashboard coverage currently centers on authentication/status/diaries and
   day review. Every new surface needs route, privacy, responsive, keyboard, and
   stable-reading acceptance.

## 4. Frozen implementation constraints

These are acceptance requirements, not optional styling preferences:

- keep the dashboard private-network and single-owner;
- retain the standard-library WSGI server and avoid an npm application build
  unless implementation evidence later proves it necessary;
- keep SQLite and private artifacts authoritative;
- never require the browser to remain open for worker progress;
- preserve selected season and relevant run/day context across navigation;
- poll only operational chrome; never replace an open transcript, diary,
  disclosure, form, selection, or scroll position;
- keep hidden plans, raw prompts, private role sheets, model identities, and raw
  wellness text out of default payloads and views;
- make raw artifact access deliberate, owner-only, path-contained, and
  non-mutating;
- make every consequential action season-qualified, version-guarded,
  CSRF-protected, idempotent, and receipt-producing;
- distinguish stale-readable, disconnected, partial, missing, loading, empty,
  invalid-path, and command-conflict states;
- support the approved desktop rail at `920px` and above and narrow bottom
  navigation below `920px`;
- preserve visible focus, complete keyboard operation, reduced motion, and
  readable authored-text typography;
- use only synthetic S02 fixtures until local automated and creator review gates
  pass.

## 5. Target internal architecture

The redesign remains one Python package and one WSGI process. The current file
is divided by responsibility before feature growth:

```text
src/improv_troupe/web/
  dashboard.py                 authentication, WSGI routing, response boundary
  dashboard_contracts.py       versioned request/response models
  dashboard_read_models.py     read-only SQL/application projections
  dashboard_commands.py        impact validation and command adapters
  dashboard_views.py           escaped HTML shell and page composition
  static/
    dashboard.css              Warm Instrument tokens and responsive components
    dashboard.js               navigation, reads, stable polling, disclosures
```

This split must not change behavior by itself. The legacy page and routes remain
available until the replacement completes creator acceptance.

### 5.1 Rollout routing

- Keep the existing `/` dashboard as the rollback surface during development.
- Serve the new shell at `/v2/home`, with `/v2/prepare`, `/v2/live`,
  `/v2/review`, `/v2/diagnostics`, and `/v2/seasons` as deep-linkable pages.
- Add new JSON contracts under `/api/v2/...`.
- Do not remove or silently repurpose the existing routes during the build.
- After creator acceptance, switch `/` to the new Home and retain `/legacy`
  for one deployment cycle.
- Remove the legacy surface only in a later, separately reviewed cleanup.

### 5.2 Read-contract envelope

Every `/api/v2` read response uses the same envelope:

```json
{
  "meta": {
    "contract_version": 1,
    "checked_at": "timestamp",
    "environment": "sandbox",
    "season_id": "S02",
    "season_version": 18,
    "freshness": "fresh"
  },
  "data": {}
}
```

`freshness` is derived from evidence and may be `fresh`, `stale_readable`,
`disconnected`, or `partial`. It is never inferred from color alone.

### 5.3 Private disclosure contract

Default Review and Diagnostics responses contain metadata and accepted text only
where that screen explicitly requires it. Review fetches safely separated diary
text from a separate resource; it does not return the raw response envelope or
wellness wording:

```text
GET /api/v2/review/diary-attempt?season_id={season_id}&diary_id={diary_id}
GET /api/v2/diagnostics/calls/{call_id}/raw
```

The Diagnostics raw route above remains a later-ticket example, not a current
endpoint.

Requirements:

- authenticated owner session;
- opaque record ID, never a client-supplied filesystem path;
- server-side private-root containment;
- `Cache-Control: no-store`;
- deliberate UI action and visible private warning;
- no state change, acceptance, wellness clearance, canon mutation, or
  publication eligibility change;
- raw wellness text is not available through the ordinary Diagnostics route.

### 5.4 Command contract

Every new mutation follows one pattern:

1. fetch a read-only impact review;
2. show current durable truth and exact consequences;
3. require the creator's explicit selection or typed season intent;
4. submit CSRF, `request_id`, aggregate ID, `expected_version`, and the review
   snapshot/hash;
5. reject stale or conflicting state without partial mutation;
6. return a durable command receipt;
7. refetch authoritative state before the UI claims success.

Navigation, opening a disclosure, refreshing a read, or closing the browser can
never submit a command.

### 5.5 Migration contract

Before adding schema version 2:

- update the migration loader to discover exactly one file matching each
  numbered prefix;
- verify a clean database, a version-1 database, and repeated migration;
- permit additive tables, columns, and indexes only;
- do not rename, rewrite, delete, or reinterpret S01 records;
- record schema version and integrity in every dashboard snapshot;
- stop if legacy chronology or preparation provenance cannot be backfilled
  honestly.

## 6. Ordered build sequence

| Ticket | Deliverable | Depends on | Creator gate |
|---|---|---|---|
| DASH-00 | Baseline, fixture, module split, migration runner | frozen design | code-start approval |
| DASH-01 | New shell, navigation, shared contracts, Home | DASH-00 | Home desktop/narrow |
| DASH-02 | Causal Day Review and deliberate private disclosure | DASH-01 | long-reading review |
| DASH-03 | Read-only call-focused Diagnostics | DASH-02 | evidence explanation |
| DASH-04 | Versioned Prepare workspace | DASH-03 | manual pre-season rehearsal |
| DASH-05 | Live supervision and consequence-first Recovery | DASH-04 | safe operation/recovery |
| DASH-06 | Seasons, Private Close, and separate Publication | DASH-05 | consequential lifecycle review |
| DASH-07 | Isolated one-day acceptance and operator runbook | DASH-06 | creator one-day decision |

Do not combine tickets across a creator gate. Each completed ticket must leave a
usable read-only or safely bounded operator surface.

## 7. Ticket specifications

### DASH-00 — protect the baseline and create the implementation seam

**Purpose:** make the redesign safe to build without changing current behavior.

**Implementation status:** code-complete and verified locally on 2026-08-25;
creator-accepted on 2026-08-26. The legacy root remains unchanged, and the
empty `/v2/home` seam is authenticated and disabled by default unless the
dashboard is launched explicitly with `--enable-v2`. This acceptance closes
`DASH-00`; it did not itself authorize `DASH-01`, which the creator authorized
separately afterward.

Recorded evidence: the protected baseline was `112 passed`; the completed
slice passes `119` tests, Python compilation, direct syntax checks for both
JavaScript files, dashboard CLI help, and `git diff --check`. Synthetic browser
checks passed at `1440×1024` and `390×844` for legacy and v2 with no horizontal
overflow or console warnings/errors. The v2 shell had zero forms and zero
buttons, and its desktop rail changed to narrow bottom navigation at the
approved breakpoint. No deployment or production-path access occurred.

**Work:**

- record the `112 passed` baseline and exact dirty-worktree scope;
- create one deterministic synthetic S02 dashboard fixture with healthy,
  partial, recovery, private-diary, failed-call, and private-complete states;
- split the embedded dashboard into the target modules and packaged static files;
- keep current HTML, API routes, status codes, authentication, CSRF, cookies,
  and 60-second stable-poll behavior unchanged;
- add `/v2/home` behind a local-development default that renders an empty new
  shell without mutations;
- make the migration runner support future numbered files without applying a
  new migration yet;
- extract dashboard JavaScript into a file that can be syntax-checked directly;
- add security headers compatible with external static assets.

**Automated acceptance:**

- all current tests remain green;
- existing route contract tests pass byte-for-byte or by approved semantic
  equivalence;
- legacy dashboard renders at desktop and `390px` without new console errors;
- `node --check` passes for the extracted JavaScript;
- unauthenticated `/v2/*` and `/api/v2/*` requests are rejected;
- migration from a version-1 fixture is additive, idempotent, and integrity
  `ok`;
- no test or fixture can resolve to the configured production data root;
- `git diff --check` passes.

**Stop conditions:** unexpected production-path access, destructive migration,
auth/CSRF regression, hidden baseline change, or unrelated worktree overwrite.

### DASH-01 — shared shell and trustworthy Home

**Purpose:** deliver the first usable read-only new dashboard slice.

**Implementation status:** code-complete, locally verified, and
creator-accepted on 2026-08-26. The legacy root is still unchanged, v2 is still
default-disabled, and every v2 destination carries the selected season and
environment through the shared read-only shell.

Recorded evidence: strict `/api/v2/context` and `/api/v2/home` projections now
cover lifecycle, read freshness, SQLite/storage integrity, queue and lease
evidence, operator attention, durable run/day progress, the latest readable
accepted beat, next schedule, cast, day completion, and recent seasons. At that
checkpoint the accepted-beat response explicitly labeled its ordering as
derived because schema version 1 had no causal accepted-turn timestamp. The
completed local suite is
`126 passed`; Python compilation, JavaScript syntax checking, and
`git diff --check` pass. Authenticated browser checks at `1440×1024` and
`390×844` confirmed the approved rail/bottom-nav switch, information order,
season-preserving Review/Back navigation, exact viewport-width layout with no
horizontal overflow, and no console warnings/errors. No live Linux path,
deployment, worker operation, model call, S01 close, recovery command, private
publication, or public release was touched.

**Creator decision:** the creator accepted the rendered desktop and narrow Home
checkpoint on 2026-08-26. This closes `DASH-01`; it does not authorize
`DASH-02`, deployment, live Linux inspection, S01 private close, worker or model
operation, recovery, or publication.

**Work:**

- implement the Warm Instrument token set and responsive shell;
- implement rail navigation at `920px+` and bottom navigation below `920px`;
- add stable season/environment context to every destination;
- implement `/api/v2/context` and `/api/v2/home` read models;
- show lifecycle, integrity, freshness, worker/queue truth, attention count,
  durable progress, Last accepted beat, next schedule, day-completion state, and
  recent seasons;
- add explicit loading, no-season, stale-readable, disconnected, and partial
  states;
- keep all controls read-only in this ticket;
- preserve the selected season through URL parameters and browser navigation.

**Automated acceptance:**

- Home never claims healthy, running, fresh, or complete without stored evidence;
- no hidden plan, raw prompt, role sheet, model identity, raw wellness text, or
  unrestricted private path appears in HTML or JSON;
- selected season remains stable across Home and Review links;
- narrow and desktop DOM order match the approved information hierarchy;
- focus order is complete and no horizontal overflow appears at `390px`;
- polling updates global truth without replacing selected content;
- authentication, CSRF, private-root, and full-suite tests remain green.

**Creator gate:** compare real rendered `/v2/home` against the approved desktop
and narrow Home references before DASH-02.

### DASH-02 — causal Day Review and stable reading

**Purpose:** make accepted story and private diary review trustworthy.

**Implementation status:** code-complete, locally verified, and creator-accepted
on 2026-08-26. Schema version 2 adds nullable accepted sequence, cause-link,
and accepted-time evidence for new turns while leaving migrated legacy turns
null and visibly derived. Strict
`/api/v2/review/day` and `/api/v2/review/diary-attempt` projections, the
responsive Review workspace, explicit newer-material loading, locally saved
day/run/tab/disclosure/scroll state, and summary-only default diary cards are
implemented. The deliberate diary route returns only safely parsed diary text
plus a wellness-presence boolean; it never returns the raw response envelope or
wellness wording.

Recorded evidence: **133 tests passed in 8.05 seconds**. Focused fixtures cover
persisted normal order, corrected acceptance, recovered completion, partial
runs, and legacy derived order; the disclosure test proves no diary, canon,
wellness, or publication mutation and a path-escape test fails closed. Direct
JavaScript syntax and Python compilation pass. Authenticated disposable browser
checks at `1440×1024` and `390×844` confirmed causal director-before-actor
reading, visible completion reason/count evidence, deliberate held-diary
disclosure with wellness wording withheld, keyboard tabs, exact-width layout
without horizontal overflow, long unbroken text wrapping, run switching, and
Back restoration of the saved day/run/scroll and open disclosure. Operational
polling only stages a newer envelope and does not replace the open reader DOM.
No live Linux path, deployment, worker/model operation, S01 close, recovery
command, private publication, or public release was touched.

**Work:**

- add a persisted accepted-sequence field for new turns or another explicit
  causal-order record;
- render legacy turns with a labeled derived order only where durable ordering
  evidence is incomplete;
- ensure each accepted director beat precedes the actor responses it prompted;
- expose run status, accepted turn count, round count, completion reason,
  scheduled/actual times, delay, day close, and non-secret fiction-clock frame;
- implement `/api/v2/review/day` with summaries that omit raw private attempts;
- implement a separate deliberate diary-attempt disclosure route;
- preserve open transcript/diary panes, disclosure state, and scroll position
  during operational polling;
- show missing, held, late, partial, corrected, recovered, and unavailable
  evidence honestly;
- distribute cast status, canon, unresolved continuity, and memory-version links
  without creating an extra primary destination.

**Automated acceptance:**

- normal, corrected, recovered, and partial fixtures render in causal order;
- a `COMPLETED` run always has visible completion reason and accepted turn count;
- default day-review JSON contains no raw private or wellness attempt;
- deliberate disclosure cannot alter diary status, canon, wellness, or
  publication eligibility;
- repeated status polls do not replace the open reading DOM subtree;
- browser Back returns to the saved day/run/scroll context;
- desktop, narrow, keyboard, and long-text checks pass.

**Creator decision:** accepted on 2026-08-26. The creator accepted the actual
rendered sustained-reading checkpoint. This closes `DASH-02` only; it does not
authorize `DASH-03`, deployment, live Linux inspection, S01 private close,
worker/model operation, recovery, or publication.

### DASH-03 — call-focused read-only Diagnostics

**Purpose:** explain one model call from request through accepted evidence.

**Implementation status:** code-complete, locally verified, and creator-accepted
on 2026-08-27. Schema version 3 adds
nullable call provenance and downstream-stage evidence without inventing values
for legacy calls. The default-disabled local fixture distinguishes successful,
transport-failed, parse-failed, and validation-failed calls.

**Work:**

- add `/api/v2/diagnostics/calls` filters for season, run, character, purpose,
  status, attempt, and error;
- add `/api/v2/diagnostics/calls/{call_id}` for binding, timing, finish,
  transport, parse, correction, validation, acceptance, and render stages;
- persist response-format mode and prompt, schema, context, role-sheet, and
  character-card version identifiers for new calls;
- label missing legacy provenance as unavailable rather than guessing;
- expose raw output only through the deliberate disclosure route and exclude raw
  wellness attempts entirely from ordinary Diagnostics;
- link the selected call back to its exact causal Review position;
- include no rerun, benchmark, bulk comparison, model download, or automated
  model-selection controls.

**Automated acceptance:**

- slow, transport-failed, parse-failed, corrected, validation-failed, accepted,
  and rendered fixtures remain distinguishable;
- raw, parsed, validated, accepted, and rendered are never collapsed into one
  ambiguous status;
- opening Diagnostics or raw evidence causes zero model calls and zero writes;
- all displayed version IDs correspond to stored records;
- forbidden private fields fail an explicit payload-leakage test;
- the return-to-Review link restores the precise accepted position.

**Creator gate:** accepted on 2026-08-27 after review of successful and failed
synthetic call explanations. This acceptance closed DASH-03 only.

### DASH-04 — versioned Prepare workspace

**Purpose:** let the creator manually perform every pre-season operator action
before templates or new season automation are added.

**Implementation status:** code-complete, locally verified, and creator-accepted on 2026-08-27.
Schema version 4 additively stores preparation workspaces, card and assignment
versions, receipts, invalidations, and idempotent action responses. A fresh
isolated S02 fixture walkthrough and runbook were creator-accepted.

**Work:**

- add additive storage for season idea, immutable character-card versions,
  model-assignment versions, preflight receipts, preparation approvals, and
  invalidation events;
- implement the full eight-step checklist with one focused workspace;
- preserve current approved truth beside any draft revision;
- make dependency invalidation explicit before save;
- implement creator-authored character cards as a required stable input to
  private role-sheet generation;
- keep private role-sheet/orientation content behind deliberate disclosure;
- implement model assignment and preflight as evidence, not automatic selection;
- implement schedule preview and a separate Green impact review;
- prohibit edits after Green except through explicit versioned revision paths;
- write the manual operator rehearsal record while the creator performs it.

**Automated acceptance:**

- every revision creates a new version and auditable invalidation event;
- prior approved versions remain readable;
- a character card survives preflight, Green, role-sheet generation, actor
  context assembly, Review, and public-projection exclusion;
- changing Opening cannot silently preserve dependent approvals;
- model assignment never downloads, swaps, or selects a model automatically;
- Green remains separate, season-qualified, version-checked, and receipt-backed;
- production S01 is unreachable from the sandbox fixture.

**Creator gate:** manually complete the entire pre-season checklist in the
isolated S02 fixture and approve the resulting operator runbook in
[DASH04_PREPARATION_REHEARSAL.md](rehearsals/DASH04_PREPARATION_REHEARSAL.md).

**Creator decision:** accepted on 2026-08-27. This closed DASH-04 only; the
creator then separately authorized DASH-05.

### DASH-05 — Live supervision and consequence-first Recovery

**Purpose:** supervise autonomous work and resolve only genuine creator decisions.

**Implementation status:** code-complete and locally verified on 2026-08-27.
Schema version 5 adds recovery versions; authenticated Live, stable transcript,
impact-review, guarded action, and durable-receipt paths are implemented for
disposable sandbox S02 fixtures. The creator gate remains open in
[DASH05_LIVE_RECOVERY_REHEARSAL.md](rehearsals/DASH05_LIVE_RECOVERY_REHEARSAL.md).

**Work:**

- implement Live worker, lease, queue, schedule, run, call-progress, accepted
  progress, day-close, and next-direction truth;
- keep one Last accepted beat and stable transcript with explicit newer-material
  loading;
- implement valid pause/resume controls with impact review and durable receipts;
- replace direct recovery mutation with read-only consequence review followed by
  one explicit `retry` or `skip` confirmation;
- route private end into the separate Seasons/Private Close review instead of
  submitting it from Recovery;
- require expected season/run/recovery versions and a review snapshot/hash;
- preserve failed calls, queue position evidence, and the exact last accepted
  causal anchor;
- render command conflicts and stale reviews without retrying automatically.

**Automated acceptance:**

- closing the dashboard never changes worker progress;
- invalid output never appears in canon, transcript, or accepted counts;
- retry, skip, pause, and resume are idempotent and receipt-producing;
- retry cannot be overtaken by later scheduled work;
- no recovery path is preselected;
- stale-version and duplicate-request fixtures fail safely;
- status polling cannot replace the transcript or an open impact review.

**Creator gate:** complete healthy supervision plus retry and skip rehearsals on
synthetic data; private end stops at the next ticket's review boundary.

### DASH-06 — Seasons, Private Close, and separate Publication

**Purpose:** preserve the private archive first and make publication an optional
later projection.

**Work:**

- build a versioned closure snapshot covering runs, work, calls, days, diaries,
  cast, notifications, integrity, archive reachability, and unresolved work;
- add an explicit private-close command with typed `end S02 privately` intent,
  expected version, snapshot/hash, request ID, and durable receipt;
- verify closure/handoff work and terminal `PRIVATE_COMPLETE` before claiming
  success;
- keep unresolved work labeled unresolved after close;
- expose archive and handoff reachability without unrestricted filesystem paths;
- split publication into eligibility, diary decisions, exact allowlisted preview,
  typed `publish S02` intent, immutable projection, manifest, and receipt;
- prove that publication cannot alter the private archive;
- structurally exclude plans, prompts, raw calls, model identities, role sheets,
  actor-local memory, wellness text, and held/missing/revoked diaries.

**Automated acceptance:**

- private close publishes, deletes, rewrites, or clears nothing;
- refresh/navigation cannot close or publish;
- exact intent, aggregate version, and snapshot mismatch all fail closed;
- unresolved work survives closure and appears in the receipt;
- publication cannot begin before `PRIVATE_COMPLETE`;
- exact preview and generated public artifact contain the same allowlisted fields;
- private-root escape, missing consent, held diary, and stale-review fixtures fail;
- repeated publish request returns the same immutable receipt;
- private archive hashes remain unchanged after publication.

**Creator gate:** rehearse Private Close and Publication on disposable synthetic
seasons without submitting either action against S01.

### DASH-07 — isolated one-day acceptance and runbook

**Purpose:** decide whether the workflow is reliable enough for another season.

**Work:**

- create an isolated data root that cannot resolve to production paths;
- run one day with morning, afternoon, and evening as three changed states;
- complete three runs, four diary opportunities, day close, and next-day
  direction;
- capture the complete operator runbook, receipts, provenance, unresolved
  questions, and creator judgments;
- run model comparisons one variable at a time only after the dashboard and
  manual workflow are stable;
- create reusable operator/actor templates only after the one-day evidence shows
  which fields and decisions are actually stable.

**Automated acceptance:**

- isolated-root guard prevents any production database or artifact access;
- complete audit chain exists for every accepted, failed, corrected, skipped,
  private, and published fixture record;
- full test suite, JavaScript syntax, rendered desktop/narrow checks, keyboard
  checks, privacy scans, and `git diff --check` pass;
- deployment and production paths remain untouched.

**Manual acceptance:**

- creator can complete the day without terminal or SQLite;
- morning, afternoon, and evening feel like changed states;
- every actor remains distinguishable by behavior, relationship, and voice;
- creator can explain every blocked or failed step from dashboard evidence;
- creator alone decides model changes and whether another season is justified.

## 8. Verification ladder

Evidence must remain separated by level:

1. **Static:** Python compile, JavaScript syntax, HTML landmarks, forbidden-field
   scans, `git diff --check`.
2. **Unit/contract:** read models, versioning, migrations, privacy, command
   conflicts, idempotency, receipts.
3. **WSGI integration:** authentication, CSRF, routes, content types, error
   schemas, no-store behavior.
4. **Synthetic browser:** desktop `1440×1024`, narrow `390px`, breakpoint,
   keyboard, focus, scroll, reconnect, stable polling, no console errors.
5. **Creator local review:** actual reading, navigation, consequence
   understanding, and visual fidelity.
6. **Isolated one-day acceptance:** real local models against a nonproduction
   root only after separate approval.
7. **Deployment:** stage, verify the dashboard process as the `improv` user,
   switch the root route only after creator acceptance, then verify the worker
   separately.

Passing an earlier level does not prove a later one.

## 9. Cross-cutting test organization

Keep tests small and routed by responsibility:

```text
tests/web/test_dashboard_auth.py
tests/web/test_dashboard_contracts.py
tests/web/test_dashboard_home.py
tests/web/test_dashboard_review.py
tests/web/test_dashboard_diagnostics.py
tests/web/test_dashboard_prepare.py
tests/web/test_dashboard_live.py
tests/web/test_dashboard_seasons.py
tests/web/test_dashboard_privacy.py
tests/web/test_dashboard_assets.py
```

Existing `tests/test_dashboard.py` remains until equivalent coverage is present;
it is not deleted simply because new tests exist.

## 10. Rollback and recovery

- Keep legacy routes and the old root UI until the full dashboard is accepted.
- Make schema changes additive and retain prior version records.
- Put every new UI surface behind `/v2` until its creator gate passes.
- Do not deploy a partial mutation workflow merely because its read view works.
- If a slice fails, revert only that slice's route exposure; preserve its
  migration and evidence unless a separately reviewed migration correction is
  required.
- Never roll back by editing SQLite statuses, deleting private artifacts, or
  overwriting command receipts.

## 11. Global stop conditions

Stop implementation and request creator direction if any of these occurs:

- a requested change would weaken a frozen privacy or publication boundary;
- current durable records cannot support a displayed claim honestly;
- migration requires destructive data rewriting;
- live S01 or its configured paths become reachable from a build/test command;
- a command cannot provide expected-version conflict handling and a receipt;
- the new dashboard would require the browser to drive server autonomy;
- automated checks pass but the rendered desktop, narrow, keyboard, or
  sustained-reading behavior has not been reviewed;
- scope expands into the public website, a general model laboratory, automated
  model selection, or a template editor before the one-day workflow is stable.

## 12. Ticket decision record

The creator first authorized and accepted **DASH-00 only**. It created the
fixture, rollback route, module seam, static-asset seam, and migration support
while preserving every existing behavior.

After that gate closed, the creator separately authorized and accepted
`DASH-01` based on its code, local evidence, and desktop/narrow Home review.
The creator then separately authorized and accepted `DASH-02` based on its
local implementation, verification, and rendered sustained-reading review.
The creator subsequently authorized and accepted `DASH-03` after reviewing
successful and failed call explanations, then separately authorized `DASH-04`.
The creator accepted the `DASH-04` manual S02 walkthrough and runbook, then
separately authorized `DASH-05`, followed by `DASH-06`. DASH-05 is implemented
and locally verified; its healthy supervision, retry, skip, desktop, and narrow
creator rehearsal remains open. DASH-06 is also implemented and locally
verified in its disposable S02 fixture; its Private Close and separate
Publication creator walkthrough is open. Neither ticket is creator-accepted,
and this does not authorize DASH-08, deployment, S01 private close, worker or
model operation, or a real publication.
