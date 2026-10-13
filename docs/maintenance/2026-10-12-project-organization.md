# Project organization — October 12, 2026

## Scope

Prepare public repository changes in an isolated clone of GitHub's `main` at
`e9bd70bd502bf2919ea91079de1ef07252b241e8`. The pre-cleanup Forgejo checkout was
clean at the same commit. Private Drive documents and deprecated local sources
were inventoried and backed up before any source organization.

## Changes

- Clarify the public GitHub, private Drive, deprecated local, and temporary
  workspace roles; improve README and agent entry points.
- Keep established paths for source, tests, schemas, manifests, and protocols.
- Make rehearsal and deployment YAML examples portable by replacing the owner's
  absolute workstation paths and model-server address. Preserve the exact
  historical versions in the private archive. Preserve experimental settings.
- Archive sealed labels, three raw result files, and five unrelated prototype
  files before removing them from the current public tree.
- Preserve the previous operator handoff and public-source snapshot privately;
  replace the root deployment guide with a generic operating boundary.
- Add a repository consistency check and an offline GitHub Actions workflow.
- Replace 30 broken links into ignored private evidence with explicit provenance
  references. Preserve the paths without advertising unavailable public downloads.
- Stabilize the existing optional UI test by driving its timer callback explicitly;
  the previous wall-clock assumption failed on the unmodified baseline. The
  application's animation and keyboard behavior are unchanged.
- Organize all existing Drive items by purpose while preserving their IDs,
  contents, and sharing. Distinguish the two same-title launcher snapshots.
- Preserve the completed Season 1 archive, deprecated local source, original
  Drive exports, repository snapshot, and Git bundle with checksum receipts.

## Preservation

The archive contains 108,526 files; every archived file matched its source SHA-256,
and the source was rechecked after packaging. The copied SQLite database reports
integrity `ok`, 21 completed runs with 16 turns each, 21 completed work items,
seven closed days, and 28 written diaries. The root completion marker and final
log also record completion. The season row still says `RUNNING`; administrative
closure remains a separate owner decision. The runtime and evidence were not
altered by this cleanup.

Historical Git commits retain previously published files. The private Drive
plan, original parent metadata, move journal, archive manifests, and readback
receipts contain the detailed rollback record.

## Validation

The baseline suite without the optional TUI dependency passed 416 tests and
skipped one module. With that dependency installed, the baseline had 420 passing
tests and one reproducible timing-dependent UI failure. After the test repair,
the complete suite passed **421 tests** with no skips.

- Repository check: 330 files, 212 local links, and 52 JSON/YAML files passed.
- Source/script/test compilation and shell syntax checks passed.
- Plan validation, the offline scene export, schema generation, and wheel build
  passed. The wheel includes SQL migrations, CSS, and JavaScript assets.
- 93 runtime/contract files are byte-for-byte unchanged. All 28 YAML examples
  preserve their parsed experimental settings except data paths and endpoints.
- All 24 existing Drive items retain their IDs and sharing. The 21 native
  documents have identical text, and the three binary files have identical
  SHA-256 hashes after organization. Every initial uploaded backup/receipt was
  independently downloaded and matched to its local source.

The full report and rollback receipts are saved privately and referenced by the
pull request. GitHub Actions adds independent Python 3.11 and 3.14 validation.
