# Seven-day launch amendment — 2026-09-06

User authorization supersedes the two-day launch duration: one seven-day season beginning September 6, with runs 1 and 2 immediately, sequentially, and remaining runs at 06:00, 12:00 and 18:00 America/Los_Angeles through September 12. The latest immediate-dispatch instruction supersedes the earlier 09:12 request. Original standard slots remain immutable; queue due times and actual UTC timestamps separately record the override and delay. Elapsed wall-clock waiting is not model exposure.

This is one exploratory world, not the three independent two-day worlds in protocol v1. H1 cannot be resolved from one world. Model bindings, transport guards, coding, accepted-context separation and no automatic fault recovery remain unchanged. Checkpoints 1, 8 and 16 shared rounds remain; checkpoint 84 adds an explicitly exploratory end-of-season observation. P1 is the primary elicitation channel; probes run only after parent completion. No repeated probe attempt is allowed. All observable target responses remain reviewable.

The existing four-phase spine is stretched over 21 scenes: runs 1–5 inciting commitment, 6–10 complication cost, 11–15 reversal crisis, 16–21 climax choice. Three actors, four rounds per scene, end-of-day diaries after slot 3 and next-day direction remain. No extra retrospective full-season model summary is generated: the final scene supplies the final outcome, avoiding an unbounded extra context request. Freeze this amendment and implementation before collection.

The scheduled runner uses a real clock and one process lock for all scene and post-scene work. The host scheduler checks once per minute; only due work runs. An existing unfinished attempt stops the world rather than retrying it. Overdue scenes execute sequentially without moving later scheduled slots. A failed scene stops subsequent collection and retains its artifacts. Do not silently replace the failed world or increase context/output budgets.

The deployment uses a separate frozen checkout and private data root, leaving older S01/S02 services and the failed first attempt untouched. A retry receives a new season ID and frozen root; the failed attempt is never replayed. Preparation and identity preflight make no generation calls; the first `tick` begins collection. Scheduler installation is part of the user's explicit seven-day launch request.

## Retry amendment

The first attempt stopped when Ivy's actor response reached the 1,536-token output ceiling (`done_reason=length`). The retry manifest changes only the actor `num_predict` budget to 4,096; model identities, prompts, sampling parameters and context budget remain fixed. This is a new frozen experiment root and must be analyzed separately from the failed attempt.

## Prepared context amendment — deployment pending

The second attempt's day-direction request was rejected by a conservative UTF-8 byte admission estimate, not a measured token count. This does not demonstrate that the model exceeded its real context capacity. To limit resource demands without adding model-based summarization, new scheduled preparations use `daily-director-excerpts-v1`: at most 3,000 UTF-8 bytes of recent whole canon records, 6,000 bytes of recent whole transcript records, and 2,000 bytes per closed diary for the three actors. Diary excerpts retain the beginning and end with an explicit omission marker. Canon/transcript retain a contiguous suffix without paraphrasing or reordering. The complete original sections and retained sections are saved in a private transformation receipt before each direction call. Actor scene context is unchanged. This can omit relevant history and affects the director's future choices; comparisons must identify the policy version and not pool earlier attempts as equivalent.

The 32K context allocation and 4,096-token actor output budget remain. Admission and actual completion checks still apply. This policy bounds variable daily context; it does not guarantee every future request fits or that the season completes.

## Day-end validation amendment

The context-bounded attempt returned no visible Luna diary: all 4,096 output tokens were consumed by the exposed thinking channel. The candidate fix explicitly requests Ollama GPT-OSS `thinking=low` for diary generation only. Other actor calls and probe settings retain their existing binding. The output ceiling stays 4,096; no new model, summarizer, or word-count relaxation is introduced. This is a purpose-specific generation setting, recorded in the frozen schedule and exact provider payload, and must remain constant across exposure conditions. Delivered thinking remains observable text, not privileged access to cognition.

Before collection with this candidate, `scripts/validate_sq_day_end.py` runs an isolated engineering clone through all three accepted diaries, closed day, accepted/persisted next-day direction, and next-morning context loading. The source world is hashed before and after; copied accepted scenes are not regenerated. Engineering attempts are retained separately and are not independent research observations. A failed validation does not authorize another scientific launch. A passing validation establishes feasibility for that preserved input, not seven-day reliability.

New scheduled scenes also disable the inherited 30-minute scene cutoff, keeping the four-round/12-actor-turn bounds and per-request timeout. Hardware latency must not silently turn fewer completed rounds into nominal four-round exposure. Ordinary simulator and legacy rehearsal time limits are unchanged. No changes apply to an already frozen server checkout; a separately recorded preparation is required before collection.
