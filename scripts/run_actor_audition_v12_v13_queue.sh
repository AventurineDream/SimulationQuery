#!/bin/zsh

set -u

cd /Users/aven/Software/Github/AI-improv-troupe || exit 1

.venv/bin/python scripts/run_live_actor_audition_rehearsal.py \
  --data-root /Users/aven/Software/Github/AI-improv-troupe/.rehearsal-data/actor-audition-v12-20260902 \
  --config rehearsals/actor-audition-v12-config.yaml \
  --manifest rehearsals/actor-audition-v5-manifest.json \
  > /Users/aven/Software/Github/AI-improv-troupe/.rehearsal-data/logs/actor-audition-v12-20260902.log 2>&1
v12_status=$?

.venv/bin/python scripts/run_live_actor_audition_rehearsal.py \
  --data-root /Users/aven/Software/Github/AI-improv-troupe/.rehearsal-data/actor-audition-v13-rotated-20260902 \
  --config rehearsals/actor-audition-v13-config.yaml \
  --manifest rehearsals/actor-audition-v13-rotated-manifest.json \
  > /Users/aven/Software/Github/AI-improv-troupe/.rehearsal-data/logs/actor-audition-v13-rotated-20260902.log 2>&1
v13_status=$?

if (( v12_status != 0 || v13_status != 0 )); then
  exit 1
fi
