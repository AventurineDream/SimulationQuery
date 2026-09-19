#!/usr/bin/env python3
"""Explicit stages for the private SQ pilot; no command implicitly starts another."""
import argparse
import asyncio
import json
from pathlib import Path

from improv_troupe.research.pilot import prepare, preflight, run_parents, run_probes
from improv_troupe.research.coding import export_review, summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "preflight", "run", "probes", "review-export", "summarize"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("rehearsals/sq-pilot2-selected-config.yaml"))
    parser.add_argument("--manifest", type=Path, default=Path("rehearsals/sq-pilot2-research-manifest.json"))
    parser.add_argument("--review-dir", type=Path)
    parser.add_argument("--ratings", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if args.command == "prepare":
        result = prepare(args.root, repo=repo, config_path=args.config, manifest_path=args.manifest)
        result = {"prepared": result["experiment_id"], "root": str(args.root), "live_calls": 0}
    elif args.command in {"preflight", "run", "probes"}:
        action = {"preflight": preflight, "run": run_parents, "probes": run_probes}[args.command]
        result = asyncio.run(action(args.root, repo=repo, config_path=args.config))
        if args.command == "preflight":
            result = {"identity_recorded": True, "models": list(result["models"]),
                      "note": "No generation performed; per-request capacity/completion checks still apply."}
    else:
        if args.review_dir is None:
            parser.error("--review-dir is required")
        if args.command == "review-export":
            result = export_review(args.root, args.review_dir)
        else:
            if args.ratings is None:
                parser.error("--ratings is required")
            result = summarize(args.root, args.review_dir, args.ratings)
    print(json.dumps(result, indent=2))
    if args.command == "run" and any(r["status"] != "COMPLETED" for r in result):
        return 2
    if args.command == "probes" and any(
        r.get("status") == "MISSING_CHECKPOINT" or
        any(s["status"] != "COMPLETED" for s in r.get("stages", [])) for r in result
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
