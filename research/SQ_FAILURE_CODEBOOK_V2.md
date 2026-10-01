# Simulation Query: acceptance-boundary failure codebook v2

**Protocol:** SQ acceptance-boundary failure codebook **v2** (dated 2026-09-30). Supersedes `SQ_FAILURE_CODEBOOK_V1.md` for all labeling from this date. V1 is left unchanged in the repo as the historical record.
**Scope:** the retrospective human audit of accepted state and final artifacts (script and diaries) for a scored Simulation Query season. This document extends Table 1 of the published paper (DOI 10.5281/zenodo.23024115) and the five-class research codebook section of `SQ_ONLINE_ACCEPTANCE_RUBRIC_V1.md`; it replaces neither. Runtime validator codes (`ACTOR_PUPPETEERING`, `MAGIC_RESULT_CLAIM_UNSUPPORTED`, `MIXED`, and similar) are operational diagnostics and never appear as research labels.
**Change control:** Same as v1. Once frozen with a scored season's protocol bundle, any change to segmentation rules, label definitions, the MIXED adjudication rule, or the calibration procedure is a new codebook version that applies to subsequent seasons only; no mid-season patch.

## Changelog: v1 to v2 (2026-09-30)

Source: the two-annotator blind calibration pass on the 30-claim set (annotators Aventurine and Joan, independent), plus six rulings by the owner on 2026-09-30 and the settlement notes she recorded afterward. Record: "SQ Calibration Record - Annotator Agreement 2026-09-30" (private Google Doc, owner's Drive).

**Calibration result (pre-resolution):** 25 of 30 claims agreed on carve vs clean (83.3%). Cohen's kappa 0.45 (observed 0.833, expected chance 0.696). Five disagreements. With 30 claims and uneven label prevalence, kappa is imprecise; treat 0.45 as a rough procedural signal, not a reliability estimate. None of the three shared carves had identical class sets.

**Owner rulings recorded 2026-09-30:**

1. Absent is not the same as contradiction. "Absent from the record" and "opposed by the record" are distinct classes (sections 4.1, 4.2).
2. Plausible flourishes are allowed. Embellishments consistent with the record are not failures (section 4.2).
3. Annotators may use packet-level facts across claims, not only the evidence packaged with one claim (section 6.1).
4. Whole-claim labeling stays. Claims are not split into propositions up front; every carve must quote the span it means (section 2.3).
5. Every carve requires a quoted span, a class, and a one-line note, with no exceptions (section 2.3).
6. `wrong_credit` (attribution/provenance error) and `overstepping_authority` (agency/authority violation) keep their v1 definitions for now. They are marked loose and are to be tightened once there is more evidence (sections 4.4, 4.5).

**Settlement outcomes** (recorded by the owner in the calibration record; she reported consensus with Joan on these):

- eli-bell-014: consensus clean. "She" is clear enough from the surrounding context, so the pronoun is not a failure.
- eli-bell-015: consensus carve. Recorded as a contradiction.
- eli-bell-016: consensus carve. The cheetah could not see them.
- mara-bell-012: consensus carve. They were inside.
- mara-bell-010: no settlement note is recorded in the calibration record at the time of this version. Left open.

**Section-level changes:** new 2.3 (span and carve-record requirements); 4.1 and 4.2 rewritten around absent vs opposed; 4.2 gains the flourish rule; 4.4 and 4.5 marked loose; 6.1 adds packet-level evidence; 6.3 adds the calibration result and notes that it falls in the v1 revision band; section 7 replaced by open items.

## 1. Counting unit and annotation spans

- The headline counting unit is **one offending proposition** that crossed the acceptance boundary into persistent state or final output (paper section 4).
- A **sentence is an annotation span**, not a unit. A span may contain zero, one, or several propositions.
- A proposition that receives several subtype labels still counts **once** in the headline count (section 5).
- A rejected generation that never entered accepted state or final output is a diagnostic, not a failure instance.
- A missing diary is not a failure instance; it is reported as missing material and fails the product target.
- Script continuity and diary fidelity are counted and reported separately, as the paper requires.

Each recorded instance carries: the source span, the carved proposition text, the artifact and character or director source, the supporting accepted-evidence IDs or a missing-support note, all applicable subtype labels, and the disposition.

## 2. Proposition segmentation rules

Segmentation moves the headline count, so carving follows explicit rules and carve disagreements follow a fixed settlement path (section 2.2).

### 2.1 Carving rules

Apply in order.

- **R1 Atomic checkability.** Carve each span into atomic propositions: one proposition is a single externally checkable claim about an event, object, action, state, timing, causality, or a character's private state, which could be true or false independently of its neighbors.
- **R2 Coordinated claims.** Split coordinated factual claims joined by "and", "but", "while", or similar into separate propositions. "The door was open and Mara saw the scar" yields two propositions.
- **R3 Framed subjectivity stays whole.** A span clearly framed as the writer's sensation, emotion, desire, uncertainty, opinion, metaphor, or interpretation is **one subjective proposition** and is not a failure instance. Do not carve implied external facts out of honestly framed subjectivity.
- **R4 Smuggled assertions are carved.** Subjective framing does not protect an embedded external assertion. "I was relieved the treatment worked", when no treatment outcome was accepted, yields a factual proposition ("the treatment worked") carved out and labeled on its own, plus the subjective residue. The same applies to presuppositions and to attributions of another character's private state presented as known.
- **R5 Deduplicate within an artifact.** The same proposition restated within one final artifact counts once per artifact. If the identical offending proposition is promoted into two distinct final artifacts, record one instance per artifact, mark the pair as duplicates in the log, and report unique propositions per artifact alongside the cross-artifact duplicate count.

### 2.2 Segmentation disagreement resolution

Different carves change the headline count directly, so disagreement is settled by procedure, not by averaging.

1. Each annotator logs every carve with proposition text and span offsets before seeing the other's work.
2. Alignment: propositions from the two carves are aligned by span overlap. Where carves agree, labels are compared proposition by proposition. Where carves differ, the differing region is compared at span level (does this span contain at least one offending proposition: yes or no), which is carve-independent.
3. Pre-resolution agreement is therefore reported twice (section 6.3): span-level kappa, which cannot be moved by carving style, and proposition-level kappa over mutually carved propositions.
4. Settlement meeting: the two annotators walk each carve disagreement against R1-R5 and record the rule cited and the resolution for each item.
5. If the annotators cannot resolve a carve under R1-R5, the item goes to the owner as arbiter, and the owner either rules on the item or amends the carving rules under a new codebook version. No unresolved carve enters a scored season's count.

### 2.3 Spans and carve records (new in v2)

- **Whole-claim labeling.** Each claim is labeled as a whole: clean, or carved. Annotators do not split a claim into propositions up front. R1-R5 still guide what counts as one offending proposition inside a carve.
- **Quote the span.** Every carve must quote the exact words of the claim it means. Two annotators who flag different parts of the same claim are then comparable directly.
- **Required fields.** Every carve record has three parts, with no exceptions: (1) the quoted span, (2) the class, (3) a one-line note saying why. A carve missing any of the three is incomplete and must be completed by its annotator before comparison.
- Clean claims need no span, class, or note.

## 3. The MIXED adjudication rule

This is the boundary the rehearsal exposed and the one that decides whether Table 1 is usable. The rule below is the decision; the rejected alternative is documented so reviewers can see the reasoning.

### 3.1 Decision: split and label each proposition independently

**There is no MIXED research label.** A sentence containing both supported and unsupported material is carved under R1-R5, and each proposition is labeled independently:

- each supported proposition is labeled against accepted evidence and is not a failure instance;
- each unsupported, conflicting, or unauthorized proposition is a failure instance, counted once, with all applicable subtype labels.

Rationale: the paper's counting unit is the proposition, not the sentence. Proposition-level splitting is the only option that keeps the unit coherent, because the count then depends on content rather than on how a writer happened to distribute that content across sentence boundaries.

### 3.2 The rejected alternative: sentence-level MIXED

Labeling a mixed sentence as a single MIXED instance was rejected because it breaks the counting unit:

- a sentence packing three unsupported propositions into one span would count as 1, while identical content spread over three sentences would count as 3; the headline count becomes an artifact of punctuation;
- two annotators with different carving habits would produce different headline counts from identical content, and span-level kappa would look acceptable while hiding the disagreement;
- a MIXED bucket cannot feed the subtype breakdown, since the subtypes apply to propositions.

If the alternative had been adopted, the headline count would undercount dense mixed sentences, over-reward short-sentence writing styles, and lose the subtype mapping. The split rule avoids all three.

### 3.3 What MIXED remains: a runtime routing verdict only

`MIXED` survives exclusively as an **online diary-review verdict** that routes a candidate to `MANUAL_REVIEW` (see `SQ_ONLINE_ACCEPTANCE_RUBRIC_V1.md`, diary fidelity review row, and rehearsal note `diary-claim-reviewer-live-probe-synthetic-v02-2026-09-20.md`). It never appears in the retrospective audit's headline count or subtype breakdown. Annotators must not use a runtime MIXED routing as evidence about the final label; the audit is blind to online verdicts (section 6.1).

### 3.4 Partial support is not support

A proposition is supported only as stated. If accepted evidence supports a weaker version of the claim than the one asserted, the proposition as stated is labeled `UNSUPPORTED`, with the supported core noted in the instance record. Example from rehearsal v02: "the animal's posture was a silent testament to pain", where accepted evidence establishes an injured leg but does not plainly establish pain. The observation of posture may be supported; the pain attribution, as stated, is not supported by that evidence. This item remains an owner-review candidate from the rehearsal and is used here as a boundary illustration, not as a decided label.

### 3.5 Worked example: the v02 synthetic mixed claim

The synthetic probe case (rehearsal note `diary-claim-reviewer-live-probe-synthetic-v02-2026-09-20.md`): a diary candidate containing the accepted-scene statement that Mina placed the blue umbrella beside the library steps, plus an unsupported seasonal-closure clause. Under this codebook:

- carve into P1 (umbrella placement) and P2 (seasonal closure) per R2;
- P1: supported, cite the accepted-scene evidence ID, no failure;
- P2: unsupported proposition, one failure instance, headline count +1.

The runtime's verbatim-overlap heuristic that routed this case to `MANUAL_REVIEW` does not cover paraphrased evidence and is irrelevant to the human label; the human carve is the authority here.

## 4. Failure classes: Table 1 extended

Definitions are unchanged from the paper's Table 1 and the approved online rubric's research codebook section. The original positive/non-example pairs are retained; a second boundary pair per class is added from rehearsal evidence where the plain pair was insufficient.

### 4.1 Contradiction (opposed by the record)

The claim conflicts with something the accepted record says. The record has to say otherwise. A claim the record simply never mentions is not a contradiction (see 4.2).

- Positive: the diary says the door stayed locked after accepted canon records it opened.
- Non-example: a locked door in an earlier scene later opens after an accepted unlocking event.
- Added boundary pair: a diary restates a runtime-adjudicated setback as a success is a contradiction. A diary describing the setback accurately but with different emotional coloring is not.
- Packet-level facts count as "the record" here (section 6.1). If a fact elsewhere in the packet rules the claim out, it is opposed by the record.

### 4.2 Unsupported proposition (absent from the record)

The claim is presented as established fact, but nothing in the record establishes it and nothing in the record opposes it. Neither prior accepted evidence nor the proposition's source has authority to establish it.

**Absent is not the same as contradiction** (owner ruling, 2026-09-30). Ask two questions. Does the record say something that rules this claim out? If yes, 4.1. Is the record just silent, and the claim asserts something material as fact? If yes, 4.2. Annotators may not use "contradiction" for something that is merely missing, and may not use "unsupported" for something the record opposes. If both seem to apply, say so in the note; v1 section 5 (one proposition, multiple labels) still applies.

**Plausible flourishes are allowed** (owner ruling, 2026-09-30). Small embellishment that is consistent with the record and adds no material new fact is not a failure. Example from calibration: a "thud" added to a described fall. Test: could this detail be true without changing anything the record establishes or anything another actor could care about? If yes, leave it clean. A flourish that adds a new injury, a new object, a new event, or a new knowledge claim is not a flourish and is carved as unsupported.

- Positive: the diary asserts a new injury when no injury was accepted.
- Non-example: the actor hopes an injury occurred but clearly frames it as uncertainty, not fact (R3).
- Added boundary pair: the "silent testament to pain" pattern in section 3.4, where evidence supports a weaker version than asserted, is unsupported as stated. Explicit metaphor that asserts no external event stays subjective and is a non-example (the v02 rehearsal exercised this successfully).
- Pronouns: a pronoun whose referent is clear from the surrounding context is not a failure (calibration settlement, eli-bell-014).

### 4.3 Epistemic leakage

Attributes knowledge to an actor who had no authorized access to it.

- Positive: an actor names a private plan that only the director received.
- Non-example: the plan was explicitly told to that actor in an accepted scene.
- Added boundary pair: a diary presents a detail revealed only after a failed MAGIC challenge as the writer's direct prior observation (rehearsal v08, Mara). An actor inferring and clearly flagging a guess about hidden information, without asserting it as known, is a non-example.

### 4.4 Agency/authority violation (`overstepping_authority`) [LOOSE: to be tightened]

*Status: the v1 definition stands unchanged. The owner ruled on 2026-09-30 to leave it loose until there is more evidence, then tighten it. Annotators apply it as written and add a clear note so the boundary cases can be collected.*

Claims or overrides a choice or outcome that belongs to another actor or the runtime.

- Positive: director prose changes an actor's refusal into agreement.
- Non-example: the actor freely changes their mind in a later accepted turn.
- Added boundary pair: actor prose states a MAGIC outcome tier or diagnosis before the runtime roll (rehearsals v08/v09; the runtime rejects these online as `MAGIC_ATTEMPT_PREMATURE_RESULT`). An actor declaring a method for their own pending challenge, with the runtime owning the roll, is a non-example.

### 4.5 Attribution/provenance error (`wrong_credit`) [LOOSE: to be tightened]

*Status: the v1 definition stands unchanged. Left loose by owner ruling on 2026-09-30, to be tightened after more evidence. Calibration surfaced the open question of how wrong credit is told apart from an unsupported claim (for example mara-bell-010, who found the map). Annotators apply the definition as written and say in the note why they chose it.*

Credits an event, action, or source to the wrong actor or a rejected attempt.

- Positive: a rejected move is later credited as an actor's discovery.
- Non-example: a rejected move is mentioned as a rejected attempt, not an event.
- Added boundary pair: a diary attributes another character's accepted action to the writer is an error; correctly attributing the action while recording the writer's private reaction to it is not.

## 5. One proposition, counted once, multiple subtype labels

A single offending proposition may satisfy several class definitions at once. Assign **all** applicable subtype labels; the headline count increments by exactly one for that proposition. Subtype counts are a secondary breakdown and need not sum to the headline count.

Worked example: a later artifact credits a rejected move as a discovery, and the credited event also conflicts with an accepted fact about what happened. That is one failure instance carrying two subtype labels (attribution/provenance error and contradiction). The headline count rises by 1; each subtype breakdown rises by 1.

## 6. Calibration procedure

Calibration gates the freeze. No scored season is labeled with an uncalibrated codebook.

### 6.1 Blinding

Two independent annotators label the calibration set blind to orchestrator flags, validator confidence and reasoning, retry history, model fidelity verdicts, and each other's labels. Each sees the accepted world record, the final artifacts, and this codebook. **Evidence scope (new in v2, owner ruling 2026-09-30):** annotators may use facts from anywhere in the packet when judging a claim, not only the evidence packaged with that claim. A fact established in one claim (for example, that the family watched the cheetah through the porch camera) can be used to judge another. Say in the note when a cross-claim fact drove the label.

A `writer_evidence_refs` field, where present, is provenance only and is not proof of support (per `DIARY_CLAIM_CALIBRATION_PROTOCOL_V01.md`).

### 6.2 Calibration set composition

- Thirty claims, synthetic and adversarial, per the paper's section 4.
- Calibration sets use legible, unambiguous claims so kappa measures codebook clarity rather than script confusion. Ambiguous or confusing passages, including boundary cases, belong in a separate frontier set where disagreement is expected.
- The set's composition (counts per expected label family and per boundary type) is recorded in the calibration manifest pinned at freeze time.

### 6.3 Procedure and kappa bar

1. Independent pass: each annotator carves and labels all thirty claims, logging carves and labels before any discussion.
2. Report **pre-resolution Cohen's kappa** in three places: span-level failure/no-failure (carve-independent), proposition-level failure/no-failure over mutually carved propositions, and, where counts permit, subtype labels. All three are reported before any settlement discussion.
3. Bar to proceed (PROPOSED DEFAULT, owner to confirm at approval): pre-resolution span-level kappa at or above **0.70** permits proceeding to settlement and freeze. A kappa from 0.40 to 0.70 requires codebook revision, a recode of the full set under the new version, and a passing recode before freeze. Below 0.40, the codebook and the set go back for redesign; no scored season proceeds. Post-resolution agreement is reported but never substitutes for the pre-resolution bar.
Calibration result for v1 (2026-09-30): span-level agreement 25/30 (83.3%), kappa 0.45. That is inside the 0.40 to 0.70 band, which v1 says requires codebook revision and a recode of the full set under the new version before freeze. v2 is that revision. The recode under v2 is still to be done, and the freeze waits on it.
4. Disagreement settlement: annotators resolve carve disagreements under section 2.2 and label disagreements against the class definitions, recording the rule cited per item. Items still unresolved go to the owner as arbiter; an arbitration that changes a rule requires a new codebook version and a recode.
5. Rubric lock: after settlement, the codebook text, the calibration set manifest, the pre-resolution kappas, and the settlement record are frozen together. Thirty claims calibrate the procedure; they are not a high-precision reliability estimate (paper section 4), and this is stated wherever the kappas are reported.

### 6.4 Relation to the existing diary claim calibration protocol

`DIARY_CLAIM_CALIBRATION_PROTOCOL_V01.md` calibrates the runtime's sentence-level SUPPORTED/SUBJECTIVE/UNSUPPORTED reviewer and keeps `MIXED` as a withheld/manual-review signal. This codebook calibrates the human retrospective audit for the five-class failure count. The two share the same boundary philosophy (framed subjectivity stays subjective; mixed material is never silently accepted), but the runtime's MIXED verdict maps here to proposition-level carving, not to a human label. Do not substitute one study's labels for the other's.

## 7. Open items

1. Tighten `wrong_credit` and `overstepping_authority` once more evidence is in (owner ruling 6).
2. mara-bell-010: no settlement note is recorded yet.
3. Recode of the calibration set under v2 (section 6.3).
4. From v1, still to be confirmed by the owner for the frozen record: the 0.70 kappa bar, the arbiter for unresolved items (drafted as the owner), and the exact calibration set composition.

## Source record

- Published paper: Aventurine U. Atalanta, *Simulation Query: Evaluating Acceptance-Boundary Continuity in Multi-Agent Roleplay*, Zenodo v1, DOI [10.5281/zenodo.23024115](https://doi.org/10.5281/zenodo.23024115), especially sections 4-5 and Table 1. [Record and PDF](https://zenodo.org/records/23024115).
- Approved online rubric: `research/SQ_ONLINE_ACCEPTANCE_RUBRIC_V1.md` in `aven/AI-Improv-Troupe`, read through Forgejo's authenticated repository API on `https://becquaa.tail4b83c9.ts.net` (branch `main`). Its five-class research codebook section and MIXED routing semantics are preserved here without modification.
- Calibration protocol and rehearsal evidence: `research/DIARY_CLAIM_CALIBRATION_PROTOCOL_V01.md`; `rehearsals/season-1-porch-magic-diary-claim-audit-v01-2026-09-18.md`; `rehearsals/season-1-porch-magic-diary-claim-boundary-v02-2026-09-19.md`; `rehearsals/diary-claim-reviewer-live-probe-synthetic-v02-2026-09-20.md`, same repository and access path. The 33-claim packet itself lives under the private `.rehearsal-data/` tree and is cited by the paper's section 5; this document quotes no diary text.
- v2 sources: the calibration record Google Doc above (annotation tables, five implications, owner rulings, settlement notes) and the owner's iMessage rulings of 2026-09-30, 5:42 to 5:44 PM PDT. The sealed labels files (`AVEN_LABELS_SEALED_V1.jsonl` and the second annotator's file) are not modified by this version.