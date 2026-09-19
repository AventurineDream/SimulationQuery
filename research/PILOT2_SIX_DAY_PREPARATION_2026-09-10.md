# Pilot 2 six-day preparation — 2026-09-10

This is a preparation record for a possible next collection. It does not
install a scheduler, create a remote root, green a season, or start model
calls.

## Proposed calendar

The prepared profile uses the next Sunday as a candidate start date:

| Day | Date | Runs |
| --- | --- | --- |
| Sunday | 2026-09-13 | 1–3 |
| Monday | 2026-09-14 | 4–6 |
| Tuesday | 2026-09-15 | 7–9 |
| Wednesday | 2026-09-16 | 10–12 |
| Thursday | 2026-09-17 | 13–15 |
| Friday | 2026-09-18 | 16–18 |

Each day retains the three Pacific slots at 06:00, 12:00, and 18:00. There is
no Saturday slot. The candidate profile leaves all runs at their standard
times; no immediate-dispatch override is inferred from the current season's
catch-up operation.

## Frozen-shape changes

- `days=6`, `sessions_per_day=3`, `total_runs=18`.
- The next-day coordinator closes after day 6.
- The final exploratory exposure checkpoint is round 72 rather than round 84.
- The four-phase spine distributes across 18 scenes as 4 / 4 / 5 / 5 scenes.
- The current seven-day, 21-run collection remains a separate frozen world and
  must not be amended or pooled with this future profile.

The executable preparation profile is
`rehearsals/sq-pilot2-six-day-config.yaml`. A future launch still needs a
fresh experiment root, model/server identity preflight, a frozen source hash,
and an explicit owner decision about the launch date and any immediate runs.
