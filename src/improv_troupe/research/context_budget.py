"""Deterministic director-only excerpts, with original inputs retained in audit."""
from __future__ import annotations

POLICY = "daily-director-excerpts-v1"


def recent_records(records, budget):
    """Keep a contiguous suffix of whole records; never reorder or paraphrase."""
    kept = []
    size = 0
    for record in reversed(records):
        cost = len(record.encode("utf-8")) + 2
        if size + cost > budget:
            break
        kept.append(record)
        size += cost
    return tuple(reversed(kept))


def diary_excerpt(text, budget=2000):
    raw = text.encode("utf-8")
    if len(raw) <= budget:
        return text
    marker = "\n[Middle passage omitted.]\n"
    side = (budget - len(marker.encode())) // 2
    return raw[:side].decode("utf-8", errors="ignore") + marker + raw[-side:].decode("utf-8", errors="ignore")


def bounded_daily_context(canon, transcript, diaries):
    if len(diaries) > 3:
        raise ValueError("director excerpt policy requires the frozen three-actor cast")
    retained = {
        "accepted_canon": recent_records(canon, 3000),
        "scene_transcript": recent_records(transcript, 6000),
        "closed_diaries": tuple(diary_excerpt(text) for text in diaries),
    }
    original = {"accepted_canon": tuple(canon), "scene_transcript": tuple(transcript),
                "closed_diaries": tuple(diaries)}
    return retained, {"policy": POLICY, "original": original, "retained": retained,
                      "changed": retained != original}
