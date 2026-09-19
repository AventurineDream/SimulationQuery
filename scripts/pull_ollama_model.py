#!/usr/bin/env python3
"""Pull one Ollama model while persisting private progress for operator review."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx


def _write_status(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--status-file", type=Path, required=True)
    args = parser.parse_args()
    endpoint = args.base_url.rstrip("/") + "/api/pull"
    started_at = datetime.now(UTC).isoformat()
    _write_status(
        args.status_file,
        {"model": args.model, "started_at": started_at, "status": "starting"},
    )
    try:
        with httpx.stream(
            "POST",
            endpoint,
            json={"name": args.model, "stream": True},
            timeout=None,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                update = json.loads(line)
                _write_status(
                    args.status_file,
                    {
                        "model": args.model,
                        "started_at": started_at,
                        "updated_at": datetime.now(UTC).isoformat(),
                        **update,
                    },
                )
    except Exception as exc:
        _write_status(
            args.status_file,
            {
                "model": args.model,
                "started_at": started_at,
                "updated_at": datetime.now(UTC).isoformat(),
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
