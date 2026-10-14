# Diary audience and launch checks

This is a prospective software change prepared on October 14, 2026. It does not
amend a frozen season's prompts, consent records, publication decisions, or research
protocol. Adopt it only with a newly approved and pinned source/prompt revision.

## Audience statement

Diaries share experiences and personal reflections with readers outside the
fictional scene. Personal voice is part of that format. Keeping a diary out of
the scene context describes access during play; it is not a promise of permanent
confidentiality or proof of permission to publish.

The shared wording is versioned as `diary-audience-v1` in
[`diary_audience.py`](../src/improv_troupe/llm/diary_audience.py). The same statement
appears in the opening orientation, every actor scene request (all prompt
profiles), and every diary request, including slot selection and correction:

> Diary entries are intended to share your experiences and personal reflections
> with readers outside the fictional scene. During scenes, diary text is withheld
> from other actors and the director. After day closure, the director may review
> it for next-day planning. Public release requires a separate review after the
> season ends, covering consent, privacy, and creator approval. You may request
> that your diary entries and attributable excerpts be withheld from publication.
> Writing an entry or agreeing to participate does not itself record publication consent.

The scene request labels this as task information outside the fictional world
and keeps it out of `ACTOR_TEXT`. The diary's personal voice and fidelity rules
remain in force. `WELLNESS_SIGNAL` can carry an out-of-world publication request;
it follows the existing private wellness handling for operator review. The
operator must honor the requested release boundary in the publication review.
This change does not implement an automatic end-to-end revocation ledger.

## Launch evidence

`LiveSceneFactory` now checks orientation before constructing model clients.
Every member of the current cast needs an `OrientationAccepted` event linking to
a completed orientation call for that season and character, with the current
diary-audience version. A missing, declined, incomplete, or unversioned briefing
blocks scene dispatch. The gate makes no model calls and does not orient an actor
automatically. Ordinary input preflight remains available before orientation.

Use the approved launch process to deliver the opening briefing before dispatch.
Archive its actual request, response, call ID, prompt version, and acceptance
event. A function in the source tree, an `ARMED` season row, or an empty consent
table does not establish what an actor actually received or agreed to.
Orientation acceptance records participation under the briefing; it does not
insert diary-publication consent into `consent_decisions`.

Historical technical rehearsal entry points explicitly use
`require_orientation=False` to retain their bounded call schedules. This is an
exception for those rehearsal tools, not a compliant season launch. Production
`improv serve` has no command-line bypass. A custom season launcher must retain
the default gate and the approved orientation step; directly constructing a
`SceneRunner` is not evidence that those launch requirements were met.

Existing seasons with older acceptance records are deliberately not upgraded by
the gate. Do not backfill events or rebrief a frozen or held season to make it
pass. A new source revision requires a separate launch decision and a fresh,
appropriately pinned season. Existing publication requests and holds still apply.

## Request provenance and verification

Changed request versions are:

| Purpose | Prompt version | Context version |
| --- | --- | --- |
| Orientation | `orientation-v2-explicit-diary-audience` | `orientation:{season}:{character}:v2` |
| Actor turn | `scene-actor-v12-explicit-diary-audience+craft` | `scene:{run}:round:{round}:v8` |
| Diary selection/write | `diary-actor-v8-explicit-audience` | `diary:{season}:day:{day}:slot:{slot}:v5` |
| Diary correction | `diary-actor-v8-explicit-audience-surgical-correction` | Same diary context version |

Offline tests cover fresh contexts with and without separate performer sheets,
all actor prompt profiles, slot deferral/write and correction requests, and the
launch gate's archived acceptance evidence. They verify what the software sends
and blocks. They do not establish how a model understands the wording, whether
it changes publication answers, or why any historical answer occurred. No live
model experiment is part of this change.
