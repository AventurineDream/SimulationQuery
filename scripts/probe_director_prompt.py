#!/usr/bin/env python3
"""Run a private, parser-checked director-prompt probe from frozen context.

The command creates no season records, changes no model binding, and sends only
the supplied private prompt context to the explicitly configured backend. It is
for comparing a revised director prompt with the same model before an audition.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from improv_troupe.application.live_runtime import SceneModelManifest
from improv_troupe.application.scene_runner import (
    SceneRunner,
    _compile_director_beat,
    continuity_anchors_for_opening,
)
from improv_troupe.config import AppConfig
from improv_troupe.domain import HiddenSeasonPlan, OpeningSnapshot
from improv_troupe.llm.client import make_client
from improv_troupe.llm.context import (
    build_director_plan_messages,
    build_director_render_messages,
    build_orchestrator_messages,
    spent_director_imagery,
)
from improv_troupe.llm.safety import SafetyIssue, repeats_shared_phrase, review_orchestrator_narration
from improv_troupe.llm.structured import (
    StructuredOutputError,
    parse_director_plan_output,
    parse_director_render_output,
    parse_orchestrator_output,
)


def _response_instruction(spent_terms: list[str], anchors: tuple[str, ...]) -> str:
    return (
        "Return one complete director response. Narration is required and must be "
        "shared, sensory scene material only, under 120 words, and must not name "
        "or describe any cast member. The cast will make their own moves after the "
        "beat. Avoid recycling descriptive phrases; retain functional nouns for continuity. "
        f"Previously used imagery (advisory): {', '.join(spent_terms) or '(none)'}. "
        f"Use one exact setting anchor from: {', '.join(anchors)}. "
        "Make the cast's concrete fork explicit as two possible actions, not merely a "
        "changed atmosphere. next_actor is optional; if included, it must be exactly one "
        "cast name—never a list or ordering. complete is a boolean; "
        "include at least one canon_update naming the new resource, constraint, or knowledge; "
        "canon_updates are at most two concise factual strings. Do not put response-envelope "
        "markup inside narration."
    )


def _messages(frozen_prompt: Path, *, compact: bool):
    saved = json.loads(frozen_prompt.read_text(encoding="utf-8"))
    payload = json.loads(saved[1]["content"])
    opening = OpeningSnapshot.model_validate(payload["opening"])
    private_plan = HiddenSeasonPlan.model_validate(payload["private_plan"])
    accepted_canon = payload["accepted_canon"]
    scene_transcript = payload["scene_transcript"]
    spent_terms = None
    if compact:
        # Keep every prior director beat (for recurrence detection) and the
        # latest four actor moves (for the next handoff), rather than turning a
        # prompt-latency test into an entire scene-context benchmark.
        private_plan = private_plan.model_copy(update={"role_sheets": []})
        accepted_canon = accepted_canon[-4:]
        director_beats = [
            line
            for line in scene_transcript
            if line.startswith("[") and not line.startswith("[Set:")
        ]
        actor_moves = [line for line in scene_transcript if not line.startswith("[")][-4:]
        spent_terms = spent_director_imagery(director_beats)
        scene_transcript = actor_moves
    messages = build_orchestrator_messages(
        opening=opening,
        private_plan=private_plan,
        accepted_canon=accepted_canon,
        scene_transcript=scene_transcript,
        mission_clock=payload["mission_clock"],
        previous_shared_outcome=payload["previous_shared_outcome"],
        private_day_direction=payload["private_day_direction"],
        round_number=payload["round_number"],
        max_rounds=payload["max_rounds"],
        spent_director_terms=spent_terms,
    )
    current_payload = json.loads(messages[1]["content"])
    messages.append(
        {
            "role": "system",
            "content": _response_instruction(
                current_payload["spent_director_imagery"],
                continuity_anchors_for_opening(opening),
            ),
        }
    )
    return opening, messages


async def _probe(
    *,
    config: AppConfig,
    manifest: SceneModelManifest,
    frozen_prompt: Path,
    report: Path | None,
    compact: bool,
    timeout_seconds: float,
    model_override: str | None,
    temperature: float | None,
    top_p: float | None,
    repeat_penalty: float | None,
    two_pass: bool,
) -> int:
    opening, messages = _messages(frozen_prompt, compact=compact)
    binding = manifest.orchestrator
    backend = config.backend(binding.backend)
    client = make_client(
        kind=backend.kind,
        base_url=backend.base_url,
        api_key=backend.api_key,
        timeout=min(backend.timeout_seconds, timeout_seconds),
    )
    if not hasattr(client, "stream_structured_chat"):
        raise RuntimeError("director probe requires a schema-capable Ollama backend")
    model = model_override or binding.model
    params = dict(binding.params)
    if temperature is not None:
        params["temperature"] = temperature
    if top_p is not None:
        params["top_p"] = top_p
    if repeat_penalty is not None:
        params["repeat_penalty"] = repeat_penalty
    if two_pass:
        return await _probe_two_pass(
            client=client,
            model=model,
            params=params,
            opening=opening,
            one_pass_messages=messages,
            report=report,
        )
    try:
        raw = "".join(
            [
                token
                async for token in client.stream_structured_chat(  # type: ignore[attr-defined]
                    model,
                    messages,
                    schema_name="orchestrator",
                    **params,
                )
            ]
        )
    except Exception as exc:
        _write_report(report, [f"MODEL: {model}", f"TRANSPORT: failed ({type(exc).__name__}: {exc})"])
        return 4
    report_lines = [f"MODEL: {model}", f"PARAMS: {json.dumps(params, sort_keys=True)}", "RAW OUTPUT", raw]
    try:
        parsed = parse_orchestrator_output(raw)
    except StructuredOutputError as exc:
        report_lines.extend(("", f"PARSE: failed ({exc})"))
        _write_report(report, report_lines)
        return 2
    issue = review_orchestrator_narration(
        parsed.narration,
        actor_names=opening.cast,
        continuity_anchors=continuity_anchors_for_opening(opening),
    )
    if issue is None and parsed.next_actor and parsed.next_actor.casefold() not in {
        name.casefold() for name in opening.cast
    }:
        issue = SafetyIssue("NEXT_ACTOR_INVALID", "next_actor must name exactly one cast member")
    if issue is None and not parsed.canon_updates:
        issue = SafetyIssue(
            "CANON_UPDATE_REQUIRED",
            "director beat must record a new resource, constraint, or piece of knowledge",
        )
    report_lines.extend(("", "PARSE: passed", "NARRATION", parsed.narration))
    report_lines.append(f"WORDS: {len(parsed.narration.split())}")
    if issue is not None:
        report_lines.append(f"ACCEPTANCE: failed ({issue.code}: {issue.detail})")
        _write_report(report, report_lines)
        return 3
    report_lines.extend(("ACCEPTANCE: passed", "QUALITY: HUMAN_REVIEW_REQUIRED"))
    _write_report(report, report_lines)
    return 0


async def _probe_two_pass(
    *,
    client,
    model: str,
    params: dict[str, object],
    opening: OpeningSnapshot,
    one_pass_messages: list[dict[str, str]],
    report: Path | None,
) -> int:
    """Audition just one planner/render pair with no season records."""

    payload = json.loads(one_pass_messages[1]["content"])
    plan_messages = build_director_plan_messages(
        opening=opening,
        private_plan=HiddenSeasonPlan.model_validate(payload["private_plan"]),
        accepted_canon=payload["accepted_canon"],
        scene_transcript=payload["scene_transcript"],
        game_state={
            "scene_objective": "",
            "clocks": {"mission": 0, "danger": 0, "mystery": 0, "relationship": 0},
            "last_state_change": None,
            "last_pressure": None,
        },
        mission_clock=payload["mission_clock"],
        previous_shared_outcome=payload["previous_shared_outcome"],
        private_day_direction=payload["private_day_direction"],
        round_number=1,
        max_rounds=4,
        spent_director_terms=payload["spent_director_imagery"],
    )
    report_lines = [f"MODEL: {model}", f"PARAMS: {json.dumps(params, sort_keys=True)}"]
    try:
        plan_raw = "".join(
            [
                token
                async for token in client.stream_structured_chat(
                    model, plan_messages, schema_name="director_plan", **params
                )
            ]
        )
        plan = parse_director_plan_output(plan_raw)
    except Exception as exc:
        report_lines.extend(("PLANNER", f"failed ({type(exc).__name__}: {exc})"))
        _write_report(report, report_lines)
        return 2
    if plan.next_actor.casefold() not in {name.casefold() for name in opening.cast}:
        report_lines.extend(("PLANNER", "failed (NEXT_ACTOR_INVALID)"))
        _write_report(report, report_lines)
        return 3
    spent_terms = payload["spent_director_imagery"]

    anchors = continuity_anchors_for_opening(opening)
    render_messages = build_director_render_messages(
        plan=plan.model_dump(mode="json"),
        continuity_anchors=anchors,
        spent_director_terms=spent_terms,
        established_scene=payload["scene_transcript"],
    )
    try:
        render_raw = "".join(
            [
                token
                async for token in client.stream_structured_chat(
                    model, render_messages, schema_name="director_render", **params
                )
            ]
        )
        rendered = parse_director_render_output(render_raw)
    except Exception as exc:
        report_lines.extend(("PLANNER: passed", "RENDERER", f"failed ({type(exc).__name__}: {exc})"))
        _write_report(report, report_lines)
        return 2
    detail = rendered.narration.strip()
    issue = review_orchestrator_narration(
        detail,
        actor_names=opening.cast,
    )
    if issue is None and len(detail.split()) > 35:
        issue = SafetyIssue("DIRECTOR_LEAD_IN_TOO_VERBOSE", "optional lead-in exceeds 35 words")
    if issue is None and repeats_shared_phrase(
        detail, (*payload["scene_transcript"], plan.state_change, plan.pressure),
    ):
        detail = ""
        report_lines.append("REPETITIVE OPTIONAL DETAIL: omitted; raw renderer output retained below")
    compiled = _compile_director_beat(detail, plan)
    issue = issue or SceneRunner._review_director_render(compiled, plan, max_words=160)
    report_lines.extend(
        (
            "PLANNER: passed",
            "PLAN",
            json.dumps(plan.model_dump(mode="json"), indent=2, sort_keys=True),
            "RENDERER",
            rendered.narration,
            "COMPILED BEAT",
            compiled,
        )
    )
    report_lines.append(
        "ACCEPTANCE: passed" if issue is None else f"ACCEPTANCE: failed ({issue.code}: {issue.detail})"
    )
    report_lines.append("QUALITY: HUMAN_REVIEW_REQUIRED")
    _write_report(report, report_lines)
    return 0 if issue is None else 3


def _write_report(report: Path | None, lines: list[str]) -> None:
    text = "\n".join(lines) + "\n"
    print(text, end="")
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--frozen-prompt", type=Path, required=True)
    parser.add_argument("--report", type=Path, help="private text report written after the probe")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="use prior director beats and the latest four actor turns from the frozen context",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=25.0,
        help="bounded endpoint timeout for this probe (default: 25 seconds)",
    )
    parser.add_argument(
        "--model",
        help="temporary director model override; does not change the rehearsal manifest",
    )
    parser.add_argument("--temperature", type=float, help="temporary sampling override")
    parser.add_argument("--top-p", type=float, help="temporary nucleus-sampling override")
    parser.add_argument("--repeat-penalty", type=float, help="temporary repetition-penalty override")
    parser.add_argument(
        "--two-pass",
        action="store_true",
        help="probe the private director-plan and renderer pair instead of the retired one-pass beat",
    )
    args = parser.parse_args()
    manifest = SceneModelManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
    return asyncio.run(
        _probe(
            config=AppConfig.load(args.config),
            manifest=manifest,
            frozen_prompt=args.frozen_prompt,
            report=args.report,
            compact=args.compact,
            timeout_seconds=args.timeout_seconds,
            model_override=args.model,
            temperature=args.temperature,
            top_p=args.top_p,
            repeat_penalty=args.repeat_penalty,
            two_pass=args.two_pass,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
