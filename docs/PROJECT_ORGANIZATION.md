# Project organization and storage

Updated October 12, 2026.

## Sources of truth

| Location | Owns |
| --- | --- |
| [Public GitHub repository](https://github.com/AventurineDream/SimulationQuery) | Reusable software, tests, examples, schemas, published methodology, and implementation documentation |
| Private SimulationQuery Google Drive folder | Unpublished writing, sealed annotations, raw results, complete run evidence, exact operating configurations, and handoffs |
| Deprecated local SimulationQuery folder | Preserved historical copy; retrieve current private work from Drive |
| Isolated clone or Codex cloud task | Temporary working copy for changes and validation |

The older Forgejo checkout and the public GitHub repository had the same source
commit at the start of this cleanup. Verify the remote when starting future work;
the GitHub repository is the public destination. The package and module names
remain `improv-troupe` and `improv_troupe` for compatibility.

## Public repository map

- `src/`, `tests/`, `schema/`, `pyproject.toml`: software and its contract.
- `scripts/`, `examples/`, `deploy/`: tools and portable starting points.
- `research/`: protocols, coding rules, calibration manifests, and dated
  methodological decisions. Unpublished claims and sealed label records stay
  private.
- `rehearsals/`: dated public summaries, model manifests, and portable example
  configurations. Stable filenames support existing scripts and tests.
- `benchmarks/`: public summaries and approved/example inputs. Raw result tables
  and batch receipts are preserved in Drive.
- `docs/`: documentation map, dashboard design, implementation reviews,
  maintenance records, and cloud setup.
- `design/`, `demos/`, `templates/`, `skills/`: reusable design and planning assets.
- `archive/README.md`: location policy for historical material held in Drive.

The root specification and implementation documents remain at their established
paths. Their dated contents record the software's development; they do not
describe current private server state. Start with `README.md` and `docs/README.md`.

## Private evidence

The Drive folder uses these groups:

| Folder | Contents |
| --- | --- |
| `00_Start_Here` | Current project index and source-of-truth directions |
| `01_Research` | Manuscript, diagram, calibration packet and agreement record, draft rubric, reference review |
| `02_Season_1` | Operating handoff, historical launcher/freeze drafts, completed evidence archive and file checksums |
| `03_Operations` | Cleanup plan, move journal, verification receipts, and rollback information |
| `90_Repo_Reference` | Dated read-only copies of repository documents; edit the repository originals |
| `99_Archive` | Earlier manuscripts and handoffs, deprecated local files, migrated private repository material, and pre-cleanup snapshots |

The two launcher documents previously sharing one title are distinct snapshots.
Both retain their file IDs and contents and are labeled by snapshot date. Moving
a Google Doc preserves its existing link. Read the dated document and current
index together; old draft instructions are historical evidence.

Sealed annotation records, raw CSV/JSON result tables, and the unrelated prototype
were archived with original relative paths and SHA-256 manifests before removal
from the current public tree. This cleanup does not rewrite Git history.

## Safe working procedure

1. Clone the verified public repository into an isolated workspace.
2. Inventory private Drive material by file ID. Export native documents; a synced
   `.docx` placeholder can be empty and is not a content backup.
3. Preserve originals, source hashes, existing parents, and sharing before edits.
4. Prepare a narrow change and validate it offline with the commands in `AGENTS.md`.
5. Verify Drive moves by metadata readback and compare document text before and
   after. Verify binary uploads against independently downloaded bytes.
6. Use a pull request to review public changes. Apply them to the intended source
   only after validation and the chosen review/merge decision.

Retain source receipts and private archives even when a run failed or a model is
no longer selected. Public documentation, private evidence, and deployed runtime
errata have separate provenance; cleanup does not reconcile them by overwriting.
