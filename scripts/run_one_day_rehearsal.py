#!/usr/bin/env python3
"""Run the deterministic, production-isolated DASH-07 one-day rehearsal.

The required data root must be a new or empty dedicated directory. This command
does not contact a model endpoint, close a season, or create public output.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from improv_troupe.application.one_day_rehearsal import run_one_day_rehearsal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(run_one_day_rehearsal(args.data_root))
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
