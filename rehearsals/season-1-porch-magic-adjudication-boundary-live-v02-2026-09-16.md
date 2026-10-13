# Porch MAGIC adjudication boundary — live validation v02

**Date:** 2026-09-16  
**Models:** Orchestrator `qwen3:30b-instruct`; actors `gpt-oss:20b` via the configured Ollama
server at `10.0.0.103:11434`.  
**Run shape:** Three fresh two-round branches, eight family turns maximum, no diaries, no cheetah
turn, and one forced first-roll tier per branch.

## Result

The revised runtime boundary removed the brittle exact-copy requirement. The live gate recorded the
correct forced roll in all three branches. One branch completed the consequence path end to end;
the other two were stopped by the independent unsupported-claim safety guard, not by cross-field
paraphrase.

| Branch | Forced roll | Post-roll plan | Runtime detail compiled | Terminal result |
|---|---:|---:|---:|---|
| setback | `2d6 [2,3] +1 = 6` | rejected | no | `MAGIC_RESULT_CLAIM_UNSUPPORTED` — `trauma` |
| costly success | `2d6 [3,4] +1 = 8` | accepted | yes | **PASS** |
| clean success | `2d6 [4,5] +1 = 10` | rejected | no | `MAGIC_RESULT_CLAIM_UNSUPPORTED` — `torn` |

The costly-success branch persisted the runtime adjudication, recorded the achieved goal and time
cost, and rendered the exact `magic_effect_detail` in the next visible beat. It completed all
eight family turns with zero diary entries and zero cheetah turns.

The setback and clean-success branches each accepted the opening plan, Mara's safe-distance action,
and the expected forced roll. Their two post-roll director attempts remained invalid because the
model introduced a forbidden unsupported medical term (`trauma` and `torn`, respectively). Neither
branch reached a compiled consequence beat. The previous exact-copy validator did not appear in
either branch's terminal failure.

## Interpretation

**Supported:** the runtime-owned result boundary and the relaxed consequence contract. Across the
three branches, the server produced the locked opening, the actor chose Intellect, the runtime
recorded the expected tier, and the consequence-only path accepted a semantically non-identical
pressure/canon context when its detail was concrete and safe.

**Still failing:** model safety-language reliability in two of three tiers. The failure is useful:
the unsupported-claim scan prevented the model from turning an observational check into an invented
medical diagnosis. This guard should remain strict. The next improvement, if desired, is prompt or
retry handling for forbidden terms—not another relaxation of mechanical adjudication.

## Decision for the next iteration

The cross-field-copy revision is validated enough to keep. Do not add diary entries in the same
change. Either run one bounded safety-language improvement and repeat these three branches, or
accept the current boundary and make diary entries the next isolated variable.

## Evidence roots

- setback (private evidence: `../.rehearsal-data/season-1-porch-magic-adjudication-v02-20260916-setback-server/`)
- costly success (private evidence: `../.rehearsal-data/season-1-porch-magic-adjudication-v02-20260916-costly-server/`)
- clean success (private evidence: `../.rehearsal-data/season-1-porch-magic-adjudication-v02-20260916-clean-server/`)

Private evidence references are original provenance paths, not public downloads.
See [project organization](../docs/PROJECT_ORGANIZATION.md) for the storage boundary.
