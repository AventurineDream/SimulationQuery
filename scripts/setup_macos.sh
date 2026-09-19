#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python_bin=""
if [[ -n "${IMPROV_PYTHON:-}" ]]; then
  candidates=("$IMPROV_PYTHON")
else
  candidates=(python3.14 python3.13 python3.12 python3.11)
fi

for candidate in "${candidates[@]}"; do
  resolved="$candidate"
  if [[ "$candidate" != */* ]]; then
    resolved="$(command -v "$candidate" 2>/dev/null || true)"
  fi
  if [[ -x "$resolved" ]] && "$resolved" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    python_bin="$resolved"
    break
  fi
done

if [[ -z "$python_bin" ]]; then
  echo "Python 3.11 or newer is required." >&2
  echo "On Apple Silicon, install it with: brew install python@3.14" >&2
  exit 1
fi

if [[ -e .venv && ! -x .venv/bin/python ]]; then
  echo "An existing .venv is not usable in this checkout." >&2
  echo "Move it aside or remove it, then run this script again." >&2
  exit 1
fi

if [[ ! -e .venv ]]; then
  "$python_bin" -m venv .venv
fi

if ! .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
  echo "The existing .venv uses an incompatible Python interpreter." >&2
  echo "Move it aside or remove it, then run this script again." >&2
  exit 1
fi

.venv/bin/python -m pip install -e ".[dev]"

echo
echo "AI Improv Troupe is ready."
echo "Run: .venv/bin/improv run examples/the_last_train.plan.json --dry-run"
