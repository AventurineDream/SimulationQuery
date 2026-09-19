#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from improv_troupe.application.actor_audition_rehearsal import run_live_actor_audition_rehearsal
from improv_troupe.application.live_runtime import SceneModelManifest
from improv_troupe.config import AppConfig


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the private two-day, four-model actor audition.")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(run_live_actor_audition_rehearsal(
        args.data_root,
        config=AppConfig.load(args.config),
        manifest=SceneModelManifest.model_validate_json(args.manifest.read_text(encoding="utf-8")),
    ))
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
