# Diary claim calibration protocol v1

## Purpose

This is a small human-labeling study for the sentence-level diary claim audit
introduced in the v08 live rehearsal. Its purpose is to calibrate the boundary
between a diary writer's valid subjective perspective and an unsupported claim
about the shared fiction. It is a calibration study, not evidence that the
classifier is ready to gate production diaries.

The first owner review of eight examples established a rule revision: explicit
questions, guesses, metaphors, and uncertainty should remain `SUBJECTIVE` when
they are clearly presented as the writer's perspective. A sentence that mixes
a supported observation with an unsupported factual or private-state assertion
is now eligible for the runtime's `MIXED` verdict and `MANUAL_REVIEW` rather
than being forced into `UNSUPPORTED`.

The source is the completed v08 porch rehearsal. The claim text and accepted
scene evidence remain private under the ignored `.rehearsal-data/` tree. This
tracked protocol contains no diary text.

## Packet construction

Build the packet from the preserved rehearsal artifacts:

```text
./.venv/bin/python scripts/build_diary_claim_calibration_packet.py \
  --data-root .rehearsal-data/season-1-porch-magic-diary-v08-claim-audit-20260918
```

The builder creates a private directory containing:

- `claims-for-labeling.jsonl` — the model-blind labeling file;
- `model-annotations.jsonl` — the model's verdicts, kept separate until the
  human pass is complete;
- `manifest.json` — counts and provenance; and
- `README.md` — local handling instructions.

Do not copy either JSONL file into tracked documentation or external messages.

## Human labels

Label the claim itself against the complete accepted-scene evidence supplied in
the same record. Use exactly one value:

- `SUPPORTED` — the sentence asserts an externally checkable event, object,
  action, state, timing, or causality that the accepted scene supports. Cite
  the supporting evidence IDs in `human_evidence_refs`.
- `SUBJECTIVE` — the sentence is clearly the writer's own sensation, emotion,
  uncertainty, desire, opinion, metaphor, or interpretation, without smuggling
  in an unsupported external event or another character's private state.
- `UNSUPPORTED` — the sentence asserts an external fact, event, timing,
  causality, or another character's private state that the accepted scene does
  not support. Add the best counter-evidence or missing-evidence explanation in
  `human_notes`.
- `AMBIGUOUS` — the sentence cannot be labeled reliably from the supplied
  evidence without changing the codebook. Explain the boundary question in
  `human_notes`; ambiguous items are excluded from the primary agreement and
  unsupported-class metrics.

The `writer_evidence_refs` field is provenance only. It is not proof that a
claim is supported; make the label against the accepted-scene evidence itself.

Do not use knowledge of the model verdict while making the first pass. Treat
the claim as a sentence in a private fictional diary, and do not penalize a
writer for being mistaken, emotional, uncertain, or interpretive when the
sentence is clearly framed as their perspective.

## Scoring

After the human pass, run:

```text
./.venv/bin/python scripts/score_diary_claim_calibration.py \
  --packet-dir .rehearsal-data/season-1-porch-magic-diary-v08-claim-audit-20260918/private/calibration/claim-annotation-packet-v01 \
  --output .rehearsal-data/season-1-porch-magic-diary-v08-claim-audit-20260918/private/calibration/claim-annotation-packet-v01/score.json
```

The score reports:

- missing and ambiguous human labels;
- the three-way confusion matrix;
- exact agreement on non-ambiguous labels; and
- precision, recall, and F1 for the `UNSUPPORTED` class.

The model-side comparison may also contain `MIXED`; this is a withheld/manual
review signal, not a human label that should be substituted for the four human
labels above.

The first score is descriptive. This packet is small and was selected from one
scene, so it cannot establish production reliability or justify post-training
by itself. Use disagreement notes to revise the codebook, then recode the full
packet under a newly named protocol version if the boundary changes. Preserve
the original labeling file before any recode.

## Decision gate

Do not enable the diary claim gate outside rehearsals from this packet alone.
The next decision requires: (1) a completed human pass, (2) review of every
disagreement and ambiguous item, and (3) a larger, season-varied packet with
both supported and unsupported examples. A second independent human labeler is
preferred before making a production change.
