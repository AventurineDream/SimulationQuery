# Porch MAGIC diary fidelity review — v01

**Date:** 2026-09-17  
**Status:** Implemented and locally verified. The fresh live validation was blocked before the
opening director call because the configured Ollama endpoint was unavailable.  
**Scope:** Add a private, provenance-preserving causal-fidelity review for diary entries.

## Contract

The diary writer still produces the original private artifact. A separate structured reviewer sees
only the named writer, the accepted scene in order, the other player-character names, and that
diary's text. It must classify the entry as:

- `ACCEPT` — no categorized fidelity findings;
- `REJECT` — at least one finding; or
- `MANUAL_REVIEW` — the evidence is genuinely ambiguous.

The required finding categories are invented events, other-character private states, event-order
issues, and causal contradictions. A malformed or unavailable review is fail-closed as
`UNAVAILABLE`.

Review output is stored as a separate private JSON artifact and an immutable domain event. The
original diary is never rewritten or deleted. When the fidelity gate is enabled, next-day direction
receives the diary body only after an explicit `ACCEPTED` review; rejected, manual, and unavailable
entries become a short withheld placeholder instead.

## Local verification

- Structured envelope tests cover valid acceptance, categorized rejection, and fail-closed
  decision/findings mismatches.
- Prompt tests verify that the reviewer receives scene and diary evidence without role sheets or
  hidden direction.
- Service tests cover private review artifacts, rejection without diary deletion, and idempotent
  replay by diary ID.
- Season-day tests cover review integration and withholding a rejected diary from strict context.
- Full suite excluding the pre-existing date-sensitive scheduled-resume fixture: **353 passed, 1
  deselected**.
- `compileall`: passed.
- trailing-whitespace scan: passed.

## Live attempt

The fresh branch
`.rehearsal-data/season-1-porch-magic-diary-v03-setback-20260917/` was started with the same
configured server pair and a forced setback target. The first director-plan call returned
`ConnectError` from `http://10.0.0.103:11434`; no actor, scene, or diary call ran. The root remains
`ARMED` with zero diary rows. This is recorded as infrastructure availability, not as a fidelity
review result.

## Decision

The review boundary is ready for live validation when the local model server is available. Do not
feed diary bodies into next-day direction until this gate has produced an explicit accepted review.
The first live follow-up should resume or replace the preserved blocked branch only after confirming
the endpoint is reachable, then compare the reviewer decisions with the earlier qualitative read
that found invented timing, new events, and other characters' private thoughts.

## Retry

On 2026-09-17, the preserved v03 branch was resumed with `--resume`. The director-plan retry again
returned `ConnectError` from `http://10.0.0.103:11434`; the endpoint health check also failed. The
run remains pre-scene: season `ARMED`, run `INTERRUPTED`, zero diaries, and zero diary-fidelity
review calls. No retry artifacts were duplicated. Live reviewer behavior remains unverified.

## Network-enabled live follow-up

After the stray manual Ollama process and failed partial download were removed, the Mac-side health
check returned HTTP 200 and the preserved v03 branch was resumed with private-network access. The
run reached the director, orchestrator, and first actor. The first Mara Bell response was rejected
by the MAGIC validator for naming a diagnosis (`sprain`/`fracture`) before the roll; its correction
was then rejected as structurally invalid. The run ended before additional actors, diaries, or
diary-fidelity reviews. This is a live model-contract failure, not a transport failure. The root
remains season `ARMED`, run `INTERRUPTED`, with zero diaries.

The three additional `ConnectError` records immediately before this attempt came from running the
Mac harness without network permission; they should not be interpreted as a renewed server outage.

## Patched resume

The live actor correction exposed a bounded compatibility case: the model returned native JSON but
placed `<MAGIC_STAT>` and `[Memory: ...]` metadata inside `text`. The parser now extracts only
those recognized fields when their JSON fields are absent, and the correction prompt explicitly
keeps them out of actor text. The targeted scene/parser tests passed **122/122**; the broader suite
passed **354**, with the pre-existing date-sensitive fixture deselected.

The network-enabled resume then completed the two-round scene with seven accepted actor turns and
one neutral interruption, wrote four private diaries, and executed four private fidelity reviews.
Coverage was complete, but `diary_fidelity_safe_for_direction` was false: Eli, Rory, and Sage were
rejected for unsupported event/order/private-state claims, while Mara's reviewer output was
unavailable because it said `ACCEPT` while also returning a non-empty finding list. The existing
fail-closed validator correctly withheld all diary bodies from future direction. The run is
mechanically complete but quality status is `HUMAN_REVIEW_REQUIRED`, not a clean pass.

Remaining live findings are actor autonomy/correction-scope drift for Sage, one diary autonomy
rejection for Eli, and the Mara reviewer decision/findings mismatch. These are separate from the
transport recovery and should be addressed in the next focused reliability pass.

## Bounded malformed-review correction

The Mara result showed that the fidelity validator was correctly fail-closed but unnecessarily
terminal. The service now records the malformed first response as rejected and permits one private,
provenance-linked correction attempt. The correction prompt requires the reviewer to preserve its
evidence, align the decision with the finding lists, avoid new story facts, and keep private material
out of the summary. A malformed or incomplete correction still records `UNAVAILABLE` and withholds
the diary body. This patch is locally tested; it has not yet been exercised against the live model.
