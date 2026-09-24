# AI Improv Troupe — Implementation Status

**Owner:** creator
**Updated:** 2026-09-17
**Contract:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)

## Branch note — Amaranth prose-craft patch — 2026-09-23

This branch (`Amaranth`) carries a prompt-layer patch aimed at narrative and
prose quality, prepared for cross-review against the `codex` branch:

- New `improv_troupe.llm.prose` module: shared craft guidance blocks (actor,
  director, diary voice, standalone scene) plus a deterministic, advisory
  `lint_prose` checker (stock imagery, out-of-world leaks, monotonous sentence
  openers). The lint is intentionally **not** wired into scene acceptance;
  gating on it needs its own rehearsal-validated experiment.
- Craft guidance injected into the actor, orchestrator, director-render, diary,
  and standalone-scene prompts. Structure, privacy boundaries, MAGIC
  adjudication, and evidence contracts are unchanged.
- Prompt version ids bumped at the changed call sites (`scene-actor-v7`,
  `scene-director-v10`, plan/render and correction ids, all suffixed
  `-prose-craft`) so receipts distinguish the new text.
- `skills/scene-architect` gains a prose-oriented brief-writing step.

No rehearsal or simulation run was executed for this patch, per the creator's
standing hold on runs until she prompts. Validation is static only: the full
local test suite plus new prose tests.

## Current handoff — porch MAGIC diary reliability and repository consolidation — 2026-09-17

The current experimental line is the isolated one-day porch-season rehearsal,
not a continuation of S01 or an authorization to deploy. Runtime-owned MAGIC
adjudication and private diary-fidelity review are implemented. The latest
network-enabled v07 run completed its two-round scene at eight accepted actor
turns, zero cheetah turns, four diary attempts, and a closed day. The forced
setback roll was recorded as `2d6 = 2 + 3` plus the actor's MAGIC modifier,
totaling `6`, and its runtime-owned consequence was carried into the next
beat. The diary envelope still requires one-based references to the exact
accepted scene; three diaries were written with range-valid reference sets,
one diary remained private after two malformed envelopes, and the reviewer
received both the writer claims and numbered scene evidence. The runtime
receipt is `FAIL` because the quality gate correctly withheld the diary set:
Mara and Sage were accepted by fidelity review, Rory was rejected for an
evidence-reference/event-order mismatch plus unsupported private-state
attribution, and Eli remained private. Quality remains
`HUMAN_REVIEW_REQUIRED`, with no diary released to future direction. See the
[latest rehearsal record](rehearsals/season-1-porch-magic-diary-reviewer-evidence-v01-2026-09-17.md).

The fidelity service now permits one private, provenance-linked correction when
the first reviewer response violates its structured contract. The live v04 and
v05 runs each exercised that path three times successfully; v06 exercised the
same path for one diary envelope and two reviewer envelopes, with the second
Rory reviewer attempt remaining unavailable. The correction cannot rewrite
the diary or invent new evidence. A second malformed response remains
`UNAVAILABLE`, so the diary stays withheld. The scheduler's historical resume
test was also made deterministic by injecting its authorization time;
production callers still default to the current UTC time.

The repository was reorganized without deleting research evidence. Dashboard
records now live under [`docs/dashboard/`](docs/dashboard/), completed
Simulation Query reviews under [`research/reviews/`](research/reviews/), and
the unrelated, nonidentical FMK folder/ZIP pair under
[`archive/adjacent-projects/fmk-study/`](archive/adjacent-projects/fmk-study/).
Raw `.rehearsal-data/` roots remain in place. The durable map and cleanup record
are [`docs/README.md`](docs/README.md) and
[`docs/maintenance/2026-09-17-repository-cleanup.md`](docs/maintenance/2026-09-17-repository-cleanup.md).

Current local verification: **361 tests passed**. Local Markdown-link audit,
Python compilation, and `git diff --check` also pass. No live service
configuration, production season state, publication state, or remote checkout
was changed; this rehearsal did call the configured private model server.

## Production implementation update — 2026-08-21

The Proxmox-oriented implementation continued with the following verified work:

- private diary wellness auditing is integrated;
- a full-pilot model outage enters a four-hour wait and then supports creator-approved retry recovery;
- retry ordering prevents later runs from overtaking recovered runs;
- deployment and status documentation now cover Linux VM/LXC service use with the Mac as the private dashboard client.

Verification for this update: **89 tests passed**, compilation passed, and `git diff --check` passed.

The next live gate requires the Proxmox guest's private address and the model-server endpoint. Final model names may remain undecided until benchmarking.

Primary records: [README.md](README.md) and [Proxmox/Linux service unit](deploy/improv-troupe.service).

## Post-green bridge update — 2026-08-21

The explicit creator approval `green` was received in the project thread. The
real Linux service database was not changed from this checkout. A bounded
[post-green bridge](scripts/green_first_run.py) now handles the remaining
private setup on the Linux guest: it generates the private plan and four role
sheets, records role-sheet versions, applies the durable `GreenSeason` command,
runs actor orientation, and leaves scene execution untouched.

The bridge was exercised against disposable local databases with the live
selected Ollama models. Role-sheet persistence, the 21-run schedule, replay
paths, and private orientation/audit wiring were exercised. An initial
high-variance orientation pass exposed inconsistent structured responses; the
orientation parser and prompt were tightened, and all four actor bindings then
passed non-persisted deterministic envelope probes at `temperature=0`.

Latest verification for this bridge: **93 tests passed**, compilation passed,
`git diff --check` passed. The real Linux handoff remains manual: transfer the
updated checkout, reinstall it, run the bridge, and review the private result
before allowing scene execution.

## Dashboard deployment handoff update — 2026-08-22

The private dashboard GUI is implemented in the current checkout and was
verified against disposable local state at desktop and narrow mobile widths.
The full local suite now passes **100 tests**. The real Linux runtime remains a
separate manual deployment boundary.

The current target is `aven@10.0.0.103`, with checkout
`/opt/improv-troupe`, virtual environment `/opt/improv-troupe/.venv`, and
operational data `/var/lib/improv-troupe`. The Linux host does not provide
`rsync`; the canonical transfer procedure is now documented in
[DEPLOYMENT_HANDOFF.md](DEPLOYMENT_HANDOFF.md) using `tar` over SSH while
excluding `.venv` and `.git`.

The creator reported that the Linux dashboard first served the old JSON page,
which indicates an older checkout or package was still running. After transfer,
reinstall the editable package and verify the new source contains
`Keep the troupe in view.` before restarting the dashboard. No remote checkout,
service, or real season database was changed by this local documentation
update.

The subsequent launch attempts exposed checkout-permission issues rather than
authentication issues: `/opt/improv-troupe` was mode `700`, and source files
such as `src/improv_troupe/cli.py` were `root:root` mode `700`. The `improv`
service user could therefore not traverse or import the checkout even though
the virtualenv launcher itself was executable. The deployment handoff now
applies mode `750` to the checkout root and gives the `improv` group read and
traverse access to `src/` without making the project world-accessible. The
import check now runs as `improv`, matching the dashboard runtime user.

## Live dashboard review checkpoint — 2026-08-22

The creator confirmed that the updated private dashboard is reachable and the
owner can sign in. The current dashboard reports that Run 3 was interrupted;
the persisted cause and exact recovery status have not yet been captured in
this record. All four visible diary entries remain private.

This is a safe, incomplete operational state: private diary status is expected
until the season is closed and the creator explicitly reviews publication. The
next decision is to inspect Run 3's Attention/notification details and, only
if the persisted status is `RECOVERY_REQUIRED`, choose `retry`, `skip`, or
`end` deliberately. No recovery or publication action has been authorized or
recorded by this checkpoint.

## Live diary review checkpoint — 2026-08-22

After the creator retried it, `S01-run-03` completed. At that captured
checkpoint, the Day 1 diary event history explained why the earlier dashboard
could not offer a `Read private entry` disclosure:

- `luna-planck` — `DiaryFormatInvalid`; no selected slot, word count, or
  content path was persisted.
- `mason-curie` — `DiaryFormatInvalid`; no selected slot, word count, or
  content path was persisted.
- `higgs-sierra` — `WellnessSignalObserved` after selecting slot 1; the diary
  remains private with no content path.
- `ivy-fermion` — `WellnessSignalObserved` after selecting slot 1; the diary
  remains private with no content path.

The raw Higgs and Ivy wellness text remains in the private audit tree. Before
the Day 1 review patch it was not included in the dashboard diary payload; the
new owner-only review route can make a selected diary attempt readable without
clearing its private status. None of the four checkpoint records is publishable
diary text, and no publication review or diary-clearing decision has been
recorded. All four underlying diary model calls completed with `error_type =
None` and left private `output.md` artifacts, so this is a structured-
output/wellness handling issue rather than a transport or model-availability
failure.

## Creator policy decision — S01 wellness handling — 2026-08-22

For S01, the creator chose to continue accepting and recording explicit
wellness signals, but not to offer automatic tap-out. Signals remain private,
audited, and visible as operator notifications; the creator will manually
monitor the cast and decide whether an actor needs to be pulled. This is a
season-specific override and does not change the default policy for future
seasons. The existing Higgs, Ivy, and other recorded signals remain intact.

The live runtime still needs the persisted S01 policy override before any
future signal can be handled under this decision. A manual review checkpoint
should occur before continuing after a new signal.

## Wellness policy and Ivy repair implementation — 2026-08-22

The checkout now carries this decision through the live runtime:

- `Season.auto_tap_out` defaults to `true`, preserving the existing behavior for
  future seasons.
- The replay-safe `SET_WELLNESS_POLICY` command can set S01 to manual review;
  status and the private dashboard expose `MANUAL_REVIEW` so the active policy
  is visible before the next run.
- Manual review continues to record raw signals privately, increment the
  season-local observation count, notify the operator, and keep the actor
  `ACTIVE`. The affected scene still pauses for creator review.
- `repair-diary` makes one explicit new model attempt for a PRIVATE diary with
  no accepted content, using a completed run's durable transcript as context.
  Earlier model calls, raw outputs, and invalid-format/wellness events remain
  append-only private evidence.

Local verification for this implementation: **104 tests passed**, Python
compilation passed with a temporary bytecode cache, and `git diff --check`
passed. The live Linux package, S01 policy, and Ivy repair still require the
manual deployment commands in [DEPLOYMENT_HANDOFF.md](DEPLOYMENT_HANDOFF.md).

## Day 1 end-of-day review patch — 2026-08-22

The creator reports that the dashboard can now show an entry that has no
wellness marker and that the diary quality to date is promising. This feedback
is qualitative creator evidence, not a publication decision or a change to the
private status of any other diary.

The current checkout addresses two Day 1 review problems before the next
content review:

- The dashboard previously refreshed all diary markup on a short timer, which
  collapsed an entry while it was being read. It now polls only operational
  status every 60 seconds; it does not reload the Diary desk or End-of-day
  review automatically. Explicit **Refresh** and **Reload review** controls are
  the only content-reload paths, and expanded details retain their state across
  a manual reload.
- The new authenticated **End-of-day review** assembles one original day’s
  creator-visible opening snapshot, accepted shared script, scheduled/run
  states, and every diary record. For a diary held due to wellness or invalid
  format, it can display parsed private review text and an explicitly expanded
  raw model output. That access is owner-only and read-only: the diary remains
  `PRIVATE`, noncanon, and nonpublishable until the separate publication gate.

The local patch has not been transferred to the Linux guest in this checkpoint.
It must not be represented as live-browser evidence until the deployment
handoff is performed and the creator checks it on the Mac.

Verification for this patch: **105 tests passed**; Python compilation,
JavaScript syntax checking, and `git diff --check` passed. A local browser
visual pass was attempted against a disposable fixture, but the available
in-app browser blocks localhost navigation; this is not browser-interaction
evidence and remains a manual Mac check after deployment.

## Day 1 narrative-direction patch — 2026-08-22

The creator's Day 1 content review found that the private shared script was
functionally usable but too dry, technical, repetitive, and committee-like to
give the cast strong material. The creator explicitly chose to keep the current
turn length while shifting the orchestrator and actors toward TTRPG-style play.
The script remains private; its quality criterion is whether it creates
specific, consequential, diary-worthy experiences rather than whether it reads
like polished public prose.

The current checkout now implements that decision:

- Every live run loads its immutable mission day, one of three daily slots, and
  original local schedule time. Slots are framed as morning, afternoon, and
  evening, with roughly six fictional hours and ordinary off-screen life
  available between them.
- An overnight sleep interval separates each evening from the following
  morning. `S01-run-04` therefore opens as Day 2 morning with the cast waking or
  rising into a new day; actors remain free to characterize how well they slept.
- Later runs receive prior accepted canon and the immediately preceding run's
  final shared orchestrator outcome. Each actor also receives only its own
  durable prior `MEMORY_NOTE` values. Peer memory remains excluded.
- A `NextDayDirectionCreated` artifact for the target day is loaded only into
  the orchestrator context. It is not rendered into the script or actor prompt.
- The game-master prompt now adjudicates what choices changed, introduces one
  concrete sensory/state-changing beat per round, varies crisis with routine,
  humor, wonder, relationships, and quiet aftermath, and privately tracks
  mission-progress, danger, mystery, and relationship clocks. It may never
  dictate actor choices, dialogue, or private thoughts.
- Actor instructions now ask for one concrete player-character move instead of
  a full technical recap or forced consensus. Existing four-round and
  16-actor-turn limits are unchanged.
- Diary instructions now prioritize personal interpretation, relationships,
  sensory detail, uncertainty, and consequential choices. Fictional insomnia,
  caffeine, pulse, fear, and danger are explicitly not wellness signals unless
  accompanied by an out-of-world request to soften, pause, or stop.
- Closed-day direction planning now receives the day's durable accepted shared
  turns and accepted canon in run order, alongside diaries available only after
  closure. Future day plans explicitly span morning, afternoon, and evening
  rather than one continuous technical emergency.

Day 1 scripts, diary artifacts, wellness observations, and direction events
were not rewritten or deleted. The patch changes future model context only.
It has not been installed on the Linux guest in this checkpoint; Run 4 must not
be started under the assumption that this behavior is live until the checkout
and editable package are refreshed.

Local verification for this patch: **106 tests passed**, including a focused
Run 4 regression proving the Day 2 wake-up boundary, prior shared
outcome/canon continuity, actor-memory partitioning, and hidden-direction
privacy.

## Two-pass director game loop — 2026-08-29

Prompt wording alone did not make the local director reliably turn actor moves
into playable decisions. The isolated rehearsal path now uses a small,
explicit TTRPG loop before it writes shared prose:

- Each run carries one persistent **scene objective**: a concrete question the
  cast can advance, make costlier, reframe, or resolve.
- Before every stage beat, the director must produce a private structured plan:
  adjudication of a prior move or established condition; an observable state
  change; immediate pressure; exactly two distinct actor-facing choices; one
  next actor; one or two progress/danger/mystery/relationship clock changes;
  and a factual canon update.
- A separate render pass supplies only fresh sensory lead-in. The system then
  compiles the approved change, pressure, and both choices verbatim into the
  shared beat. Actors can choose either, refuse both, or invent a third
  response; the director never supplies their thoughts, dialogue, or action.
- The accepted private plan is stored with the round's private events so a
  resumed rehearsal restores the objective and clocks. The shared transcript
  contains the rendered beat, not the private mechanics.

The normal live path is unchanged. This is enabled only when the factory is in
strict rehearsal acceptance mode, and it has not been deployed or used to
alter a live season. Local verification: **185 tests passed**, including a
four-round two-pass regression and the complete three-slot deterministic
one-day rehearsal.

## S01 Day 2 review and overhaul commitment — 2026-08-24

The creator reports that Day 2 eventually completed after the earlier recovery
work and supplied the private End-of-day export plus all four diary outputs for
review. This documentation pass did not query or mutate the authoritative Linux
database, so the creator-supplied export is qualitative evidence rather than a
fresh operational-state verification.

The creator has decided to end S01 rather than continue the seven-day pilot and
to preserve it privately as overhaul evidence. No season-control or publication
command was executed by this update. S01 remains nonpublishable until the
separate end-of-season privacy, wellness, consent, and publication gates are
explicitly completed.

The committed overhaul sequence is:

1. rebuild the dashboard as a trustworthy operator surface;
2. manually exercise and document every pre-season operator step;
3. run an isolated one-day test containing three scenes, four diary
   opportunities, day closure, and next-day planning;
4. create reusable operator/model templates only after that manual workflow is
   understood.

Trying one or two model swaps, including 12B-class candidates, is still an open
possibility rather than an assignment decision. The private evidence and
per-model assessment are recorded in
[benchmarks/s01-day-2-model-review-2026-08-24.md](benchmarks/s01-day-2-model-review-2026-08-24.md).

The Day 2 review established these implementation defects:

- the End-of-day projector orders each round by lexical `turn_id`, placing actor
  responses before the orchestrator beat that prompted them;
- the API returns `turn_count` and `completion_reason`, but the browser hides
  both, so a nine-turn Run 6 appears equivalent to a 16-turn run;
- the assembled review omits the non-secret mission-clock framing supplied to
  the models;
- the creator-reviewed cast briefs and voice seeds were not preserved in the
  approved opening or passed into post-green role-sheet generation;
- the concrete `LLMClient` does not implement the advertised native structured
  output capability, leaving all live models on fragile tagged-text envelopes;
- current deterministic review checks enforce hard safety boundaries but not
  first-person identity, pronoun consistency, role fidelity, unsupported canon,
  or repeated turns;
- the mandatory one-turn-per-actor-per-round structure remains a possible cause
  of committee-style repetition and must be treated as an open design decision
  for the one-day test.

The creative premise remains promising. The diaries showed more distinct voice,
relationship awareness, and interiority than the shared scenes. That evidence
supports fixing orchestration, context, character input, review truth, and
format enforcement before making broad cast changes.

Functional planning for the dashboard overhaul is now captured in
[DASHBOARD_OVERHAUL_PLAN.md](docs/dashboard/DASHBOARD_OVERHAUL_PLAN.md). Its functional model
was approved through focused creator decisions on 2026-08-24. The private
Penpot file and its first low-fidelity checkpoint now exist, but layout, visual
design, and implementation remain unapproved and incomplete.

The creator approved the first functional decision on 2026-08-24: the dashboard
uses a guided studio workflow, with denser control-room information confined to
Live and Diagnostics. Layout and all visual design remain open.

The creator then approved six stable primary destinations: Home, Prepare, Live,
Review, Diagnostics, and Seasons. They remain visible across lifecycle states;
gated destinations and actions explain their prerequisites rather than
disappearing. Placement, responsive behavior, and visual design remain for the
later Penpot phase.

The creator also approved the Live story-reading boundary: its overview shows
one compact Last accepted beat, while the full transcript opens deliberately.
Operational polling never replaces or scrolls an open transcript; newly
accepted material raises a creator-controlled refresh indicator. Ordinary Live
views remain limited to accepted private story text.

Prepare will use a guided checklist with one focused step workspace rather than
a rigid wizard. All steps and statuses remain visible, unlocked work can be
revisited, and changing an earlier artifact visibly invalidates dependent later
evidence. Navigation alone never approves a step or advances season state.

Cast and Continuity will not add another primary destination. Prepare owns
editable pre-green character cards; Review owns the durable cards, cast status,
canon, unresolved continuity, and memory-version metadata; Diagnostics owns
private role-sheet and prompt provenance; Live shows compact cast status and
links only. Post-green identity changes require an explicit versioned workflow.

The first Diagnostics slice is limited to explaining individual model calls:
filters and call identity, binding, timing/error state, schema path, artifact
versions, raw-to-rendered stages, correction/validator evidence, and a Review
link. It remains read-only and excludes reruns, benchmark graphs, bulk model
comparison, automated selection, and raw wellness text.

The creator approved operationally complete narrow layouts. Desktop remains the
full workspace, while narrow screens adapt checklists, transcript reading,
diagnostic comparisons, and dense records without removing lifecycle actions or
hiding privacy, safety, completion, consequence, or confirmation evidence.

Penpot will use a synthetic rehearsal season by default. It may reproduce the
shape of S01 failures but cannot copy private diaries, prompts, role sheets,
hidden direction, or wellness text. Adding any selected S01 excerpt requires a
separate explicit creator decision.

The functional plan has been translated into the durable Penpot screen map,
synthetic fixture, component inventory, prototype flows, and first-checkpoint
criteria in [PENPOT_DASHBOARD_BRIEF.md](docs/dashboard/PENPOT_DASHBOARD_BRIEF.md). On
2026-08-24, the private file `AI Improv Troupe — Operator Dashboard` was created
with the planned nine-page structure. The Decisions and Flow Map boards plus
desktop and narrow Home and Day Review wireframes were imported from the
synthetic SVG sources in [`design/penpot/`](design/penpot/), arranged for
comparison, and visually checked for contrast. The creator then approved this
first checkpoint in full, including the hierarchy, responsive treatment, and
navigation hypothesis A: stable left rail on desktop and persistent bottom
navigation on narrow screens. The visual system, high-fidelity treatment,
remaining screens, and implementation remain unapproved.

The next low-fidelity Prepare checkpoint was assembled in Penpot on 2026-08-24.
It contains desktop character-card approval, desktop Opening-revision impact,
and narrow character-card frames. The frames preserve all eight checklist
steps, distinguish navigation from mutation, explain approval effects and
blocked prerequisites, and preview downstream invalidation before an earlier
artifact is saved. The creator approved this Prepare checkpoint in full on
2026-08-24. The visual system, remaining screens, and implementation remain
unapproved.

The low-fidelity Diagnostics checkpoint was then assembled and imported on
2026-08-24. Its desktop and narrow frames explain one synthetic model call from
identity and binding through raw, parsed, validated, accepted, and rendered
evidence. They preserve the originating Review position, expose schema failure,
validator, correction, timing, and version provenance, and keep raw output
behind deliberate disclosure on narrow screens. The frames are read-only,
exclude raw wellness text, and contain no rerun or model-selection controls.
The creator approved this Diagnostics interaction checkpoint in full on
2026-08-24. The visual system, remaining screens, and implementation remain
unapproved.

The low-fidelity Live and Recovery checkpoint was then assembled and imported
on 2026-08-24. Four synthetic frames cover healthy autonomous supervision and
Recovery Required at desktop and narrow widths. They keep one Last accepted
beat visible, preserve a deliberately opened transcript during polling, expose
new accepted material through creator-triggered refresh, distinguish durable
worker/queue truth from story reading, and explain retry, skip, and private end
without preselecting or submitting a choice. Private end remains a separate
snapshot-and-confirmation journey and cannot publish or delete evidence. This
interaction checkpoint was approved in full by the creator on 2026-08-24. The
visual system, remaining screens, and implementation remain unapproved.

The low-fidelity Seasons and Publication checkpoint was then assembled and
imported on 2026-08-24. Four synthetic frames cover private close and the
separate publication review at desktop and narrow widths. Private close starts
from a versioned operational snapshot, preserves unresolved work, distinguishes
its effects from publication/deletion, and requires a season-qualified private
intent before receipt and terminal-state verification. Publication starts only
from an explicitly selected private-complete season, repeats privacy and consent
gates, previews the exact allowlisted output and structural exclusions, and
uses a different season-qualified intent before an immutable version, manifest
hash, and receipt. The creator approved this Seasons and Publication
interaction checkpoint in full on 2026-08-24. The visual system, final
low-fidelity system checkpoint, and implementation remain unapproved.

The final low-fidelity system checkpoint was then assembled, visually checked,
and imported into Penpot on 2026-08-24. Its three synthetic boards define the
shared content/component grammar, seven lifecycle prototype paths, and nine
exceptional-state contracts. Every path preserves context and evidence and
stops before an unapproved live mutation; every exceptional state names known
truth, readable evidence, a valid action, and blocked actions. Polling may
update operational chrome but cannot replace open reading panes or creator
input. The creator approved this final checkpoint in full on 2026-08-24. The
functional model and low-fidelity interaction architecture are now frozen as
the baseline for visual-language exploration. The visual system, high-fidelity
screens, and implementation remain unapproved.

The first visual-language direction round was assembled, rendered, and imported
into Penpot on 2026-08-24. A neutral comparison and three detailed synthetic
Home/Day Review boards explore Warm Instrument, Molten Observatory, and Quiet
Archive without changing the frozen interaction model. Warm Instrument is the
recommended starting point for long reading and creative warmth; no direction,
font, high-fidelity screen, or implementation is approved yet.

The creator selected **A · Warm Instrument** on 2026-08-24. Its warm paper
reading surface and dark operational rail are now the active visual direction
for token, component, responsive, and high-fidelity refinement. Exact tokens,
final fonts, component styling, high-fidelity screens, and implementation
remain unapproved.

The Warm Instrument visual-system refinement checkpoint was then assembled,
rendered, and imported into Penpot on 2026-08-24. Three synthetic boards define
proposed foundation tokens, reusable component/state treatment, and matching
desktop/narrow application. Color contrast ratios were calculated for proposed
pairs, but remain design evidence rather than rendered implementation or human
accessibility evidence. At assembly, the visual-system checkpoint awaited
creator review; high-fidelity screens and implementation remained unapproved.

The creator approved the Warm Instrument visual-system checkpoint in full on
2026-08-24. Its foundation tokens, component language, and responsive rules are
now frozen as the high-fidelity baseline. Calculated contrast remains design
evidence only; final font loading, rendered behavior, and human accessibility
evidence remain implementation/acceptance gates. The first representative
high-fidelity checkpoint was the next design step at that point; implementation
remained unapproved.

The first representative high-fidelity checkpoint was then assembled, rendered,
visually inspected, and imported into Penpot on 2026-08-24. Desktop and narrow
Home screens test calm supervision and retained operator context; desktop and
narrow Day Review screens test stable authored-text reading, saved position,
private diary boundaries, and deliberate loading of newer accepted material.
All four screens use synthetic S02 content, expose no command submission, and
show no raw wellness text. At assembly, the checkpoint awaited creator review;
remaining high-fidelity workflows and implementation remained unapproved.

The creator approved the Home and Day Review high-fidelity checkpoint in full
on 2026-08-24. Its desktop and narrow calm-supervision hierarchy, responsive
navigation, stable reading behavior, saved-position evidence,
creator-controlled refresh, and private diary boundary are now frozen as the
representative high-fidelity reference. This does not authorize implementation
or replace later rendered, interactive, and accessibility acceptance.

The Prepare high-fidelity checkpoint was then assembled, rendered, visually
inspected, and imported into Penpot on 2026-08-24. Four synthetic screens cover
Character Cards and Opening-revision impact at desktop and narrow widths. They
retain the entire eight-step checklist, explicit prerequisites and approval
effects, durable versions, current approved truth, every downstream
invalidation, and separate navigation/save/review boundaries. No screen connects
to production state or executes a command. At assembly, the checkpoint awaited
creator review; remaining high-fidelity workflows and implementation remained
unapproved.

The creator approved the Prepare high-fidelity checkpoint in full on
2026-08-25. Its desktop and narrow full-checklist visibility, focused-step
workspace, prerequisites, durable versions, approval impact,
current-approved-truth treatment, downstream-invalidation explanation, and
separate navigation/save/review boundaries are now frozen. This does not
authorize implementation.

The Live and Recovery high-fidelity checkpoint was then assembled, rendered,
visually inspected, and imported into Penpot on 2026-08-25. Four synthetic
screens cover healthy autonomous supervision and Recovery Required at desktop
and narrow widths. They retain worker/queue and timing truth, one Last accepted
beat, stable creator-refreshed reading, failure-stage evidence, the exact safe
stop, and equal unselected retry/skip/private-end paths with distinct
consequences. No screen connects to production state, preselects or submits a
path, publishes, deletes, or exposes raw wellness text. At assembly, the
checkpoint awaited creator review; remaining high-fidelity workflows and
implementation remained unapproved.

The creator approved the Live and Recovery high-fidelity checkpoint in full on
2026-08-25. Its desktop and narrow calm-supervision hierarchy, worker/queue
truth, stable reading, creator-controlled loading, exact last-accepted causal
anchor, failure-stage explanation, equal unselected recovery paths, and
consequence-first decision boundary are now frozen. This does not authorize
implementation or any recovery command.

The call-focused Diagnostics high-fidelity checkpoint was then assembled,
rendered, visually inspected, and imported into Penpot on 2026-08-25. Its
desktop and narrow synthetic screens explain one selected call through identity,
timing and finish evidence, raw-to-rendered stages, validator findings, linked
correction attempts, version provenance, and an exact causal return to Review.
The screen is read-only; it connects to no production state, executes no
command, and excludes reruns, benchmarks, bulk comparison, automated model
selection, private role-sheet contents, and raw wellness text. The checkpoint
awaited creator review at assembly; remaining high-fidelity workflows and
implementation remained unapproved.

The creator approved the Diagnostics high-fidelity checkpoint in full on
2026-08-25. Its desktop and narrow selected-call identity, timing and finish
evidence, raw-to-rendered causal sequence, deliberate disclosure boundary,
validator and correction history, version provenance, exact return-to-Review
point, and read-only operating boundary are now frozen. This does not authorize
implementation, model operation, or disclosure of excluded private evidence.

The final Seasons and Publication high-fidelity checkpoint was then assembled,
rendered, visually inspected, and imported into Penpot on 2026-08-25. Four
synthetic screens cover Private Close and the later separate Publication review
at desktop and narrow widths. Private Close begins from a versioned read-only
snapshot, preserves unresolved-work truth, distinguishes effects and
non-effects, and requires exact season-qualified private intent. Publication
begins only from a selected `PRIVATE_COMPLETE` season, repeats every privacy and
consent gate, previews the exact allowlisted projection and structural
exclusions, and requires its own publish intent before an immutable result. The
screens connect to no production state, prefill no intent, execute no command,
and expose no excluded source data. At assembly, the checkpoint awaited creator
review; dashboard implementation remained unapproved.

The creator approved the Seasons and Publication high-fidelity checkpoint in
full on 2026-08-25. Its desktop and narrow versioned closure snapshot,
unresolved-work preservation, effect and non-effect boundary, exact private
intent, terminal-private verification, separate release eligibility, repeated
privacy and consent gates, exact allowlisted public projection, structural
exclusions, distinct publish intent, and immutable-result evidence are now
frozen. This completes and freezes the full dashboard high-fidelity design. It
does not authorize dashboard implementation, private close, publication, or any
production-state change.

The creator then authorized an implementation-ready build sequence on
2026-08-25, not dashboard coding or deployment. Current-code inspection found a
dependency-free WSGI dashboard with sound authentication/CSRF foundations but
an approximately 1,100-line combined route/read-model/HTML/CSS/JavaScript file,
normal authenticated diary payloads that can carry raw private attempts, direct
recovery/publication mutations without the approved staged impact contracts,
and a one-migration loader that must be extended before additive preparation or
closure records. The complete bounded sequence is
[DASHBOARD_IMPLEMENTATION_SEQUENCE.md](docs/dashboard/DASHBOARD_IMPLEMENTATION_SEQUENCE.md).
It preserves the current dashboard as rollback, introduces new work under
`/v2`, begins with read-only contracts and Home/Review, and keeps live S01
closure on a separate explicitly approved operational track. Local baseline:
**112 tests passed in 6.48 seconds** and `git diff --check` passed. At that
planning checkpoint, the first coding decision was `DASH-00` only and remained
unapproved.

## DASH-00 implementation checkpoint — 2026-08-25

The creator authorized `DASH-00` only. That bounded implementation slice is
complete in the local checkout and was creator-accepted on 2026-08-26. No
`DASH-01` work was authorized by that acceptance; `DASH-01` was authorized
separately afterward and is recorded below.

Implemented boundaries:

- the legacy `/` dashboard retains its authenticated reads, recovery and
  publication routes, CSRF behavior, cookies, and 60-second status polling;
- its embedded CSS and JavaScript are now allowlisted packaged assets, and both
  the login and authenticated pages use a self-only Content Security Policy
  plus no-sniff, no-referrer, frame-denial, and permissions headers;
- an authenticated, empty Warm Instrument shell exists at `/v2/home`, has no
  read model or mutation controls, and is disabled unless the local dashboard
  is launched explicitly with `--enable-v2`;
- shared strict versioned envelope models exist for later `/api/v2` reads, but
  no v2 data route has been added;
- the migration loader can resolve future numbered SQL files without applying
  a second migration or changing schema version 1;
- a deterministic S02 fixture covers completed, partial, queued, recovery,
  private diary, late/missing diary, failed-call, manual-review, closed-day, and
  private-publication evidence; its guard rejects the production data root and
  any parent capable of containing it.

Verification evidence:

- protected pre-ticket baseline: **112 tests passed in 6.48 seconds**;
- completed ticket: **119 tests passed in 6.83 seconds** on the final recorded run;
- Python compilation, both direct JavaScript syntax checks, dashboard CLI help,
  and `git diff --check` passed;
- synthetic browser inspection passed for legacy and v2 at `1440×1024` and
  `390×844`, with no horizontal overflow and no console warnings/errors;
- v2 showed the desktop rail and narrow bottom navigation at the intended
  breakpoint, with zero forms and zero buttons;
- no Linux connection, deployment, worker restart, model call, S01 close,
  recovery decision, private publication, or public release occurred.

The current virtual environment does not include a compatible `setuptools`, so
an extra installed-wheel inspection was not accepted as evidence and no
dependency installation was attempted. Package-data declarations are present,
and all static assets were loaded through the same `importlib.resources` path
during WSGI and browser verification. Installed-wheel contents remain a later
deployment packaging check, not a reason to weaken or expand this ticket.

### Creator decision — DASH-00 accepted — 2026-08-26

The creator confirmed that `DASH-00` is good. This closes the ticket's creator
gate based on its preserved legacy surface, default-disabled v2 seam,
production-isolated fixture, and recorded automated/browser evidence. It is a
dashboard-overhaul acceptance decision, not authorization for `DASH-01`, live
Linux access, deployment, S01 private close, worker operation, model use,
recovery, or publication.

## DASH-01 implementation checkpoint — 2026-08-26

The creator separately authorized `DASH-01`, the read-only shared shell and
trustworthy Home slice. That bounded implementation is code-complete and locally
verified. The creator accepted its required desktop and narrow Home comparison
on 2026-08-26. This closes `DASH-01`; it does not authorize `DASH-02`.

Implemented boundaries:

- `/api/v2/context` and `/api/v2/home` use strict allowlisted envelopes and
  preserve the selected season in every Home, Review, and shared-shell link;
- the Warm Instrument shell uses the approved `920px` breakpoint, with a fixed
  240px desktop rail and narrow selected-context header/bottom navigation;
- Home reports stored lifecycle, SQLite/root integrity, snapshot freshness,
  queue and lease evidence, attention, durable progress, latest readable
  accepted beat, next schedule, cast, day completion, and recent seasons;
- worker wording is deliberately limited to `Active lease observed`,
  `Expired lease observed`, or `No active lease observed`; no heartbeat exists
  in schema version 1, so Home does not claim worker health;
- at the DASH-01 checkpoint, the latest accepted beat exposed no artifact path
  and labeled its order as derived because schema version 1 had no causal
  accepted-turn fields; DASH-02's later additive migration is recorded below;
- explicit loading, no-season, partial, stale-readable, and disconnected states
  retain the last readable snapshot instead of clearing it after a failed poll;
- Prepare, Live, Diagnostics, and Seasons remained read-only shared-context
  placeholders at this checkpoint; Review was implemented separately in
  DASH-02, and no v2 mutation route or form was added;
- legacy `/` behavior remains intact, and all v2 pages and APIs remain
  authenticated, default-disabled, and available only with `--enable-v2`.

Verification evidence:

- **126 tests passed in 6.60 seconds** on the final recorded full-suite run;
- focused v2 tests cover authentication, strict environment labeling,
  no-season state, partial evidence, worker lease truth, day-completion proof,
  selected-season navigation, private-root escape refusal, and forbidden model,
  prompt, wellness, notification-payload, and path leakage;
- Python compilation, direct v2 JavaScript syntax checking, and
  `git diff --check` passed;
- authenticated synthetic browser inspection at `1440×1024` measured a visible
  rail, hidden mobile controls, four metric columns, correct card hierarchy,
  and `1440px` document width with no horizontal overflow;
- authenticated inspection at `390×844` measured a hidden rail, visible
  selected-context header, two primary metric cards, fixed bottom navigation,
  and exactly `390px` document/body width with no horizontal overflow;
- Review navigation and browser Back both retained `season_id=S02`; the browser
  console contained no warnings or errors;
- the browser used a disposable production-guarded S02 fixture. No Linux
  connection, deployment, worker restart, model call, S01 close, recovery
  decision, private publication, or public release occurred.

### Creator decision — DASH-01 accepted — 2026-08-26

The creator accepted the read-only shared shell and trustworthy Home render.
This is a dashboard-overhaul acceptance decision for `DASH-01` only. It is not
authorization for causal Day Review work in `DASH-02`, live Linux inspection,
deployment, S01 private close, worker operation, model use, recovery, private
publication, or public release.

## DASH-02 implementation checkpoint — 2026-08-26

The creator separately authorized `DASH-02`, the causal Day Review and stable
reading slice. That bounded implementation is code-complete, locally verified,
and creator-accepted as of 2026-08-26.

Implemented boundaries:

- additive schema migration 2 adds nullable `accepted_sequence`,
  `caused_by_turn_id`, and `accepted_at` fields; migrated legacy rows remain
  null and are explicitly labeled as derived rather than silently rewritten;
- new accepted director, actor, corrected, and neutral-interruption records get
  durable sequence/time evidence, while actor/interruption records link back to
  the director beat that prompted their round;
- `/api/v2/review/day` exposes allowlisted day/run status, accepted counts,
  rounds, completion reason, scheduled/actual times, delay, close evidence,
  non-secret fiction-clock frame, causal accepted story, diary summaries, cast
  status, memory versions, canon, and honest continuity unavailability;
- default Review JSON never includes diary text, raw private attempts, model
  identity, artifact paths, or wellness wording;
- `/api/v2/review/diary-attempt` is a separate authenticated GET projection. It
  returns accepted diary text or safely parsed diary text from a held attempt,
  plus only a wellness-presence boolean. Malformed or escaped artifacts fail
  closed instead of returning the raw response envelope;
- the Warm Instrument Review page implements run selection, visible completion
  evidence, stable transcript, Diary desk, Cast & continuity, Day summary,
  explicit newer-material loading, and local day/run/tab/disclosure/scroll
  restoration. Sixty-second operational probes stage new material without
  replacing the open reader subtree;
- the legacy `/` dashboard is unchanged, v2 remains authenticated and disabled
  by default, and no v2 mutation command was added.

Verification evidence:

- **133 tests passed in 8.05 seconds** on the final recorded full-suite run;
- normal, corrected, recovered, partial, and legacy-derived fixtures verify
  director-before-actor order, cause links, completion evidence, and honest
  fallback labeling;
- disclosure tests prove the GET cannot alter diary status/content, canon,
  wellness records, or publication eligibility; strict contract and path
  containment tests prevent raw output and wellness-text expansion;
- migration from a version-1 fixture is additive and preserves legacy turn
  rows without backfilling inferred evidence;
- Python compilation and direct v2 JavaScript syntax checking pass;
- authenticated disposable browser rehearsal at `1440×1024` and `390×844`
  confirmed the approved hierarchy, exact-width narrow layout with no
  horizontal overflow, native keyboard tabs, deliberate held-diary reading,
  withheld wellness wording, long/unbroken-text wrapping, run switching, and
  Back restoration of saved day/run/scroll and disclosure state;
- no live Linux connection, deployment, worker restart, model call, S01 close,
  recovery decision, private publication, or public release occurred.

### Creator decision — DASH-02 accepted — 2026-08-26

The creator accepted the actual Day Review sustained-reading behavior. This
closes `DASH-02` only and is not authorization for `DASH-03`, live Linux
inspection, deployment, S01 private close, worker/model operation, recovery,
private publication, or public release.

## DASH-03 implementation checkpoint — 2026-08-27

The creator separately authorized `DASH-03`, the call-focused read-only
Diagnostics slice. That bounded implementation is code-complete, locally
verified, and creator-accepted. Local tests and browser rehearsal remained
separate from the creator's explanation-quality decision.

Implemented boundaries:

- schema version 3 additively stores nullable response-format, prompt, schema,
  context, role-sheet, character-card, downstream-stage, validator,
  correction, and exact Review-link evidence on model-call attempts;
- new structured calls persist the actual negotiated `NATIVE_SCHEMA` or
  `TAGGED_FALLBACK` mode plus available prompt, schema, context, and role-sheet
  identifiers; absent character-card or legacy provenance remains visibly
  unavailable rather than inferred;
- authenticated `/api/v2/diagnostics/calls` filters by season, run, character,
  purpose, status, attempt, and error, while
  `/api/v2/diagnostics/calls/{call_id}` explains one selected call;
- raw, parsed, validated, accepted, and rendered remain five separate stored
  stages; accepted and rendered content appears only when its allowlisted
  private artifact is readable;
- raw output is available only through the deliberate
  `/api/v2/diagnostics/call-raw` read route, with private-root containment and
  wellness-signal refusal; diary and other non-run private attempts are absent
  from the ordinary call list;
- the deterministic S02 fixture distinguishes a slow schema failure,
  transport failure, parse failure, and accepted/rendered call without making
  any model request;
- the selected accepted call returns to its stored causal Review turn, and
  browser Back restores the selected Diagnostics call;
- desktop keeps call list and evidence together; narrow screens put the
  selected call first, retain all five stages, and avoid horizontal overflow;
- no rerun, benchmark, bulk comparison, model download, automated-selection,
  recovery, acceptance, canon, wellness, or publication control was added.

Local evidence:

- the full suite passes: `137 passed in 7.97s`;
- Python compilation, dashboard JavaScript syntax, and `git diff --check`
  pass;
- authenticated browser rehearsal passed at 1440x1024 and 390x844, including
  successful and failed call explanations, filters, deliberate raw reveal,
  exact Review targeting, browser Back, five-stage narrow reading, and zero
  horizontal overflow;
- the browser console reported no warnings or errors;
- no live Linux connection, deployment, worker restart, model call, S01 close,
  recovery decision, private publication, or public release occurred.

### Creator decision — DASH-03 accepted — 2026-08-27

The creator accepted the successful and failed synthetic call explanations and
then separately authorized `DASH-04`. DASH-03 acceptance did not authorize live
Linux inspection, deployment, S01 private close, worker/model operation,
recovery, private publication, or public release.

## DASH-04 implementation checkpoint — 2026-08-27

The creator separately authorized `DASH-04`, the versioned manual Prepare
workspace. The bounded implementation is code-complete and locally verified.
The creator completed the fresh eight-step S02 walkthrough and accepted the
runbook on 2026-08-27, closing DASH-04 only.

Implemented boundaries:

- schema version 4 additively stores preparation workspaces, immutable
  character-card versions, model-assignment versions, step receipts,
  invalidation events, and idempotent action responses;
- authenticated `/api/v2/prepare` exposes the eight-step checklist, focused
  workspace, current approved card truth beside drafts, version history,
  dependency state, and invalidation history;
- private role-sheet and orientation fixtures retain their source
  character-card version, stay closed by default, and open only through the
  deliberate sandbox-only artifact disclosure route;
- authenticated `/api/v2/prepare/action` is sandbox-only, rejects S01, requires
  CSRF plus an expected workspace version, and records one versioned receipt;
- model assignments appear only inside their focused step and are stored
  evidence, never automatic selection, download, or model operation;
- preflight is explicitly stored-only, private preparation returns no role-sheet
  or orientation text, and schedule preview writes no production schedule;
- Green records `season_armed=false` and `command_submitted=false`; it cannot
  start a worker or transition the season;
- opening and character-card revisions preserve prior versions and explicitly
  invalidate dependent receipts before the workflow can proceed again;
- the legacy dashboard and all live S01 data paths remain untouched.

Local evidence:

- the full suite passes: `143 passed in 9.17s`;
- Python compilation, dashboard JavaScript syntax, and `git diff --check` pass;
- authenticated browser rehearsal completed all eight actions at 1440x1024 and
  390x844, with the focused step first on narrow screens and zero horizontal
  overflow;
- the browser console reported no warnings or errors;
- database assertions confirmed unchanged season and schedule rows and zero new
  model calls through Green;
- the completed browser fixture was discarded and replaced by a fresh 3-of-4
  card fixture for the creator walkthrough;
- no live Linux connection, deployment, worker restart, model call, S01 close,
  recovery decision, private publication, or public release occurred.

### Creator decision — DASH-04 accepted — 2026-08-27

The creator accepted the walkthrough and
[DASH04_PREPARATION_REHEARSAL.md](docs/dashboard/rehearsals/DASH04_PREPARATION_REHEARSAL.md), then
separately authorized DASH-05. DASH-04 acceptance did not authorize live Linux
inspection, deployment, S01 private close, worker/model operation, private
publication, or public release.

## DASH-05 implementation checkpoint — 2026-08-27

The creator separately authorized `DASH-05`, Live supervision and
consequence-first Recovery. The bounded sandbox implementation is code-complete
and locally verified; its healthy, retry, skip, desktop, and narrow creator gate
remains open.

Implemented boundaries:

- schema version 5 adds an optimistic version to recovery records; Live action
  reviews bind season, run, and recovery versions to a canonical snapshot hash;
- authenticated `/api/v2/live` exposes durable lifecycle, schedule, run,
  accepted-count, call-progress, worker lease, queue, day-close, next-direction,
  Last accepted beat, and recovery truth;
- `/api/v2/live/transcript` deliberately opens accepted records only; Live
  polling does not replace that pane and new accepted material remains
  creator-triggered;
- `/api/v2/live/impact-review` is read-only and presents separate pause, resume,
  retry, skip, and private-close consequences without a preselected path;
- `/api/v2/live/action` is sandbox-only, rejects S01, requires CSRF, expected
  versions, and the exact review hash, and returns a durable request receipt;
- exact request replay is idempotent, reused request IDs with different intent
  conflict, and stale review hashes or versions fail without automatic retry;
- retry keeps failed calls and accepted anchors, returns the run to QUEUED, and
  inserts priority `-100` work ahead of later schedule items;
- skip requires the season-qualified typed phrase supplied by its review;
- private end is not executable from Recovery and routes only to the unimplemented
  DASH-06 private-close review;
- the legacy dashboard, production environment, and all live S01 paths remain
  untouched.

Local evidence:

- the complete test suite passes with the final count recorded under Latest
  local implementation verification;
- repeated healthy Live reads produce zero database changes;
- tests prove accepted-only transcript output, failed-output exclusion, retry
  priority, typed skip, pause/resume, exact replay, stale rejection, and the
  non-executing private-end boundary;
- JavaScript syntax and `git diff --check` pass;
- automated in-app-browser navigation to localhost was denied by the browser
  security layer, and no alternate browser path was used. Three disposable
  creator fixtures remain available for the visual and interaction gate.

### Creator gate — DASH-05 rehearsal pending

Complete healthy supervision plus independent retry and skip rehearsals in
[DASH05_LIVE_RECOVERY_REHEARSAL.md](docs/dashboard/rehearsals/DASH05_LIVE_RECOVERY_REHEARSAL.md), including
desktop and narrow visual review. This is not authorization for DASH-06, live
Linux inspection, deployment, S01 private close, worker/model operation,
publication, or public release.

## Baseline preserved

The checkout already contained user work before implementation began:

- modified `README.md` and `CLAUDE.md`;
- untracked `scripts/setup_macos.sh`;
- untracked `PRODUCTION_SPEC.md`, `ARCHITECTURE_SPEC.md`, and
  `IMPLEMENTATION_PLAN.md`.

Baseline verification before Luna changes:

```text
.venv/bin/python --version
Python 3.14.6

.venv/bin/python -m pytest -q
8 passed

.venv/bin/improv --help
legacy validate/schema/backends/run command surface present
```

## Gate summary

| Gate | Status | Evidence |
|---|---|---|
| Gate 0 — baseline protection | COMPLETE | v1 schema and dry-run compatibility tests; injected clock and scripted fake protocols added |
| Gate 1 — season domain and calendar | COMPLETE | pure domain models, transitions, Pacific schedule, DST and privacy-shape tests |
| Gate 2 — SQLite/events/outbox | COMPLETE | six packaged idempotent migrations, including additive accepted-turn causality, call provenance, preparation-version fields, recovery optimistic versions, and versioned private-close receipts/handoffs; WAL/foreign keys, constrained repositories, reclaimable leases, durable events/work/outbox, safe idempotent projector |
| Gate 3 — commands/workflow shell | COMPLETE | typed create/transition/opening-revision/preflight/green/control/recovery commands, atomic request fingerprints/replay, 21-run enqueue/lease boundary, deterministic fake worker, recovery decisions, handoff enqueue, later-season reopening; 76 tests pass |
| Gate 4 — model boundaries | PARTIAL | normalized streaming results, partial/cancelled scripted failures, persisted usage/finish metadata, strict actor/orchestrator/diary/orientation envelopes, capability negotiation, purpose-specific private contexts, model-call repository, and private redacted audit writer exist; the concrete live client still lacks provider-native schema enforcement and S01 exposed repeated tagged-envelope failures |
| Gate 5 — recoverable scene runner | PARTIAL | four-round/four-actor runner, dynamic order, 30-minute injected deadline, durable stage/turn checkpoints, restart resume, wellness-first handling, one correction, readable non-canon markers, neutral interruption, live-manifest construction, durable seven-day clock, TTRPG-style instructions, and worker wiring exist; explicit word limits, role/canon review, repetition controls, and the future round/spotlight structure remain unresolved |
| Gate 6 — memory/canon/diaries/daily direction | PARTIAL | actor-local memory notes now carry across runs without peer leakage; prior accepted canon and the preceding shared outcome carry forward; one diary obligation per active actor-day, autonomous slot choice, personal rather than technical diary guidance, soft target notes, durable close-day work, hidden orchestrator-only next-day direction, closed-day script/canon planning context, and the full 21-slot fixture are covered; versioned memory/canon ledger remains |
| Gate 7 — wellness/tap-out/orientation | PARTIAL | private orientation prompt, explicit signal parsing, observational audit, default three-signal per-season counter, season-local manual-review override, tap-out status when enabled, private notifications, scene/diary signal seams; alternate casting, character archives, consent/revocation, and return boundaries remain |
| Gate 8 — scheduler/restart/service | PARTIAL | sequential durable worker, original-order catch-up, durable run-priority recovery retry, lease use, run start/completion timestamps, `+HH:MM:SS` delay markers, four-hour `WAITING_FOR_MODEL` timer, Linux service lifecycle, migrations, status, recovery CLI, and private-manifest scene construction are covered; live endpoint/model evidence remains |
| Gate 9 — private dashboard | PARTIAL | creator-accepted DASH-00 through DASH-04 plus locally complete DASH-05 and DASH-06 provide the default-disabled v2 seam, trustworthy Home, causal Day Review, sanitized diary disclosure, five-stage Diagnostics, exact Review return, versioned Prepare, stable Live supervision, consequence-reviewed sandbox Recovery, and versioned Seasons controls while preserving the legacy WSGI surface; DASH-05 and DASH-06 creator walkthroughs remain gated |
| Gate 10 — publication | PARTIAL | explicit wellness/privacy/consent review, revisable diary decisions with edit events, immutable versioned public Markdown/manifest export, private-root checks, idempotent replay, and a distinct DASH-06 private-close receipt, allowlisted preview, typed publication intent, and private-hash guard are covered; departing-actor consent records remain |
| Gate 11 — benchmark/pilot simulation | PARTIAL | accelerated fake/live-manifest fixtures cover 21 scene slots, diaries, day directions, wellness routing, and recovery; the real S01 pilot reached Day 2 but exposed format, latency, continuity, role-input, repetition, and review-surface failures, so a manual pre-season rehearsal and isolated one-day live-model acceptance test now remain |
| Gate 12 — S01 operator overhaul and one-day acceptance | PARTIAL | the Day 2 evidence, privacy boundary, functional workflow, complete Penpot design, implementation sequence, rollback, and acceptance ladder are creator-approved; DASH-00 through DASH-04 are creator-accepted, DASH-05/DASH-06 are implemented and locally verified at their creator gates, and DASH-07 has a deterministic isolated one-day rehearsal; creator walkthroughs, any separately authorized live-model day, DASH-08+, full native-schema implementation, and final model decisions remain incomplete |

## Decisions made during implementation

- `ProductionPlan` v1 remains unchanged and is exported separately from the season schema.
- Season scheduling uses strict “next 06:00 Pacific boundary” semantics: approval exactly at
  06:00 waits for the following day, avoiding a race with the boundary that arms it.
- Gate 1 uses deterministic natural IDs for schedule slots (`S01-run-01` etc.); persistence
  may add UUIDs later while retaining these uniqueness keys.
- Domain code has no filesystem, database, web, or model dependency.
- SQLite is the operational source of truth; readable artifacts are committed through a
  natural-keyed outbox and projected idempotently into separately validated state/private/public
  roots.
- Gate 2 uses only Python standard-library persistence and filesystem primitives; no dependency
  installation or network access was required.
- Migration SQL is declared as package data so installed distributions retain the schema source.
- `SQLiteDatabase` is the primary Gate 2 API; `SQLiteStore` remains a compatibility alias for the
  existing local test/service harness.
- Packaged numbered SQL migrations are the canonical schema source; migration
  1 remains the base schema and migration 2 additively introduces accepted-turn
  causality without backfilling legacy evidence.
- Gate 2 preserves the season aggregate snapshot, immutable schedule natural keys, optimistic
  versions, event/work/outbox natural keys, root-bound artifact paths, hashes, and byte lengths.
- Gate 3 provides typed `CreateSeason`, `TransitionSeason`, `ReviseOpening`, `PreflightSeason`,
  `GreenSeason`, `ControlSeason`, and `ResolveRecovery` commands with request-id replay and
  changed-intent rejection. `green` requires successful preflight, snapshots the opening and
  private model manifest, creates the immutable 21-slot schedule, and enqueues one durable scene
  work item per slot. Request journaling and command effects now share one SQLite transaction,
  including a failure-injection test for rollback. Closing queues a private handoff work item.
- Gate 3 recovery is explicit: `EnterRecovery` marks a run and season before the creator can
  choose `retry`, `skip`, or `end`; retry/skip resume the season only after the decision.
- Expired work leases are reclaimable by a later worker, preserving attempt counts for restart
  recovery.
- Gate 4 keeps the existing `ChatClient` protocol and adds a backend-neutral call result with
  partial text, cancellation, timing, and error-type metadata. Structured actor/orchestrator
  envelopes now include diary and orientation responses; context builders require explicit state
  inputs and deny unclosed diary access to the orchestrator. Model-call attempts persist
  normalized completion/failure metadata, while private audit files are redacted and append-only.
- Gate 4 capability negotiation is connected to the normalized collector: it prefers a
  provider-native structured stream when advertised and otherwise appends strict tagged-format
  instructions without changing the low-level client.
- Gate 5 uses accepted actor turns and orchestrator interventions as separate durable records.
  A raw actor attempt is audited before review; a hard-boundary violation gets one private
  correction, and a second violation remains readable as non-canon before a neutral interruption.
- Diary service decisions are actor-local. A future slot choice is durable, a first accepted
  entry is not quality-rewritten, soft word-target misses become private notes, and a late entry
  retains its original day with a visible private marker.
- Day closure uses the actual third-run resolution instant plus `+02:00:00`; the next-day
  director refuses to run unless the durable day row is closed.
- Wellness signal records store raw text only in private audit files. SQLite events and
  notifications carry observational metadata, and the third explicit signal changes only the
  correct cast member to `DEPARTED`; manual interventions do not increment the counter.
- The durable worker claims one item at a time, processes due scenes in original schedule order,
  records the original scheduled timestamp and execution delay, and requeues a later run when
  an earlier run is unresolved. This keeps the server autonomous from dashboard availability.
- Model failures now enter a durable `WAITING_FOR_MODEL` request. After four injected hours the
  request becomes `RECOVERY_REQUIRED` on both the run and season aggregates with a concise
  notification; retry/skip/end remains a creator command rather than an autonomous story decision.
- The live worker attaches diary/day coordination after each scene, queues a durable `CLOSE_DAY`
  item at the actual `+02:00:00` cutoff, and refuses next-day direction until the day is closed.
- Fictional time is derived from the immutable schedule rather than actual delayed execution:
  slots 1/2/3 are morning/afternoon/evening, and a sleep interval precedes every later day's
  morning. The approved four-round/16-actor-turn shape is unchanged.
- Cross-run live context is rebuilt from durable evidence: accepted orchestrator canon, the
  previous final shared narration, and character-partitioned memory notes. Hidden next-day
  direction is a separate orchestrator-only input and is never promoted into actor context.
- Private progress, danger, mystery, and relationship clocks are currently prompt-level GM
  mechanics rather than new public schema fields. This gives the live models stronger play
  structure without migrating or rewriting S01 state.
- Publication constructs a new public tree from cleared diary IDs only. Private source paths,
  pending season-level model calls, and incomplete wellness/privacy/consent confirmations block it.
- The first dashboard slice is a standard-library WSGI app intentionally hosted with the Linux
  service and opened from the Mac browser; it uses scrypt owner sessions and CSRF for mutating
  actions, with no public-network binding by default.
- Dashboard status polling is deliberately separate from content reload: it
  runs every 60 seconds and does not replace the open Diary desk or Day Review.
  The v2 authenticated owner can deliberately read safely separated diary text
  from a held attempt without receiving raw wellness wording and without
  changing private, canon, wellness, or publication state. The preserved legacy
  route has not been promoted as the v2 privacy contract.
- The accelerated pilot fixture runs the real live-manifest `SceneRunner` through all 21 scheduled
  queue items, creates all 28 daily diaries, closes all seven days, and creates six private
  next-day directions. It is not yet the wellness, publication, or live Linux acceptance pilot.

## Current failures / manual gates

- No automated Gate 0/1/2 failures are known at this status update.
- Before ending or otherwise controlling S01, inspect the authoritative Linux
  season, run, work-item, recovery, model-call, diary, and day-closure records.
  Do not infer current operational state from the Day 2 export or this local
  checkout, and do not edit SQLite statuses manually.
- Preserve all S01 raw attempts, accepted artifacts, diaries, wellness records,
  events, and model metadata. Ending S01 is not permission to publish or delete
  any private record.
- Gate 4 needs a real provider-native structured-output implementation and
  backend contract tests. Tagged output must remain only a declared fallback.
- Gate 5 still needs explicit word-limit enforcement, role/canon/identity review,
  repetition detection, and an owner decision about future mandatory round
  participation. Gate 6 still needs versioned memory/canon repositories. Gate 7
  still needs alternate casting, archives, departing-actor consent, and return
  boundaries.
- Gate 9 chronology and completion evidence are creator-accepted in DASH-02.
  DASH-03 locally adds call provenance and stage separation while preserving
  the ordinary-view privacy boundary; creator explanation-quality acceptance
  remains pending.
- Final actor/orchestrator assignments remain a creator decision after the
  isolated one-day benchmark. Model size alone is not an acceptance criterion.

## Specification review note

The earlier interview rule for immediate local/public diary export was superseded by the
creator's later decision: every season remains private until its end-of-season `publish`
gate, until the creator removes that requirement. `PRODUCTION_SPEC.md` is authoritative on
this point; the private review and immutable export workflow is now implemented, while the
public website remains behind that gate.

## Exact next action

`DASH-00` through `DASH-04` are accepted. `DASH-05` and `DASH-06` are
implemented and locally verified. The next decisions are whether the creator
accepts DASH-05's healthy supervision/retry/skip rehearsal and DASH-06's
private-close/publication rehearsal.

Do not mark `DASH-05`, `DASH-06`, or `DASH-07` accepted or begin `DASH-08`,
deployment, live Linux inspection, the already decided but still unexecuted S01
private close, a worker restart, model use, or real publication without their
separate decision and evidence gates.

## Latest local implementation verification

```text
./.venv/bin/python -m pytest -q
148 passed in 9.26s

node --check src/improv_troupe/web/static/dashboard-legacy.js
passed

node --check src/improv_troupe/web/static/dashboard.js
passed

./.venv/bin/improv dashboard --help
passed previously for DASH-00; --enable-v2 remains explicit and disabled by default

git diff --check
passed
```

This pass changed local schema/repository, Live supervision services, dashboard
read/view code, tests, packaged assets, fixture helpers, and durable
documentation for the separately authorized `DASH-05` slice. It did not
inspect live Linux state, deploy, restart a production service, run a model,
end S01, mutate production recovery, or publish anything.

### DASH-06 local implementation evidence — 2026-08-27

The separately authorized `DASH-06` Seasons slice is implemented against a
disposable S02 fixture. It adds a sixth additive migration for closure
snapshots, closure receipts, verified handoffs, and action receipts; a terminal
`PRIVATE_COMPLETE` season state; versioned private-close intent; and a separate
publication preview/publish route. Private close preserves the archive hash,
records unresolved work, and stops later queued fixture work without deleting
or rewriting evidence. Publication begins only after the private receipt,
defaults diaries to private, uses an exact diary-only allowlist, requires typed
intent and three confirmations, and proves the private archive hash is
unchanged afterward.

The v2 Seasons view is enabled for sandbox S02 rehearsal only. Its controls are
CSRF-protected; S01 and production mutations fail closed. Local verification
passed with `154 passed in 8.96s`, Python compilation, JavaScript syntax, and
`git diff --check`. The creator walkthrough is documented in
[`DASH06_SEASONS_REHEARSAL.md`](docs/dashboard/rehearsals/DASH06_SEASONS_REHEARSAL.md). No live Linux
state was inspected, no service was deployed or restarted, no model was run,
no S01 state was changed, and no real publication occurred.

### DASH-07 local deterministic one-day evidence — 2026-08-27

The separately authorized DASH-07 preparation work adds a dedicated
`S02-ONE-DAY` rehearsal. Its root guard refuses the production data root and
any non-empty target. It advances a virtual Pacific clock across morning,
afternoon, and evening while exercising the normal scene, diary, day-close, and
next-day-direction services through a deterministic in-process client. A
non-secret JSON report records run and diary outcomes, event receipt IDs and
types, model-call provenance, archive hashes, unresolved work, and creator
judgment prompts. The report confirms no model endpoint was contacted and no
public projection was created.

The local deterministic run completed three 16-turn slots, four written
diaries, day closure, and next-day direction with no unresolved work. It is
documented in [`DASH07_ONE_DAY_REHEARSAL.md`](docs/dashboard/rehearsals/DASH07_ONE_DAY_REHEARSAL.md).
This is not a live-model test, browser/keyboard acceptance, S01 operation,
deployment, or evidence that another season is justified.

### Isolated three-day live continuity evidence — 2026-08-31

The isolated `S02-THREE-DAY` rehearsal completed nine live-model scene runs
using Qwen3 30B Instruct for the director and GPT-OSS 20B for all four actor
roles. Every run completed its 16-turn limit (`9/9`), with `144/144` turns,
`36/36` director plans, and `36/36` orchestrator rounds accepted. All twelve
diaries were written and validated at 405–532 words. All three days closed and
each produced a next-day direction.

The day-two/day-three continuity receipt confirms prior accepted canon, the
previous shared outcome, private day direction, actor-local memory, and prior
actor canon were present in both subsequent opening contexts. The first day-2
direction attempt was deliberately retained as a rejected audit record after
missing the required continuity anchor; a single resumed repair was accepted.
There are no pending model calls or unresolved durable work, and no public
projection was created (`public_archive_sha256` is the empty-tree hash).

This is isolated nonproduction evidence of the current prompt, diary-repair,
continuity, and model-size configuration. It is not a production deployment,
browser/accessibility acceptance, S01 operation, or final model-selection
decision. The full local regression suite passed (`193 passed`) and
`git diff --check` passed.

## Amaranth branch notes
- Amaranth addendum: anti-echo actor rule (never restate narration imagery; add one sensory detail from your own vantage) plus advisory ECHO_PHRASE lint (stem-normalized 3-word overlap vs a reference narration/adjudication, one merged run per span); actor prompt version bumped to scene-actor-v7-prose-craft-2.
