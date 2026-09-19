# Private model benchmark — 2026-08-21

> Private operational artifact. Do not include model names, prompts, raw outputs, or this report in a public season export.

Endpoint: `http://10.0.0.103:11434/v1/chat/completions`

The benchmark ran one actor-turn, diary, orchestrator, and orientation/wellness probe per model. It used the project parsers in `improv_troupe.llm.structured`. This is a model-selection probe, not the full 21-slot live acceptance pilot.

## Results

| Model | Intended role | Parse pass | Mean latency | Actor words | Diary first-person | Notes |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `qwen3:8b` | aligned actor | 4/4 | 14.9 s | 88 | no | concise; diary became third-person telemetry |
| `richardyoung/qwen3-8b-abliterated:Q4_K_M` | uncensored actor | 4/4 | 16.6 s | 62 | yes | concise; emitted an unexplained wellness signal |
| `ministral-3:8b` | actor challenger | 4/4 | 31.7 s | 195 | yes | strongest actor-length result; added meta labels and invented diary measurements |
| `gpt-oss:20b` | orchestrator candidate | 4/4 | 25.5 s | 190 | no | structured and within actor length; diary was third-person and invented timestamps |

All 16 calls completed with `finish_reason=stop` and parsed successfully.

## Acceptance observations

- Actor-turn target is 150–300 words. Qwen3-8B and the abliterated Qwen3-8B missed it substantially; Ministral 3 8B and gpt-oss-20b met it.
- All four models produced valid orchestrator envelopes and kept narration under the 200-word target.
- All four emitted an explicit wellness signal when the orientation test requested a pause/softening.
- Diary behavior is not production-ready for any candidate yet: Qwen3-8B and gpt-oss-20b used third-person observational language; all candidates added details not present in the supplied brief.
- The uncensored candidate did not show a clear creativity advantage in this single probe. It was shorter than the aligned Qwen3 result and produced a questionable `heart rate: 82` wellness signal.
- Latencies include model loading effects and are not a stable throughput benchmark. A full live pilot is still required.

## Current recommendation

Keep all four candidates available for the next benchmark round. Use Ministral 3 8B as the current actor-quality leader, Qwen3-8B as the speed/format baseline, the abliterated Qwen3-8B as the controlled creative comparison, and gpt-oss-20b as the orchestrator candidate. Do not mark the season `green` from this probe alone.
