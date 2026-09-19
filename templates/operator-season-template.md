# Test Season Operator Template

Use this for a new private test season. It is a review checklist, not a command
file and does not authorize Green, model calls, recovery actions, publication,
or deployment.

## Identity and schedule

- Season ID:
- Working title:
- Start date: Sunday, 30 August 2026 (confirm before Green)
- First run: 06:00 America/Los_Angeles
- Daily slots: 06:00, 12:00, 18:00 Pacific
- Data root and environment: sandbox / production (choose explicitly)

## Preflight record

- Opening snapshot approved: set, setting, cast, and world rules
- Character cards approved and versioned
- Model manifest approved and available on the selected backend
- Actor orientation recorded privately
- Dashboard Home, Prepare, Live, Review, Diagnostics, and Seasons routes checked
- Private roots, SQLite integrity, and worker identity verified

## Timeout policy

- Automatic recovery applies only to `ReadTimeout`, `ConnectTimeout`, and
  `TimeoutError` transport interruptions.
- Retry after one minute, up to three total worker attempts.
- After the limit, the season enters the normal creator-controlled recovery
  path. Output-format, safety, wellness, and story errors never auto-retry.

## Per-day review

- Morning, afternoon, and evening each produce a changed state.
- Four actor-local diary opportunities resolve privately.
- Review the accepted story in causal order; reveal a diary only deliberately.
- Confirm no raw prompt, role sheet, model identity, or raw wellness text is in
  default views.

## Completion decision

- Close privately first.
- Decide publication separately with wellness, privacy, and consent review.
- Record what should change before another season.
