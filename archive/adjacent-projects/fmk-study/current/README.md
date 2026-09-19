# FMK / Field Study — prototype

A zero-dependency static prototype for a Fuck / Marry / Kill social-comparison site.

## Run it

Open `index.html` directly, or from this folder run:

```bash
python3 -m http.server 8080
```

Then visit `http://localhost:8080`.

## What works

- Responsive landing page
- Repeated FMK rounds with mixed celebrity/demo-user trios
- Exactly-one-per-role assignment flow
- Persistent local vote counts via `localStorage`
- Seeded demo leaderboard with source filters
- Local-only profile editor with 18+ / opt-in gate
- Reset demo state
- No framework, build step, backend, account system, or external API

## Product thesis

The celebrity pool is not merely content. It is calibration. A user does not just receive an abstract score; they can see the public figures and other consenting users near them in the population distribution.

Useful metrics for a real version:

- `% fuck`, `% marry`, `% kill`
- pairwise Elo / Bradley–Terry score by role
- percentile within demographic slices
- nearest celebrity neighbors
- “polarization” / variance across raters
- short-term vs long-term desirability gap (`fuck - marry`)
- rater-cluster differences
- minimum-N confidence intervals

## Production architecture

Suggested first real stack:

- **Frontend:** Next.js + TypeScript
- **DB/Auth:** Supabase/Postgres
- **Images:** Supabase Storage or Cloudflare R2
- **Auth:** magic link / OAuth plus birthdate + consent records
- **Analytics:** PostHog or a small first-party event table
- **Moderation:** report queue + blocklist + immediate self-removal

Core tables:

- `profiles(id, kind, display_name, birthdate, bio, visibility, consented_at, status)`
- `profile_media(id, profile_id, asset_url, approved_at)`
- `rounds(id, rater_id, created_at)`
- `round_items(round_id, profile_id, slot)`
- `votes(round_id, profile_id, role)`
- `reports(id, reporter_id, profile_id, reason, status)`
- `celebrity_reference(id, name, source, rights_notes, active)`

Do **not** store the result only as a single composite score; preserve every forced-choice observation so ranking methods can change later.

## Safety / launch constraints

This concept can become abusive very quickly if anyone can upload other people. A real launch should require:

1. Adults only (18+).
2. User profiles are self-submitted and explicitly opt in to being rated.
3. A user can immediately pause/remove themselves from future rounds.
4. Never allow third-party uploads of private individuals.
5. Minimum sample thresholds before showing personal results.
6. Report / moderation / ban tooling before public growth.
7. Rate limits and anti-brigading controls.
8. Separate celebrity/public-figure ingestion with source and likeness-rights review.
9. Avoid surfacing tiny demographic slices that can deanonymize raters.
10. Clear language that results represent this site's participant pool, not objective human worth.

## Next build slice

The strongest v0.2 would be a real database plus invite-code signup, image moderation, and a Bradley–Terry ranking model. That is enough to test the actual loop without prematurely building payments, DMs, or elaborate social features.
