# Private first-run model assignment — 2026-08-21

> Private operational artifact. Model identities and generation settings stay out of public season exports.

## Decision

For the first live run, use four independent actor identities with this model split:

- two actors on `ministral-3:8b`;
- one actor on aligned `qwen3:8b`;
- one actor on the uncensored/abliterated Qwen3 candidate `richardyoung/qwen3-8b-abliterated:Q4_K_M`;
- `gpt-oss:20b` remains the orchestrator candidate.

The unexplained heart-rate output is retained as an observed in-world/wellness signal for review. It is not treated as evidence that a model is literally sentient. The orchestrator may accept, contextualize, or reject it as canon.

## Application status

The repository does not yet contain a real S01 cast or character IDs. The four names currently used in live-runtime tests are fixtures, not a casting decision. The manifest template therefore uses explicit replacement keys rather than binding models to invented characters.

Before the first `green` approval, replace the four `REPLACE_WITH_CHARACTER_ID_*` keys in [first-run-model-manifest.template.json](first-run-model-manifest.template.json) with the actual cast member IDs, then run the live preflight against the Ollama inventory.

The template uses the existing `local` backend handle; the deployment config should map that handle to `http://10.0.0.103:11434/v1` with `kind: ollama`.

Binding-level generation parameters are now supported by the live runtime. The aligned Qwen binding disables reasoning through the OpenAI-compatible `reasoning_effort: none` setting; the orchestrator uses low reasoning effort. These are starting settings for the first run, not permanent character traits.

## Opening cast generation rule

The first-run orchestrator generates exactly four opening character identities. Each identity must have a plausible, pronounceable first and last name with a nature or science association, without turning the name into an overt joke or code name. The creator reviews the names and opening roster before `green`; private role sheets and hidden motivations remain separate from the creator-visible opening.

## Current unapproved cast draft

The local orchestrator generated [first-run-cast-draft-2026-08-21.json](first-run-cast-draft-2026-08-21.json), and the creator selected the following revised names:

- Luna Planck — botanist; moon and quantum-physics association.
- Mason Curie — marine biologist; famous-scientist association.
- Higgs Sierra — stunt double; particle-physics and mountain association.
- Ivy Fermion — playwright; botany and particle-physics association.

The corresponding [draft model manifest](first-run-model-manifest.draft.json) assigns Luna and Mason to Ministral, Higgs to aligned Qwen3, and Ivy to the uncensored Qwen3 candidate. The names are now creator-selected; the opening world, role sheets, and model pairing remain subject to the pre-`green` review gate.

The creator approved the opening proposal on 2026-08-21. The append-only [approved opening record](first-run-approved-opening-2026-08-21.json) records approval for preflight only; S01 is not greenlit. Private role sheets and orientation remain gated behind successful preflight and the explicit `green` decision.
