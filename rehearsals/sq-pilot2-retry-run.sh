#!/bin/sh
set -u
umask 077
BASE=/home/aven/sq-pilot2-retry-20260906
ROOT="$BASE/data"
[ ! -f "$ROOT/STOPPED.json" ] || exit 0
[ ! -f "$ROOT/parents-complete.json" ] || exit 0
cd "$BASE/checkout" || exit 1
export PYTHONPATH="$BASE/checkout/src"
exec /opt/improv-troupe/.venv/bin/python -u scripts/run_sq_scheduled.py tick \
  --root "$ROOT" \
  --config rehearsals/sq-pilot2-retry-config.yaml
