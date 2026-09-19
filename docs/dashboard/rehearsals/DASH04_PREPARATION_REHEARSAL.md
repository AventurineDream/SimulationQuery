# DASH-04 manual preparation rehearsal

**Status:** creator-accepted on 2026-08-27

**Scope:** disposable local S02 fixture only

**Production effect:** none. This rehearsal cannot target S01, run a model,
write the production schedule, arm a season, restart a worker, or publish.

## Automated baseline — 2026-08-27

- schema version 4 additively stores preparation workspaces, immutable character
  card and model-assignment versions, receipts, invalidations, and idempotent
  action responses;
- the fixture begins with season idea v2 and opening v3 approved, three of four
  character cards approved, and Mara v4 awaiting review beside approved v3;
- the complete eight-step action path was exercised through the authenticated
  browser at desktop and narrow widths;
- the final Green action produced a readiness receipt with
  `season_armed=false` and `command_submitted=false`;
- automated checks confirmed unchanged season rows, unchanged schedule rows,
  zero new model calls, S01 rejection, production-environment rejection,
  idempotent replay, prior-version readability, and explicit dependency
  invalidation;
- each synthetic role sheet and orientation record carries its approved
  character-card source version; content remains closed until deliberate reveal,
  and approved card summaries remain readable in Review without exposing the
  private extensions;
- public-projection tests explicitly exclude both character-card and private
  role-sheet sentinel text;
- the browser reported no console errors and no horizontal overflow at
  1440x1024 or 390x844.

## Creator walkthrough

Start from the fresh local **Prepare** tab. Complete the steps in order and
record any wording, evidence, or consequence that is unclear.

1. **Season idea** — confirm approved idea v2 is understandable as the stable
   source. No action is required in the fixture.
2. **Opening** — inspect approved opening v3 and the stated consequence of a
   versioned revision. Do not revise it during the main happy-path rehearsal.
3. **Character cards** — compare Mara draft v4 with approved v3, edit if useful,
   then approve the intended version. Confirm that 4/4 unlocks model assignment.
4. **Model assignment** — inspect the stored candidates and approve the stored
   assignment. Confirm that no model was selected or downloaded automatically.
5. **Preflight** — record stored-only preflight evidence. Confirm that no model
   availability probe ran.
6. **Private preparation** — compare each approved card with its generated
   role-sheet/orientation version, deliberately reveal any private fixture you
   want to inspect, then record the review. Confirm that private text is closed
   by default and every artifact names its source card version.
7. **Schedule preview** — record the 7-day, 21-slot preview. Confirm that no
   durable production schedule changed.
8. **Green review** — record readiness. Confirm that the receipt explicitly says
   the season was not armed and no command was submitted.

## Creator decision record

- Walkthrough completed: yes, 2026-08-27
- Runbook wording accepted: yes
- DASH-04 accepted: yes
- Notes or requested changes: none

Acceptance closed DASH-04 only. The creator separately authorized DASH-05; it
did not authorize live Linux
inspection, deployment, S01 private close, worker or model operation, recovery,
publication, or a public release.
