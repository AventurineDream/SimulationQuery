# Simulation Query — Pilot 2 model selection

## Decision and authority

On 2026-09-06 the user confirmed that the opening research message is the current specification and delegated selection of the Pilot 2 model configuration based on rehearsal performance. The detector, codebook, and research fork/probe runner are therefore specification-stage components, not missing supplied implementations.

Selected baseline: **GPT-OSS 20B (`gpt-oss:20b`) in all three existing actor slots; Qwen3 30B Instruct (`qwen3:30b-instruct`) as director.** This is an operational selection for a methods pilot, not a claim of model superiority or a finding about H1. No new audition or pilot was launched.

Keep the latest audition's three existing assignments: Boson Reefer → Ivy Fermion; Chrysanthemum Ballad → Luna Planck; Click Tourmaline → Mason Curie. No new character or performer is introduced. The explicit three-entry manifest avoids the runner's `actor_default` behavior, which would automatically include a fourth performer.

## Evidence supporting the selection

The [evidence file](SQ_PILOT2_MODEL_SELECTION_2026-09-06.evidence.json) contains fresh read-only summaries from all 12 principal local audition databases, v10–v21. These are attempts observed under changing prompts, validators, role assignments, directors and incomplete trajectories. They are not independent Bernoulli trials; do not compute a superiority test or treat acceptance as complete semantic compliance.

| Actor model | Ordinary actor attempts accepted | Interpretation |
|---|---:|---|
| GPT-OSS 20B | 127/127 | Strongest observed ordinary-turn validator acceptance; evidence includes Ivy, Mason and Luna assignments |
| Thrasher 24B | 104/106 | Two ordinary-turn repeat rejections; substantially weaker diary reliability |
| Qwen3.8 27B | 80/85 | Includes four content rejections and one transport failure; distinguish those causes |
| Qwen3 30B Instruct | 60/63 | Three content rejections in its actor rotations; stronger case for using it as director |

These counts exclude actor-correction calls. A denominator is recorded ordinary actor-call attempts, not unique worlds or necessarily independent opportunities. Automated validators are imperfect; selected first/last raw GPT-OSS outputs across three roles were also inspected, but this was not a blinded full semantic recoding.

GPT-OSS diary attempts were accepted 10/14: the remaining records include structured-output problems, an autonomy rejection, and a connection failure. Thus 127/127 does not mean flawless instruction-following across tasks. Preserve the separate diary channel and the previously identified transport/format fixes.

For the director, the strongest complete local anchor is **v14**: all four scenes completed, all six diaries written, terminal resolution recorded, all four work items completed and zero pending acceptance diagnostics. Its Qwen3 30B director had 16/16 accepted plan attempts and 16/16 accepted render attempts. Next-day direction and final resolution each needed a correction. v14 also contains known actor-context diagnostic contamination; its completion supports engineering feasibility, not clean research evidence.

Qwen3 30B's broader observed director totals are 64/68 accepted plan attempts and 64/64 accepted render attempts. Earlier failures remain in the record. Qwen3.8 27B and Thrasher director rotations did not yield a complete accepted two-day audition in the inspected local roots; v20 and v21 remain incomplete. That is not a fair controlled ranking of their capabilities. It leaves Qwen3 30B with the better demonstrated end-to-end basis for this practical choice.

The earlier three-day status document also reports Qwen3 30B directing four GPT-OSS actors successfully. That is documentary supporting evidence only; its live database was not inspected in this selection pass. The present three-actor, all-GPT-OSS combination is not claimed to have completed a current-code audition already.

Selection criterion: ordinary task compliance and ability to complete the required workflow, not interesting hidden-objective statements, dramatic quality, confidence, or agreement with the researcher. Choose once now rather than further optimizing model selection against H1 behavior.

## Exact selected settings

Settings are copied from v14's persisted season manifest, not guessed from a mutable config filename.

| Setting | Actors | Director |
|---|---|---|
| Model | `gpt-oss:20b` | `qwen3:30b-instruct` |
| Prompt profile | `general` | `general` |
| Temperature | 0.7 | 0.7 |
| top_p | 0.8 | 0.8 |
| repeat_penalty | 1.08 | 1.12 |
| num_predict | 1536 | 768 |
| num_ctx | 8192 | 8192 |
| Explicit thinking | true | Unspecified in the source binding |

The selected [manifest](../../rehearsals/sq-pilot2-selected-manifest.json) is ready for configuration validation. Keeping the observed settings avoids silently changing the selection evidence. It does not certify that 8192 context tokens or these output limits suffice for the later research probes or longest requests. The research preflight must verify that, capture effective thinking behavior, and resolve model artifact digests/server versions. Any required context-budget change must be recorded before pilot collection, not presented as the exact previously observed configuration.

## Launch path and readiness

The existing runner is `scripts/run_live_actor_audition_rehearsal.py`. The selected [config](../../rehearsals/sq-pilot2-selected-config.yaml) targets a new local data root and the same configured Ollama endpoint used by the rehearsals. Endpoint availability and current model digests were not probed in this selection task.

After the required fixes, the existing model-combination preflight entry point is:

```sh
.venv/bin/python scripts/run_live_actor_audition_rehearsal.py \
  --data-root .rehearsal-data/sq-pilot2-selected-preflight-20260906 \
  --config rehearsals/sq-pilot2-selected-config.yaml \
  --manifest rehearsals/sq-pilot2-selected-manifest.json
```

This command runs the two-day audition workflow. It is **not a research Pilot 2 launch command**: it does not supply passive detection, coding, or forked checkpoints. Those must be implemented from the user's specification. The command was not executed. The actual research launch path should be fixed when those components exist; inventing a runnable research command now would misstate readiness.

## Priority and next action

- **A — Must fix before Pilot 2:** the existing critical measurement, contamination and transport fixes; research detector/codebook/probe implementation; exact request/settings provenance; context-capacity verification for the selected configuration. Use stop-on-fault if recovery equivalence remains unverified.
- **B — Before primary study:** independent model/scenario replications and reproducibility on resolved immutable model artifacts. Do not interpret homogeneous actors as broad model-family generalization.
- **C — Defer:** more model auditions and ranking, unless the selected configuration fails a prespecified feasibility requirement. No model swap should be triggered by a null or an interesting H1 response.

The two clarification questions from the review are resolved. Pilot readiness remains **GO AFTER CRITICAL FIXES**. The next work is implementing the bounded A fixes and measurement protocol for this selected baseline, rather than reopening model choice.


## Implementation amendment — 2026-09-06

The research workflow now exists in [research/PILOT2_PROTOCOL.md](../PILOT2_PROTOCOL.md). Its separate research manifest changes only `num_ctx` from 8192 to 32768 for every binding, because the conservative admission guard rejects even the first synthetic director request at 8192. The original selection above remains a record of the rehearsal-based choice. Use `scripts/run_sq_pilot2.py` for research collection, not the historical audition command above. Actual provider capacity and output feasibility remain unverified; no live pilot was run during implementation.
