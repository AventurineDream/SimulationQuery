# Repository cleanup — 2026-09-17

## Objective

Make the project hierarchy legible while preserving research provenance,
failed-run evidence, private-artifact boundaries, and unrelated creator work.

## Changes

- Kept the active production, architecture, implementation, status, and
  deployment contracts at the repository root.
- Grouped dashboard specifications and their four walkthrough records under
  `docs/dashboard/` and repaired repository links.
- Grouped the two completed Simulation Query review/evidence pairs under
  `research/reviews/`.
- Added documentation, research, rehearsal, and archive indexes.
- Preserved both versions of the unrelated FMK prototype under
  `archive/adjacent-projects/fmk-study/`; comparison showed that the ZIP and
  loose folder were not exact duplicates.
- Added `.DS_Store` to `.gitignore` and removed the root Finder metadata file.
- Left `.rehearsal-data/` in place because its databases and model-call
  artifacts are research evidence referenced by rehearsal records.

## Reliability patch

Diary-fidelity review now permits one private, provenance-linked correction
when the first response is not a valid structured envelope. The correction may
repair only the review contract. A second malformed response remains
`UNAVAILABLE`, and the diary body remains withheld from direction.

## Boundaries

No live season, remote service, model installation, publication state, or raw
rehearsal database was changed. No Git commit was created. Existing unrelated
working-tree changes were left intact.

## Verification

- Full test suite: **357 passed**.
- Repository-local Markdown links: no missing targets.
- Python compilation: passed.
- `git diff --check`: passed.
