#!/bin/zsh
set -u
cd /Users/aven/Software/Github/AI-improv-troupe || exit 1
for version in 20 21; do
  target_root="/Users/aven/Software/Github/AI-improv-troupe/.rehearsal-data/actor-audition-v${version}-director-rotation-20260904"
  [[ ! -e "$target_root" ]] || { print "Existing root: $target_root"; exit 1; }
done
failed=0
for version in 20 21; do
  manifest_version=$((version - 4))
  print "Starting v${version} at $(date -u), using v${manifest_version} manifest"
  .venv/bin/python -u scripts/run_live_actor_audition_rehearsal.py \
    --data-root "/Users/aven/Software/Github/AI-improv-troupe/.rehearsal-data/actor-audition-v${version}-director-rotation-20260904" \
    --config "rehearsals/actor-audition-v${version}-config.yaml" \
    --manifest "rehearsals/actor-audition-v${manifest_version}-manifest.json" \
    > ".rehearsal-data/logs/actor-audition-v${version}-director-rotation-20260904.log" 2>&1
  code=$?
  print "Finished v${version} at $(date -u), exit=$code"
  (( code == 0 )) || failed=1
done
exit "$failed"
