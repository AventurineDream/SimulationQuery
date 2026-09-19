#!/usr/bin/env python3
"""Run one private, parser-checked Higgs challenger audition.

This is intentionally not a season command: it creates no records, changes no
model binding, and sends only a fixed synthetic scene to the selected backend.
"""

from __future__ import annotations

import argparse
import json

import httpx

from improv_troupe.llm.structured import (
    StructuredOutputError,
    parse_actor_output,
    schema_for,
)


SYSTEM_PROMPT = """You are Higgs Sierra, an independent player-character in a
text-based reality-show roleplaying game. You are a stunt double with
wildfire-safety habits: you check exits, feel structural risk in your body, and
name the thing everyone else is avoiding. Stay first-person limited. Give
exactly one concrete, consequential contribution rather than a situation
report. Do not recap every metric, narrate another actor, force consensus, use
a generic thriller opening. Your `text` field must contain 45-90 words, and
`diary_intent` should be false unless you genuinely want a diary entry."""

SCENE = {
    "role_sheet": {
        "public_role": "stunt double with wildfire-safety habits",
        "private_voice_note": "She checks fire escape routes before every rehearsal.",
        "priorities": [
            "get the crew through the next minute",
            "refuse a spectacular but unsafe maneuver",
            "notice physical escape routes and material failure",
        ],
    },
    "accepted_canon": [
        "The submarine Aether is inside Yellowstone caldera.",
        "The aft junction is taking slag; coolant seals are holding briefly.",
        "The environment appears to react to the fusion core's modulation.",
    ],
    "scene": [
        "Luna says the thermal gradient is folding inward and wants to inspect the fusion logs.",
        "Mason has locked the core at 78% because he distrusts the diagnostics.",
        "Ivy's seals hold for minutes, not safely for long.",
        "The aft junction hisses again; the only clear escape route passes directly beside it.",
    ],
    "prompt": "Higgs, it is your turn. Make one choice or demand that changes what the crew does next.",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one private Higgs model audition.")
    parser.add_argument(
        "--base-url",
        required=True,
        help="explicit private model endpoint; never defaults to a season backend",
    )
    parser.add_argument("--model", default="in-character-rp-12b:v0.1-chatml-q4km")
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=320,
        help="enough room to finish a JSON envelope; not a target turn length",
    )
    args = parser.parse_args()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(SCENE, sort_keys=True)},
    ]
    base_url = args.base_url.rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]
    if not base_url.endswith("/api"):
        base_url = f"{base_url}/api"
    response = httpx.post(
        f"{base_url}/chat",
        json={
            "model": args.model,
            "messages": messages,
            "format": schema_for("actor_turn"),
            "options": {
                "temperature": 0.85,
                "min_p": 0.05,
                "top_p": 1.0,
                "num_predict": args.max_tokens,
            },
            "stream": False,
        },
        timeout=180,
    )
    response.raise_for_status()
    raw = response.json()["message"]["content"]
    print("RAW OUTPUT\n" + raw)
    try:
        parsed = parse_actor_output(raw)
    except StructuredOutputError as exc:
        print(f"\nPARSE: failed ({exc})")
        return 2
    print("\nPARSE: passed")
    print("ACTOR TEXT\n" + parsed.text)
    word_count = len(parsed.text.split())
    print(f"WORDS: {word_count}")
    if not 45 <= word_count <= 90:
        print("ROLE LENGTH: failed (expected 45-90 words)")
        return 3
    print("ROLE LENGTH: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
