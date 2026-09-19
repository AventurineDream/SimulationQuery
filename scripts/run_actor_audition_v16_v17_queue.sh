#!/bin/zsh
set -u
cd /Users/aven/Software/Github/AI-improv-troupe || exit 1
for version in 16 17; do
  target_root="/Users/aven/Software/Github/AI-improv-troupe/.rehearsal-data/actor-audition-v${version}-director-rotation-20260903"
  if [[ -e "$target_root" ]]; then
    print "Refusing to reuse existing rehearsal root: $target_root"
    exit 1
  fi
done
queue_failed=0
for version in 16 17; do
  print "Starting v${version} at $(date -u)"
  .venv/bin/python -u scripts/run_live_actor_audition_rehearsal.py \
    --data-root "/Users/aven/Software/Github/AI-improv-troupe/.rehearsal-data/actor-audition-v${version}-director-rotation-20260903" \
    --config "rehearsals/actor-audition-v${version}-config.yaml" \
    --manifest "rehearsals/actor-audition-v${version}-manifest.json" \
    > ".rehearsal-data/logs/actor-audition-v${version}-director-rotation-20260903.log" 2>&1
  rehearsal_exit=$?
  print "Finished v${version} at $(date -u), exit=$rehearsal_exit"
  if (( rehearsal_exit != 0 )); then
    queue_failed=1
  fi
done
exit "$queue_failed"
