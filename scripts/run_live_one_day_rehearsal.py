#!/usr/bin/env python3
"""Run one isolated Aether day against selected private model backends.

The data root must be a new or empty dedicated directory. This command never
uses S01, publishes output, deploys code, or starts the production worker.
Use --resume only to continue an interrupted run in its same isolated root;
the supplied manifest must exactly match the persisted rehearsal manifest.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from improv_troupe.application import SceneModelManifest, run_live_one_day_rehearsal
from improv_troupe.config import AppConfig


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--resume", action="store_true", help="continue an interrupted isolated rehearsal")
    args = parser.parse_args()
    manifest = SceneModelManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
    report = asyncio.run(
        run_live_one_day_rehearsal(
            args.data_root,
            config=AppConfig.load(args.config),
            manifest=manifest,
            resume=args.resume,
        )
    )
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
