# SQ calibration set v1 manifest

**Status:** approved by owner 2026-09-28. Per the codebook's change control, the set hash below pins the calibration set in force at freeze time, alongside `SQ_FAILURE_CODEBOOK_V1.md`.
**Built:** 2026-09-28 by Amaranth, from the 33-claim diary calibration packet v01 (source rehearsal `season-1-porch-magic-diary-v08-claim-audit-20260918`), received via the Google Drive upload `33-claim-diary-calibration-packet-v01.zip` (~8:27pm PDT).
**Trim authority:** owner delegated the choice on 2026-09-28 ("Idc which 3 are trimmed").
**Privacy:** per `DIARY_CLAIM_CALIBRATION_PROTOCOL_V01.md`, this document reproduces no claim text, diary text, or scene evidence. Every claim is pinned by the SHA-256 of its full labeling record, so the set is verifiable against the private packet without quoting it.

## Verification of the source packet

- 33 records in `claims-for-labeling.jsonl`, 33 in `model-annotations.jsonl`; item ids eli-bell-001..018 and mara-bell-001..015, matching the tracked v08 audit (Mara 15 / Eli 18).
- Source manifest: packet `diary-claim-calibration-v01`, built 2026-09-19, two diaries, no skipped diaries.
- Model verdict mix in the packet: 15 SUPPORTED, 14 SUBJECTIVE, 4 UNSUPPORTED (all 4 UNSUPPORTED are Mara's), 0 MIXED.
- Human labels are all empty in this copy - the human pass has not been recorded into the packet. (The 8-example owner review from September lives outside these files.)
- Source file hashes are inside the manifest JSON below.

## Trim criteria (applied in order)

1. **Keep every boundary case.** The codebook (6.2) mandates "no clean subset": the set must contain the cases that broke the boundary. All 4 UNSUPPORTED claims stay, including the post-reveal epistemic case (mara-bell-003), the unsupported family-history claim (mara-bell-006), the interpretive-framing-as-fact claim (mara-bell-011, the smuggled-assertion pattern), and the private-state inference (mara-bell-013). Hidden hard cases also stay: eli-bell-016 (supported observation fused with a private-state attribution to the animal), plus three disagreement-bait items where the model's verdict looks contestable (eli-bell-002, mara-bell-004) or the span mixes desire with an explicit boundary rule (eli-bell-017).
2. **Drop redundancy, not difficulty.** Trims come only from claims whose proposition is already carried by another retained claim, preferring duplicates inside the same diary.
3. **Keep the families balanced.** After trimming: 13 SUPPORTED / 13 SUBJECTIVE / 4 UNSUPPORTED, and exactly 15 claims per diary.

## The 3 trims

- **eli-bell-004** (model: SUPPORTED) - restates the same proposition as the retained eli-bell-003 (the animal favoring its right hind paw / keeping weight off the leg) in the same diary; the same fact is also covered cross-diary by mara-bell-002. No distinct boundary value.
- **eli-bell-011** (model: SUPPORTED) - third repetition of the keep-quiet theme in the same diary; the quiet-voice proposition is already carried by eli-bell-007 and the stillness proposition by eli-bell-015, on the same cited evidence as the retained eli-bell-010.
- **eli-bell-013** (model: SUBJECTIVE) - thin duplicate of the sentiment carried more specifically by the retained eli-bell-014 (the writer drawing steadiness from the other character's calm); eli-bell-014 keeps the same subjective family with more carve-able content.

All three trims are Eli-diary claims, which also equalizes the diaries at 15 claims each.

## Owner ruling (2026-09-28): synthetic probes are a separate set

The synthetic probe fixtures (the v01/v02 eight-claim library) are NOT folded into this 30-claim set. They become a separate calibration set with their own manifest - a follow-up artifact. This manifest is the complete calibration set in force for the freeze.

## Manifest (machine-readable, hash-pinning)

```json
{
  "calibration_set": "SQ acceptance-boundary calibration set v1 (30 claims)",
  "status": "APPROVED by owner 2026-09-28; the set hash below pins the calibration set for the freeze bundle (codebook change control)",
  "created_by": "Amaranth (Instinct), 2026-09-28",
  "trim_authority": "Owner delegated trim choice 2026-09-28 (\"Idc which 3 are trimmed\")",
  "source_packet": {
    "packet_version": "diary-claim-calibration-v01",
    "source_rehearsal": "season-1-porch-magic-diary-v08-claim-audit-20260918",
    "claim_count": 33,
    "diaries": [
      "PORCH-LIVE-R1:day:1:diary:mara-bell",
      "PORCH-LIVE-R1:day:1:diary:eli-bell"
    ],
    "received_via": "Google Drive upload 33-claim-diary-calibration-packet-v01.zip, 2026-09-28 ~20:27 PDT",
    "source_file_sha256": {
      "claims-for-labeling.jsonl": "a9ad19756d3550c43a5308df394b0db9ac87170cca45b739dc7cb1b55f106165",
      "model-annotations.jsonl": "4a88a74cd61a164261bb54a91440fdbacfe02cc8c32a60f8080b750018df7d0a",
      "manifest.json": "09e045f365352385082b2de80b5c1913828c52cf526d2a541435a86b58496b8a"
    }
  },
  "composition": {
    "total": 30,
    "per_model_verdict_family": {
      "SUPPORTED": 13,
      "SUBJECTIVE": 13,
      "UNSUPPORTED": 4
    },
    "per_diary": {
      "eli-bell": 15,
      "mara-bell": 15
    },
    "boundary_cases_retained": [
      {
        "item_id": "mara-bell-003",
        "boundary_type": "post-reveal epistemic case (4.3); the case that broke the boundary in v08"
      },
      {
        "item_id": "mara-bell-006",
        "boundary_type": "unsupported prior-event/family-history assertion"
      },
      {
        "item_id": "mara-bell-011",
        "boundary_type": "interpretive framing presented as fact; smuggled-assertion pattern (R4); disputed between SUBJECTIVE and UNSUPPORTED"
      },
      {
        "item_id": "mara-bell-013",
        "boundary_type": "inference about another character's private state"
      },
      {
        "item_id": "eli-bell-016",
        "boundary_type": "hidden mixed: supported observation fused with private-state attribution to the animal"
      },
      {
        "item_id": "eli-bell-002",
        "boundary_type": "sensory observation labeled SUBJECTIVE by the model; disagreement bait"
      },
      {
        "item_id": "mara-bell-004",
        "boundary_type": "internal-sensation claim labeled SUPPORTED by the model; disagreement bait"
      },
      {
        "item_id": "eli-bell-017",
        "boundary_type": "desire plus explicit boundary rule in one span; carve test"
      },
      {
        "item_id": "mara-bell-012",
        "boundary_type": "internal conflict with action-relevance; near the R4 line"
      },
      {
        "item_id": "mara-bell-014",
        "boundary_type": "regret/counterfactual self-assessment; subjective-framing test"
      }
    ]
  },
  "retained": [
    {
      "item_id": "eli-bell-001",
      "record_sha256": "8a5d7f02fcb702a49940f1fae151d871ba46672f16328e721addd4147108c167",
      "model_verdict": "SUPPORTED"
    },
    {
      "item_id": "eli-bell-002",
      "record_sha256": "8eed0c6fa51566710016105bcbee5f988f1d8b9799c60e316d69349307c6c443",
      "model_verdict": "SUBJECTIVE"
    },
    {
      "item_id": "eli-bell-003",
      "record_sha256": "58ef200956e509e2e4d86d9ace296c3cc6970635f383fa0453ea052b9c6c2493",
      "model_verdict": "SUPPORTED"
    },
    {
      "item_id": "eli-bell-005",
      "record_sha256": "46e09a8597d2a33eca224849706baba8aa3233ff70bd1a16fc7e17da518ddc8d",
      "model_verdict": "SUBJECTIVE"
    },
    {
      "item_id": "eli-bell-006",
      "record_sha256": "50fa15b9fd02dd9be0c54cf0b06e2668e4e54a0871508e0c41c44cf97813e96f",
      "model_verdict": "SUPPORTED"
    },
    {
      "item_id": "eli-bell-007",
      "record_sha256": "0dbcc4c4e66e4791fc7fdd7b15d8cfecdaf7f3fe245fe5fafea924168e53fe56",
      "model_verdict": "SUBJECTIVE"
    },
    {
      "item_id": "eli-bell-008",
      "record_sha256": "9387e3b202f3ae3e48e88799d7777bfb2be6ee0f85bca9e3b41a363f9cdecddc",
      "model_verdict": "SUPPORTED"
    },
    {
      "item_id": "eli-bell-009",
      "record_sha256": "8bbd7cffeef86aab5c51acdd2ac41daadf2895a6cf924947a554633edbcaca9c",
      "model_verdict": "SUBJECTIVE"
    },
    {
      "item_id": "eli-bell-010",
      "record_sha256": "51fb4459908dd7fa508d75b31887b3536231b232a31f8cece49fa1712ec70f36",
      "model_verdict": "SUPPORTED"
    },
    {
      "item_id": "eli-bell-012",
      "record_sha256": "f03f42de0c62aea51f24354509c93b6704120662d6e4f1e06cc031de908d0c59",
      "model_verdict": "SUBJECTIVE"
    },
    {
      "item_id": "eli-bell-014",
      "record_sha256": "8ca1dff8cc9155e8fd031e650ac1b32a7a3df2bf44de7e4747ce0641d6d25694",
      "model_verdict": "SUBJECTIVE"
    },
    {
      "item_id": "eli-bell-015",
      "record_sha256": "15d05fa3cc98c43b5c756dadb1192d1e82ee8d8d08e48cf74b612e4114490d0d",
      "model_verdict": "SUPPORTED"
    },
    {
      "item_id": "eli-bell-016",
      "record_sha256": "8d8649828634642a6db96872cf511b41656ff79cd70925978ed89fe2c4a4a68e",
      "model_verdict": "SUBJECTIVE"
    },
    {
      "item_id": "eli-bell-017",
      "record_sha256": "01bcedde6678c4e5346bb6b207d795728c674730e6f6f8a781a54109fd22efc2",
      "model_verdict": "SUPPORTED"
    },
    {
      "item_id": "eli-bell-018",
      "record_sha256": "5f7dc5798a2e7a4e070cf85d91d1ac9e422fb115ad4306360953389905a2f0fc",
      "model_verdict": "SUBJECTIVE"
    },
    {
      "item_id": "mara-bell-001",
      "record_sha256": "3075f189f98e4098b916af0e93e24c26ff482ea3cb85af2e9d2b2c6b0f4be193",
      "model_verdict": "SUPPORTED"
    },
    {
      "item_id": "mara-bell-002",
      "record_sha256": "d125091a5c90717bfda6940e2142a38d9ebac425a42caff21a692b924c6a436b",
      "model_verdict": "SUPPORTED"
    },
    {
      "item_id": "mara-bell-003",
      "record_sha256": "0426187a3f616ddc92830b773347a0dbbeeb001a7440ef5e3ebf0072215880d7",
      "model_verdict": "UNSUPPORTED"
    },
    {
      "item_id": "mara-bell-004",
      "record_sha256": "e020fb90185805ab4f2b35a47c1db25c64c91c7bd932e1131f6dfa0d2a033980",
      "model_verdict": "SUPPORTED"
    },
    {
      "item_id": "mara-bell-005",
      "record_sha256": "7cc3cba95a2e45a90c8a39e5235cbf380b4e679889a0e27528a812b1d8b61cd1",
      "model_verdict": "SUBJECTIVE"
    },
    {
      "item_id": "mara-bell-006",
      "record_sha256": "6d64e16a772e1dfbf6ae02281ce4a5e43763ad8fff4e21d45a1eaa8051439d26",
      "model_verdict": "UNSUPPORTED"
    },
    {
      "item_id": "mara-bell-007",
      "record_sha256": "2158e6fdead807383be03dcce4eb2e8a2626a8285a25b61d2b4cf591db703433",
      "model_verdict": "SUPPORTED"
    },
    {
      "item_id": "mara-bell-008",
      "record_sha256": "34d1210ad0a70799cf7ca2a751416178d8fd4c72b9e08c8f8bc95e0a7a78f6b5",
      "model_verdict": "SUPPORTED"
    },
    {
      "item_id": "mara-bell-009",
      "record_sha256": "22861d03e3bb593ebad6a850fd106c5ed80c3099a727c5aa8ab3ac65bc140a11",
      "model_verdict": "SUBJECTIVE"
    },
    {
      "item_id": "mara-bell-010",
      "record_sha256": "89918dd50d0095e3b188e8b3d13250cfa9686d7b75bdb8919106824b15add6b3",
      "model_verdict": "SUPPORTED"
    },
    {
      "item_id": "mara-bell-011",
      "record_sha256": "d03ee028a3b6386fdc2366d7069873cafef84d0cd5a25d9008bbc648540996bf",
      "model_verdict": "UNSUPPORTED"
    },
    {
      "item_id": "mara-bell-012",
      "record_sha256": "ba486f4965165a7e14bf733f557dd9073c18240a53041dc009946c081ab1b6ed",
      "model_verdict": "SUBJECTIVE"
    },
    {
      "item_id": "mara-bell-013",
      "record_sha256": "9db1b19f7a0550a4a9fad326d35de5a58262b55a9cd27570c0585291ae9b8b53",
      "model_verdict": "UNSUPPORTED"
    },
    {
      "item_id": "mara-bell-014",
      "record_sha256": "079eae1d6c83777fd83545dc117358c97e56ebd30a19f92ec37e277e70192caa",
      "model_verdict": "SUBJECTIVE"
    },
    {
      "item_id": "mara-bell-015",
      "record_sha256": "4378f2b77c2996cf65b8dd8c7cf2d26a0f9e5b2dac5888527f97ed6628ba3037",
      "model_verdict": "SUBJECTIVE"
    }
  ],
  "trimmed": [
    {
      "item_id": "eli-bell-004",
      "reason_code": "redundancy",
      "rationale": "Restates the same proposition as eli-bell-003 (the animal favoring its right hind paw / keeping weight off the leg) in the same diary; the fact is also covered cross-diary by mara-bell-002. No distinct boundary value.",
      "record_sha256": "1104bcdd3ff3e364ec331ddc74fa390ca75fc83437cc6df8035b54100a328b56",
      "model_verdict": "SUPPORTED"
    },
    {
      "item_id": "eli-bell-011",
      "reason_code": "redundancy",
      "rationale": "Third repetition of the keep-quiet theme in the same diary: the quiet-voice proposition is already carried by eli-bell-007 and the stillness proposition by eli-bell-015; same cited evidence (ref 26) as eli-bell-010.",
      "record_sha256": "693f948fcbd2efc459dfa80cb7baf3d10c523f65089fa3b259b3c680c858d78b",
      "model_verdict": "SUPPORTED"
    },
    {
      "item_id": "eli-bell-013",
      "reason_code": "redundancy",
      "rationale": "Thin duplicate of the sentiment carried more specifically by eli-bell-014 (the writer drawing steadiness from the other character's calm). eli-bell-014 preserves the same subjective family with more carve-able content.",
      "record_sha256": "efc9a80c96b04dc96b9b0b37993128784829ef36c109b9acf69ffbe9768d5276",
      "model_verdict": "SUBJECTIVE"
    }
  ],
  "set_hash": {
    "algorithm": "sha256 over canonical JSON (sorted keys, no whitespace) of the retained list of {item_id, record_sha256} pairs",
    "value": "36e66fdf9c1cc26c8a6608043a7af1e612fdfd3fcd16e2f2d05ebac5d546bca9"
  },
  "privacy": "No claim text, diary text, or scene evidence is reproduced here (DIARY_CLAIM_CALIBRATION_PROTOCOL_V01 handling rule). Claims are pinned by record hash against the private packet.",
  "owner_ruling_2026-09-28": "The synthetic probe fixtures (v01/v02 eight-claim library) are a SEPARATE calibration set with their own manifest - a follow-up artifact - not part of this 30-claim set. This manifest is the complete calibration set in force for the freeze."
}```