# DASH-05 Live and Recovery rehearsal

**Status:** implemented and locally verified; creator walkthrough pending

**Scope:** three disposable local S02 fixtures only

**Production effect:** none. These fixtures reject S01 and production-mode
actions. They do not connect to live Linux, operate a real worker or model, end
S01, publish, or enter the DASH-06 private-close workflow.

## Implemented boundary — 2026-08-27

- schema version 5 adds a recovery version used with existing season and run
  versions for optimistic command review;
- Live reads durable season, schedule, run, accepted-count, model-call,
  worker-lease, queue, diary/day-close, and recovery evidence;
- the accepted transcript opens deliberately and remains outside operational
  polling; newer accepted material is offered without replacing the open pane;
- pause, resume, retry, and skip require a read-only consequence review and its
  exact snapshot hash before submission;
- retry is inserted with priority `-100`, ahead of later scheduled work;
- skip requires the season-qualified phrase shown by its impact review;
- exact request replay returns the original command result; stale reviews and
  reused request IDs with different intent fail closed;
- Recovery never preselects a path;
- private end is non-executable here and only links to the future DASH-06
  private-close review;
- failed calls and the exact last accepted causal anchor remain stored and
  readable; invalid output does not enter transcript or accepted counts.

## Local evidence

- the full Python suite passes with 148 tests;
- dashboard JavaScript syntax and whitespace checks pass;
- authenticated WSGI tests exercise healthy polling, stable accepted-only
  transcript projection, retry priority, typed skip confirmation, pause/resume,
  exact replay, stale conflict, S01 rejection, and the non-executing private-end
  route;
- two repeated Live reads cause zero database changes;
- automated in-app-browser navigation to localhost was denied by the browser
  security layer. No alternate browser path was used. Desktop and narrow visual
  acceptance therefore remain part of this creator walkthrough.

## Creator walkthrough

Three independent fixtures are running so one consequence does not contaminate
another:

1. **Healthy supervision** — `http://localhost:8878/v2/live?season_id=S02`
   - confirm the active lease, queue, current run, timing, call, accepted count,
     day state, and Last accepted beat are understandable;
   - open the transcript, leave it open, and confirm the operational surface is
     visually separate;
   - open Pause impact review, confirm, inspect its receipt, then open Resume
     impact review and confirm;
   - confirm closing or navigating away never presents itself as a worker
     control.
2. **Retry rehearsal** — `http://localhost:8876/v2/live?season_id=S02`
   - confirm no recovery path is preselected;
   - compare the failure evidence, queue effect, and exact last accepted beat;
   - open Retry impact review and confirm it;
   - confirm a durable receipt appears and the run returns to the queue ahead of
     later scheduled work.
3. **Skip rehearsal** — `http://localhost:8877/v2/live?season_id=S02`
   - open Skip impact review;
   - verify the consequence wording and exact typed confirmation;
   - confirm it and inspect the receipt;
   - confirm the accepted beat remains unchanged and the skipped gap remains
     explicit.
4. On either recovery fixture, open **End season privately** and confirm it
   presents a read-only route only. Do not expect the destination to work until
   DASH-06.
5. Repeat the healthy and recovery review at desktop width and a narrow mobile
   width. Confirm no controls, evidence, or confirmation text are clipped or
   horizontally lost.

## Creator decision record

- Healthy supervision accepted: pending
- Retry rehearsal accepted: pending
- Skip rehearsal accepted: pending
- Desktop and narrow layout accepted: pending
- Runbook wording accepted: pending
- DASH-05 accepted: pending
- Notes or requested changes: pending

Acceptance closes DASH-05 only. It does not authorize DASH-06, deployment,
live Linux inspection, S01 private close, worker/model operation, publication,
or public release.
