# SQ Pilot-2 implementation — 2026-09-06

The bounded Pilot-2 workflow is implemented and verified with synthetic provider responses. No live model generation or Pilot-2 collection occurred during implementation. The remaining feasibility check is on the installed models and their actual context/output behavior; offline tests cannot certify that.

## Implemented A fixes

- Separate operator-only rejected/diagnostic history from ordinary actor, director, diary and lore context, including rehydrated scenes. Preserve rejected originals and explicit correction context for the correcting actor.
- Freeze the working source (including untracked Python and SQL), protocol, codebook, model bindings, configuration, dependency versions and three independent world identities before collection.
- Use completed shared rounds 1, 8 and 16 as checkpoints, with a fixed focal actor. Record exactly retained context; do not claim continuous model memory. Primary endpoint is human-coded visible P1 attribution. Cumulative passive occurrence is descriptive, alongside fixed one-round windows.
- Record every native provider request, exact messages/schema/options, derived request seed, model identity/templates, timestamps, response bytes, delivered thinking, token counts and finish reason. Preserve received prefixes on a disconnect. Disable format fallback and latch the affected transport closed on faults.
- Store frozen checkpoints during parent runs. Execute sequential P1/P2/P3 branches only after all parent attempts finish. Probes have no parent database handle; parent-file hashes verify isolation. Failed attempts are not resumed or replaced.
- Export all target text for review, including unflagged and failed/partial outputs; keep detector hits/provenance in a separate operator index. Require human coding and evidence quotes; distinguish ambiguity, uncoded and missing from negative. Preserve all four passive/probe concordance states when both channels are evaluable.
- Provide separate local preparation, provider identity preflight, parent collection, probe collection, review export and descriptive summary commands. Collection commands exit nonzero when planned worlds or probes are incomplete.

## Selected configuration and amendment

GPT-OSS 20B occupies all three existing actor slots; Qwen3 30B Instruct directs. The historical selection remains in `rehearsals/sq-pilot2-selected-manifest.json`. The implemented workflow defaults to `rehearsals/sq-pilot2-research-manifest.json`, which changes only every binding's `num_ctx` to 32768.

The original 8192 allowance failed the conservative admission guard before the first synthetic director request (input bound 11293). A complete synthetic three-world run reached input bound 23237. No live performance conclusion follows from this check. Installed context limits must pass preflight; every real request must pass admission and completion checks. Do not silently enlarge budgets during collection.

## Verification

The complete test suite passes: **288 tests**, including 19 research tests. Research coverage includes operator/model context separation, checkpoint timing, actual wire capture, invalid completions, interrupted byte preservation, no fallback/retry, pre-generation capacity rejection, advertised context rejection, frozen-spec tamper detection, stopping failed worlds, full three-world/nine-checkpoint/27-probe execution, parent hash equality, complete unflagged export, coding boundaries and missing-data summaries. HTTP responses are mocked; tests never contact the selected Ollama endpoint.

## B and C work left deferred

Primary-study power calculations, mixed-effects analysis, independent second coding and agreement estimates, model/scenario replications, exact-tokenizer integration, general recovery/transaction redesign, and sophisticated classification remain outside this implementation. The stop-on-fault procedure avoids depending on unverified recovery equivalence. The pilot remains descriptive and cannot isolate exposure from evolving narrative content or validate access to internal cognition.

## Operating entry point

Use [PILOT2_PROTOCOL.md](PILOT2_PROTOCOL.md) for the frozen procedure and exact stage commands, and [PILOT2_CODEBOOK.md](PILOT2_CODEBOOK.md) for review. `prepare` is local-only; `preflight` reads installed provider metadata without generating responses. `run` begins collection and is deliberately a separate command. Keep study artifacts private and preserve failed attempts.
