# AI Improv Troupe dashboard — Penpot collaboration brief

**Status:** low-fidelity interaction architecture, Warm Instrument system,
Home/Day Review, Prepare, Live/Recovery, Diagnostics, and Seasons/Publication
high-fidelity checkpoints approved and frozen; the complete dashboard design is
approved; DASH-00 through DASH-03 are implemented, locally verified, and
creator-accepted; DASH-04 is implemented and locally verified at its manual S02
creator gate

**Updated:** 2026-08-27

**Functional source:** [DASHBOARD_OVERHAUL_PLAN.md](DASHBOARD_OVERHAUL_PLAN.md)

**Design boundary:** Penpot work may explore layout and interaction, but it does
not alter approved functional, privacy, or action-safety decisions without an
explicit creator decision recorded back in the functional plan.

## 1. Objective

Turn the approved functional plan into an understandable private operator
application before implementation begins.

The first Penpot outcome is not a polished skin. It is a reviewable set of
low-fidelity flows that proves:

- the six stable destinations are intelligible;
- the creator always knows environment, season, lifecycle state, and freshness;
- preparation feels guided without becoming a rigid wizard;
- Live is calm until control-room evidence is needed;
- Review supports sustained reading without moving underneath the creator;
- Diagnostics explains a model call without becoming a model laboratory;
- private end and publication cannot be confused;
- desktop and narrow layouts preserve the same capability.

## 2. Approved constraints

- Guided studio workflow is the primary mental model.
- Control-room density is limited to Live and Diagnostics.
- Primary destinations are Home, Prepare, Live, Review, Diagnostics, and
  Seasons.
- Destinations remain stable across lifecycle states.
- Live shows one Last accepted beat; full transcript reading is deliberate and
  manually refreshed.
- Prepare uses a visible checklist plus one focused workspace.
- Cast and Continuity is distributed across Prepare, Review, Diagnostics, and
  Live rather than becoming another destination.
- First Diagnostics is read-only and call-focused.
- Narrow layouts remain operationally complete.
- Synthetic fixture content is the default.
- Reading never mutates canon, wellness, privacy, recovery, or publication.
- Ending and publication are separate journeys.

## 3. Penpot file structure

Recommended file name:

`AI Improv Troupe — Operator Dashboard`

Recommended pages:

| Page | Contents |
|---|---|
| `00 — Decisions` | Approved constraints, vocabulary, privacy matrix, design questions |
| `01 — Flow Map` | Lifecycle, recovery, review/diagnostics, private close, publication |
| `02 — Content & Components` | Synthetic fixture, information priority, reusable component inventory |
| `10 — Desktop Low-fi` | Primary desktop screens and exceptional states |
| `11 — Narrow Low-fi` | Operationally complete narrow adaptations |
| `20 — Prototype Flows` | Click paths for the critical operator scenarios |
| `30 — Visual System` | Typography, color, spacing, iconography, states—only after low-fi approval |
| `40 — High-fi` | Approved desktop and narrow compositions |
| `90 — Parking Lot` | Deferred ideas that are not approved scope |

## 4. Synthetic rehearsal fixture

Use one clearly labeled nonproduction season throughout the file.

### Fixture identity

- Environment: `SANDBOX`
- Season: `S02 — The Weather Library`
- Premise: four specialists maintain an orbital archive of impossible weather;
  one storm begins rewriting the labels on its own containment chamber.
- Schedule: one rehearsal day with morning, afternoon, and evening runs.

### Synthetic cast

| Character | Public card anchor | Status |
|---|---|---|
| Mara Venn | acoustic engineer; listens before acting; clipped humor | Active |
| Tavi North | repair diver; improvises physical solutions; superstitious | Active |
| Oren Vale | chef-meteorologist; notices atmosphere through taste and smell | Active |
| Sable Reed | oral historian; protects ambiguity; asks unsettling questions | Active |

These are design fixtures, not approved future cast members.

### Required evidence shapes

The fixture should include enough varied content to exercise the UI:

- one healthy completed run with 16 accepted actor turns;
- one completed run with 15 accepted turns and a visible correction;
- one partial run in `RECOVERY_REQUIRED` after a completed stream failed schema
  validation;
- one repeated-turn validator finding;
- one native-schema call and one tagged-fallback call;
- one accepted diary;
- one late diary;
- one held private diary with no raw wellness text;
- one missing diary obligation;
- one unread operator notification;
- one pending artifact projection;
- one long transcript and one long raw model output;
- one stale preparation artifact that invalidates later preflight evidence.

No real S01 diary, prompt, role sheet, hidden direction, or wellness text enters
the Penpot file.

## 5. Flow map boards

Create small state-and-action maps before individual screens.

### Prepare to green

```text
Idea -> Opening -> Character cards -> Model assignment -> Preflight
  -> Role sheets/orientation -> Schedule preview -> Green review
```

Show revision loops and downstream invalidation. Navigation does not approve a
step.

### Live and recovery

```text
Armed -> Running <-> Paused
             |
             v
        Waiting for model -> Recovery required
                                | retry -> Running
                                | skip  -> Running
                                | end   -> Private close
```

### Review and diagnostics

```text
Day/Diary/Cast evidence -> Select accepted item -> Explain in Diagnostics
                                              -> Return to causal Review position
```

### Private close and publication

```text
Read-only close snapshot -> Typed private-end confirmation -> Close receipt
  -> Private archive/handoff

Private archive -> Separate publication review -> Exact public preview
  -> Typed publish confirmation -> Immutable publication receipt
```

These should appear as visibly separate flows.

## 6. Low-fidelity desktop frame inventory

Use one consistent desktop canvas during low-fidelity work. Exact breakpoints and
container widths remain visual decisions.

### Global shell

- standard connected production state;
- sandbox state;
- stale but readable state;
- disconnected state;
- attention drawer open;
- season selector with one active and prior private seasons.

### Home

- healthy running season;
- creator attention required;
- no active season;
- sandbox rehearsal;
- stale evidence.

### Prepare

- checklist overview with focused current step;
- character-card editing/review;
- model assignment evidence;
- failed preflight;
- stale downstream steps after an opening/card revision;
- role-sheet/orientation comparison;
- schedule preview;
- green impact review and typed confirmation;
- approved read-only historical preparation record.

### Live

- healthy running scene;
- Last accepted beat plus New material available;
- stable full transcript open;
- paused;
- waiting for model;
- recovery required with retry/skip/end explanations;
- command receipt;
- private-end confirmation.

### Review

- complete day with morning/afternoon/evening summaries;
- one expanded causally ordered run;
- partial run with missing evidence;
- diary grid with accepted, late, held, and missing states;
- held-diary explicit disclosure boundary;
- Cast and Continuity record;
- stable reading with new material available.

### Diagnostics

- filtered call list;
- successful native-schema call;
- tagged-fallback call;
- completed-stream/schema-failure call;
- correction and validator findings;
- raw/parsed/validated/accepted/rendered comparison;
- link back to Review;
- no-results and unavailable-artifact states.

### Seasons

- season list with active, private-complete, and published states;
- pre-end read-only snapshot;
- private-end typed confirmation;
- private closure receipt and pending handoff;
- private archive;
- separate publication review;
- exact public preview;
- immutable publication receipt.

## 7. Narrow frame priorities

Produce narrow adaptations for at least:

- Home with attention;
- Prepare checklist and one focused step;
- Live running;
- Live recovery decision;
- stable transcript reading;
- complete Day Review;
- long diary reading;
- Diagnostics call stages as tabs or sequence;
- private-end confirmation;
- publication preview and confirmation.

No horizontal data tables are required. Convert records into cards, stacked
definition lists, tabs, or disclosures while preserving the same evidence.

## 8. Reusable component inventory

Begin with low-fidelity components and state variants:

- global navigation;
- environment badge;
- season selector;
- connection/freshness indicator;
- lifecycle status badge;
- worker status;
- attention item and drawer;
- next-safe-action card;
- checklist step and invalidation state;
- evidence/version marker;
- schedule/day/slot marker;
- Last accepted beat;
- transcript stage beat and actor turn;
- New material available indicator;
- diary state card;
- cast status/card summary;
- diagnostic call row;
- raw-to-rendered stage selector;
- validator finding;
- empty, missing, stale, blocked, and error states;
- impact summary;
- typed confirmation;
- command receipt;
- explicit private disclosure.

Do not settle final component styling during the first flow pass.

## 9. Prototype flows

The first clickable prototype should cover:

1. Home -> highest-priority attention -> evidence -> safe workflow;
2. Prepare -> revise character card -> observe downstream invalidation -> rerun
   preflight -> green review without submitting green;
3. Live -> read Last accepted beat -> open transcript -> receive New material
   available -> refresh deliberately;
4. Review -> partial run -> Diagnostics -> inspect schema failure -> return to the
   exact review position;
5. Recovery -> compare retry/skip/end consequences -> stop before submission;
6. Seasons -> private close preview -> close receipt -> demonstrate that
   publication remains separate;
7. Publication review -> exact preview -> stop before publish submission.

Prototype confirmations demonstrate the interaction but must not imply that
Penpot design approves or executes live commands.

## 10. First collaborative checkpoint

The first Penpot session is complete when the creator can review:

- the file/page organization;
- the lifecycle flow map;
- the global shell information priority;
- desktop and narrow Home;
- desktop and narrow Day Review;
- annotations for privacy, refresh behavior, and consequential actions.

At that checkpoint, ask for feedback on hierarchy and flow before adding visual
polish or designing all remaining screens.

### First-checkpoint decision — approved

**Decision date:** 2026-08-24

The creator approved the complete first checkpoint: file organization,
lifecycle flow, global-shell priority, desktop and narrow Home, desktop and
narrow Day Review, and navigation hypothesis A. Hypothesis A uses a stable left
rail on desktop and persistent bottom navigation on narrow screens. This
approval establishes the low-fidelity hierarchy and flow; it does not yet
approve the eventual visual system, high-fidelity treatment, or implementation.

### Prepare checkpoint — approved

The second checkpoint was assembled on 2026-08-24 and tests the approved
preparation interaction at desktop and narrow widths:

- the complete eight-step checklist remains visible;
- one focused character-card workspace opens beside or below it;
- navigation is explicitly read-only;
- approval explains its limited effect before execution;
- model assignment remains blocked until all cards are approved;
- an Opening revision previews every downstream invalidation before save;
- replaced versions remain durable, and no private extension is overwritten;
- narrow layout preserves the same statuses, prerequisites, evidence, and
  actions.

The Penpot file contains a normal desktop character-card state, a desktop
Opening-revision impact state, and a narrow character-card state.

### Prepare-checkpoint decision — approved

**Decision date:** 2026-08-24

The creator approved the Prepare checkpoint in full: permanent visibility of
the eight-step checklist, one focused workspace, read-only navigation, explicit
approval impact, named blocked prerequisites, pre-save downstream invalidation,
durable replaced versions, and the operationally complete narrow adaptation.
This approves Prepare's low-fidelity interaction model, not its eventual visual
system or implementation.

### Diagnostics checkpoint — approved

The third checkpoint was assembled on 2026-08-24 and tests the approved
call-focused Diagnostics boundary at desktop and narrow widths:

- a filtered call list preserves the selected synthetic call and its causal
  Review position;
- call identity, binding, timing, token, finish-reason, and artifact-version
  evidence are visible without leaving the detail view;
- raw, parsed, validated, accepted, and rendered stages form one readable
  sequence;
- the completed-stream/schema failure, validator finding, and correction
  attempt remain distinguishable;
- desktop keeps call selection and detail together, while narrow stacks the
  same evidence in causal order;
- long raw output is deliberately disclosed rather than exposed by default;
- Diagnostics remains read-only and includes no rerun, benchmark, bulk model
  comparison, or automated-selection controls;
- raw wellness text remains excluded.

The Penpot file contains one desktop and one narrow Diagnostics call frame for
the synthetic `S02 — The Weather Library` fixture. Both were imported and
visually checked on 2026-08-24.

### Diagnostics-checkpoint decision — approved

**Decision date:** 2026-08-24

The creator approved the Diagnostics checkpoint in full: selected-call
list/detail on desktop, the causal evidence sequence on narrow screens,
deliberate raw-artifact disclosure, return to the originating Review position,
and the read-only boundary with no mutation, rerun, benchmark, or model-selection
controls. This approves the low-fidelity Diagnostics interaction pattern, not
the eventual visual system or implementation.

### Live and Recovery checkpoint — approved

The fourth checkpoint was assembled on 2026-08-24 and tests both ordinary
autonomous performance supervision and the transition to a creator decision:

- healthy Live opens with current durable performance truth, worker/queue
  health, day-completion evidence, and no false demand for operator attention;
- one compact Last accepted beat keeps the creator in contact with the story;
- an explicitly opened transcript remains stable while polling continues and
  presents a creator-triggered New material available action;
- pause, resume, and private-end controls appear only with their current
  validity and explain impact before submission;
- Recovery Required clearly freezes the story at the last accepted beat and
  distinguishes completed transport from failed validation;
- retry preserves failed attempts and enqueues a new attempt, skip preserves
  the ledger position and permits later scheduled work, and end begins a
  separate private-close journey without publishing or deleting anything;
- no recovery path is preselected, and viewing evidence or navigating away does
  not resolve the durable request;
- narrow frames preserve the same story, timing, queue, privacy, consequence,
  and confirmation evidence.

The Penpot file contains healthy Live and Recovery Required frames for desktop
and narrow layouts, using only the synthetic `S02 — The Weather Library`
fixture. All four were imported and visually checked on 2026-08-24. This
checkpoint does not yet approve the visual system or implementation.

### Live-and-Recovery-checkpoint decision — approved

**Decision date:** 2026-08-24

The creator approved the Live and Recovery checkpoint in full: calm autonomous
supervision, one Last accepted beat, stable transcript reading with deliberate
new-material loading, an unmistakable safe stop, and unselected retry, skip,
and private-end paths whose consequences are explained before submission. This
approves the low-fidelity Live and Recovery interaction pattern, not the
eventual visual system or implementation.

### Seasons and Publication checkpoint — approved

The fifth checkpoint was assembled on 2026-08-24 and tests the terminal private
lifecycle and the separate optional public-release journey:

- private close begins with a versioned read-only snapshot of runs, queue,
  accepted story, calls, diaries, cast, notifications, integrity, and archive
  reachability;
- incomplete work remains named and is recorded as unresolved rather than
  disguised as successful completion;
- the effect summary explicitly distinguishes what private close will do from
  what it cannot publish, expose, delete, or rewrite;
- the season-qualified `end S02 privately` intent, version check, command
  receipt, closure work, and terminal-private verification form one journey;
- publication begins only from an explicitly selected `PRIVATE_COMPLETE`
  season and repeats privacy, consent, held-diary, allowlist, and path review;
- the creator sees the exact allowlisted public projection alongside the
  categories that are structurally excluded;
- `publish S02`, immutable release version, manifest hash, and publication
  receipt form a separate journey that cannot alter the private archive;
- desktop and narrow frames preserve the same prerequisites, exclusions,
  consequences, typed intent, and durable-result evidence.

The Penpot file contains private-close and publication-review frames for desktop
and narrow layouts, using only the synthetic `S02 — The Weather Library`
fixture. All four were imported and visually checked on 2026-08-24.

### Seasons-and-Publication-checkpoint decision — approved

**Decision date:** 2026-08-24

The creator approved the Seasons and Publication checkpoint in full: private
close from a versioned snapshot, durable preservation of unresolved work,
season-qualified private intent, and a later separate publication journey with
repeated privacy and consent gates, an exact public preview, structural
exclusions, and an independent immutable receipt. This approves the
low-fidelity Seasons and Publication interaction pattern, not the eventual
visual system or implementation.

### Final low-fidelity system checkpoint — approved

The final foundation checkpoint was assembled and imported on 2026-08-24. It
tests the shared interaction system that connects the already approved screens:

- the Content & Components board orders every task as global truth, task truth,
  evidence, then valid action;
- it defines reusable shell/context, reading/evidence, workflow/action, and
  exceptional-state patterns;
- action friction scales from immediate read-only actions through light,
  workflow, and season/run-qualified consequential actions;
- private material stays absent from ordinary views and appears only through
  deliberate owner-only disclosure where allowed;
- the Prototype Paths board defines seven journeys across Home, Prepare, Live,
  Review/Diagnostics, Recovery, private close, and optional publication;
- each journey preserves season context, provenance, return position, and an
  explicit stop before any unapproved live consequence;
- the Exceptional States board distinguishes loading, fresh, stale-readable,
  disconnected, partial/missing, no-season, invalid-path, command-conflict, and
  narrow/keyboard states;
- exceptional states preserve known durable evidence, name one valid next
  action, and keep invalid actions visibly blocked;
- operational polling may refresh status chrome but cannot replace open
  transcripts, diaries, evidence disclosures, forms, selections, or scroll
  positions.

The three boards use only synthetic content. They do not execute commands,
connect to production state, expose private S01 material, approve a visual
language, or authorize implementation.

### Low-fidelity-architecture decision — approved and frozen

**Decision date:** 2026-08-24

The creator approved the final content/component, prototype-path, and
exceptional-state checkpoint in full. Together with the earlier screen
checkpoints, this freezes the low-fidelity interaction architecture as the
baseline for visual-language and high-fidelity work. Visual exploration may
change typography, color, spacing, shape, iconography, and surface treatment;
it may not silently change information hierarchy, workflow consequences,
privacy boundaries, stable-reading behavior, or action safety. Any such change
requires a new explicit creator decision recorded in the functional plan.

### Visual-language direction checkpoint — Warm Instrument selected

The first visual-language round was assembled, visually checked, and imported
on 2026-08-24. All three directions apply the same frozen Home/Day Review slice
so mood, reading comfort, density, hierarchy, and state signaling can be
compared without functional drift:

- **A · Warm Instrument** — a warm paper reading surface held by a dark
  operational rail; creative field notebook plus dependable instrument panel;
- **B · Molten Observatory** — an evolution of the current dark console in
  which geologic glow appears only at meaningful thresholds;
- **C · Quiet Archive** — a cool editorial research desk with explicit record
  structure, minimal decoration, and print-like reading.

The recommended starting point is **A · Warm Instrument** because it preserves
the project's warmth and strangeness while giving scripts and diaries the
calmest sustained-reading surface. B offers the most continuity with the
current dashboard; C offers the most restrained precision. The comparison and
three detail boards define initial palette, typography roles, shape/rhythm,
state colors, action treatment, and one signature gesture per direction.

At assembly, this checkpoint used only synthetic S02 content and did not itself
approve a visual direction, choose final fonts, create high-fidelity screens,
or authorize implementation.

### Visual-direction decision — approved

**Decision date:** 2026-08-24

The creator selected **A · Warm Instrument** as the visual direction. The warm
paper reading surface, dark operational rail, calm supervision tone, and
creative-field-notebook/instrument-panel relationship now guide token,
component, responsive, and high-fidelity exploration. The unselected Molten
Observatory and Quiet Archive boards remain comparison history rather than
active directions. This selection does not yet approve exact color values,
font stacks, component styling, high-fidelity screens, or implementation.

### Warm Instrument visual-system checkpoint — approved

The selected direction was refined, visually checked, and imported on
2026-08-24 as three boards:

- **Foundations** proposes exact canvas, paper, surface, charcoal, ink, muted,
  and ember roles; UI, reading, and evidence type stacks; spacing and radius
  scales; depth rules; semantic state colors; focus; motion; and accessibility
  behavior;
- **Components** applies the system to navigation, selected context, freshness,
  action tiers, control states, Last accepted beat, stable/new reading,
  evidence disclosure, impact preview, typed intent, durable receipt, stale,
  and disconnected states;
- **Responsive** applies the same visual and safety system to desktop and a
  390-pixel narrow reference, retaining context, evidence, impact, actions,
  stable reading, touch targets, and persistent navigation.

The proposed core colors are warm canvas `#E7E1D5`, paper `#F3EFE6`, reading
surface `#FAF7F0`, charcoal `#26302D`, ink `#222724`, muted text `#6C6B63`, and
ember `#C56F42`. Ember marks selection and the boundary where creative material
meets operator consequence; it is not a generic health or atmosphere color.
Calculated contrast examples are recorded on the board, including Ink/Paper at
13.23:1, Muted/Paper at 4.67:1, and Light/Charcoal at 11.88:1. These
calculations are design evidence, not rendered implementation or accessibility
acceptance evidence.

The type roles propose an Inter/system UI stack, Charter/Georgia authored
reading stack, and SF Mono/Menlo evidence stack. They approve roles and
fallback behavior only if this checkpoint is accepted; no font asset, license,
loading strategy, or final platform rendering has been approved. The breakpoint
proposal keeps the desktop rail at 920 pixels and above and uses bottom
navigation below 920 pixels, subject to real-content testing rather than device
names.

This checkpoint uses only synthetic S02 material. It does not create
high-fidelity screens, connect to production state, execute a command, or
authorize implementation.

### Warm-Instrument-system decision — approved and frozen

**Decision date:** 2026-08-24

The creator approved the Warm Instrument foundations, component language, and
responsive rules in full. The recorded palette roles, typography roles and
fallbacks, spacing/radius/depth scales, state treatments, action tiers, focus
and motion rules, ember-boundary gesture, and desktop/narrow composition rules
are now the frozen visual-system baseline for high-fidelity screens. Calculated
contrast remains design evidence only; font assets/loading, rendered
implementation, keyboard/touch behavior, and human accessibility acceptance
remain later verification gates. A change to the frozen visual system requires
a new explicit creator decision.

### Home and Day Review high-fidelity checkpoint — approved

The first representative high-fidelity checkpoint was XML-validated, rendered
for visual inspection, and imported into the `40 — High-fi` Penpot page on
2026-08-24. It contains four synthetic S02 compositions:

- desktop Home applies the approved calm-supervision shell, stable context,
  freshness, durable progress, Last accepted beat, next slot, cast, Day Review,
  and private system-note hierarchy;
- desktop Day Review combines a run timeline, stable script-reading pane, and
  private diary desk while holding newer accepted material behind an explicit
  load action;
- narrow Home retains season and freshness context, attention, durable summary,
  accepted beat, next slot, and Day Review entry with persistent bottom
  navigation;
- narrow Day Review retains run selection, evidence provenance, saved reading
  position, stable text, deliberate new-material loading, and the raw-wellness
  exclusion within the same operational capability.

The source assets are
[`40-home-desktop.svg`](../../design/penpot/40-home-desktop.svg),
[`40-day-review-desktop.svg`](../../design/penpot/40-day-review-desktop.svg),
[`40-home-narrow.svg`](../../design/penpot/40-home-narrow.svg), and
[`40-day-review-narrow.svg`](../../design/penpot/40-day-review-narrow.svg). They use
only synthetic material, do not connect to production state, and expose no
command submission. This checkpoint tests whether the frozen Warm Instrument
system produces calm supervision and comfortable sustained reading before the
remaining higher-risk workflows receive high-fidelity treatment.

### Home-and-Day-Review high-fidelity decision — approved and frozen

**Decision date:** 2026-08-24

The creator approved the desktop and narrow Home and Day Review compositions in
full. Their calm-supervision hierarchy, Warm Instrument application, desktop
rail, narrow bottom navigation, stable-reading treatment, explicit
new-material loading, saved-position evidence, and private diary boundary are
now the frozen high-fidelity reference for the remaining screens. This approval
does not authorize implementation or weaken later rendered, interactive, or
accessibility acceptance gates.

### Prepare high-fidelity checkpoint — approved

The second high-fidelity checkpoint was XML-validated, rendered for visual
inspection, and imported as a second row on the `40 — High-fi` Penpot page on
2026-08-24. It contains four synthetic S02 compositions:

- desktop and narrow Character Cards retain the entire eight-step checklist,
  one focused editable card, explicit prerequisites, durable version history,
  approval impact, and distinct save-versus-review actions;
- desktop and narrow Opening Revision show every dependent approval, binding,
  preflight result, private artifact, schedule preview, and Green review that
  will become stale before the creator saves the revision.

The source assets are
[`40-prepare-character-cards-desktop.svg`](../../design/penpot/40-prepare-character-cards-desktop.svg),
[`40-prepare-invalidation-desktop.svg`](../../design/penpot/40-prepare-invalidation-desktop.svg),
[`40-prepare-character-cards-narrow.svg`](../../design/penpot/40-prepare-character-cards-narrow.svg),
and
[`40-prepare-invalidation-narrow.svg`](../../design/penpot/40-prepare-invalidation-narrow.svg).
They use only synthetic material and connect to no production state. The
invalidation screens describe a future workflow action but do not execute one;
the current approved Opening remains explicit. At assembly, this checkpoint
awaited creator approval; implementation remained unapproved.

### Prepare high-fidelity decision — approved and frozen

**Decision date:** 2026-08-25

The creator approved the desktop and narrow Character Cards and Opening
Revision compositions in full. Their full-checklist visibility, focused-step
workspace, explicit prerequisites, durable version history, approval impact,
current-approved-truth treatment, downstream-invalidation preview, and distinct
navigation/save/review boundaries are frozen as the Prepare high-fidelity
reference. This approval does not authorize implementation.

### Live and Recovery high-fidelity checkpoint — approved

The third high-fidelity checkpoint was XML-validated, rendered for visual
inspection, and imported as a third row on the `40 — High-fi` Penpot page on
2026-08-25. It contains four synthetic S02 compositions:

- desktop and narrow healthy Live combine current performance truth,
  worker/queue evidence, day-completion state, one Last accepted beat, a stable
  transcript with creator-controlled loading, and only currently valid controls;
- desktop and narrow Recovery Required distinguish completed transport from
  failed validation, anchor all paths to the last accepted beat, and give retry,
  skip, and private end equal unselected action weight with consequences shown
  before submission.

The source assets are
[`40-live-running-desktop.svg`](../../design/penpot/40-live-running-desktop.svg),
[`40-live-recovery-desktop.svg`](../../design/penpot/40-live-recovery-desktop.svg),
[`40-live-running-narrow.svg`](../../design/penpot/40-live-running-narrow.svg), and
[`40-live-recovery-narrow.svg`](../../design/penpot/40-live-recovery-narrow.svg).
They use only synthetic material, connect to no production state, preselect no
recovery path, and execute no command. Raw invalid output and wellness text
remain outside ordinary Live. At assembly, this checkpoint awaited creator
approval; implementation remained unapproved.

### Live-and-Recovery high-fidelity decision — approved and frozen

**Decision date:** 2026-08-25

The creator approved the desktop and narrow healthy Live and Recovery Required
compositions in full. Their calm-supervision hierarchy, worker and queue truth,
stable story reading, exact last-accepted causal anchor, failure-stage evidence,
equal unselected recovery paths, and pre-submission consequence explanations
are frozen as the Live/Recovery high-fidelity reference. This approval does not
authorize implementation or any recovery command.

### Diagnostics high-fidelity checkpoint — approved

The fourth high-fidelity checkpoint was XML-validated, rendered for visual
inspection, and imported as a fourth row on the `40 — High-fi` Penpot page on
2026-08-25. It contains two synthetic S02 compositions:

- desktop Diagnostics keeps a call list beside one selected-call explanation,
  including identity, transport and finish evidence, raw-to-rendered stages,
  a deliberately opened synthetic excerpt, validator finding, correction
  attempt, version provenance, and the exact causal return to Review;
- narrow Diagnostics turns the same evidence into a single call-focused
  sequence, keeps raw output collapsed behind deliberate disclosure, and
  preserves failure, correction, provenance, and return-to-Review context.

The source assets are
[`40-diagnostics-call-desktop.svg`](../../design/penpot/40-diagnostics-call-desktop.svg)
and
[`40-diagnostics-call-narrow.svg`](../../design/penpot/40-diagnostics-call-narrow.svg).
They use only synthetic material, connect to no production state, and execute
no command. Diagnostics remains read-only: reruns, benchmarks, bulk comparison,
automated model selection, private role-sheet contents, and raw wellness text
remain outside this screen. At assembly, this checkpoint awaited creator
approval; implementation remained unapproved.

### Diagnostics high-fidelity decision — approved and frozen

**Decision date:** 2026-08-25

The creator approved the desktop and narrow call-focused Diagnostics
compositions in full. Their selected-call identity, timing and finish evidence,
raw-to-rendered causal sequence, deliberate raw disclosure, validator and
correction history, version provenance, exact return-to-Review point, and
read-only boundary are frozen as the Diagnostics high-fidelity reference. This
approval does not authorize implementation, model operation, or disclosure of
excluded private evidence.

### Seasons and Publication high-fidelity checkpoint — approved

The fifth and final high-fidelity checkpoint was XML-validated, rendered for
visual inspection, and imported as a fifth row on the `40 — High-fi` Penpot
page on 2026-08-25. It contains four synthetic S02 compositions:

- desktop and narrow Private Close begin from the same versioned read-only
  snapshot, preserve unresolved work as unresolved, distinguish every effect
  and non-effect, require the exact season-qualified private intent, and show
  the durable closure sequence without submitting it;
- desktop and narrow Publication begin only from an explicitly selected
  `PRIVATE_COMPLETE` season, repeat privacy, consent, held-diary, allowlist, and
  path checks, show the exact allowlisted projection beside structural
  exclusions, and require a distinct publish intent before an immutable result.

The source assets are
[`40-seasons-private-close-desktop.svg`](../../design/penpot/40-seasons-private-close-desktop.svg),
[`40-seasons-publication-desktop.svg`](../../design/penpot/40-seasons-publication-desktop.svg),
[`40-seasons-private-close-narrow.svg`](../../design/penpot/40-seasons-private-close-narrow.svg),
and
[`40-seasons-publication-narrow.svg`](../../design/penpot/40-seasons-publication-narrow.svg).
They use only synthetic material, connect to no production state, prefill no
intent, and execute no command. Private close cannot publish, publication
cannot alter the private archive, and neither screen exposes structurally
excluded source data. At assembly, this checkpoint awaited creator approval;
implementation remained unapproved.

### Seasons-and-Publication high-fidelity decision — approved and frozen

**Decision date:** 2026-08-25

The creator approved all four Private Close and Publication compositions in
full. Their versioned closure snapshot, unresolved-work preservation,
effect-versus-non-effect explanation, exact private intent, terminal-private
verification, separate release eligibility, repeated privacy and consent gates,
exact allowlisted projection, structural exclusions, distinct publish intent,
and immutable-result evidence are frozen as the Seasons/Publication
high-fidelity reference. This approval completes and freezes the dashboard's
high-fidelity design. It does not authorize implementation, private close, or
publication.

## 11. Visual questions reserved for Penpot

- left rail, top navigation, or another stable navigation placement;
- density and whitespace rhythm;
- how warm, theatrical, scientific, or utilitarian the private console feels;
- typography for sustained script and diary reading;
- color use for environment, state, privacy, attention, and danger;
- icon language;
- transcript speaker treatment;
- desktop canvas and narrow breakpoint;
- motion, if any, for new accepted material;
- whether the current dark molten aesthetic is retained, evolved, or replaced.

These are collaborative design choices, not implementation defaults.
