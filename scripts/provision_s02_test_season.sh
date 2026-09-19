#!/usr/bin/env bash
# Provision the isolated S02 test runtime. Run from the macOS checkout with an
# SSH identity already authorized for aven@10.0.0.103. This never writes S01's
# checkout, config, service, or data root.
set -euo pipefail

repo_root=$(cd "$(dirname "$0")/.." && pwd)
target=${IMPROV_LINUX_TARGET:-aven@10.0.0.103}
remote_checkout=/opt/improv-troupe-test
remote_config_dir=/etc/improv-troupe-test
remote_data_root=/var/lib/improv-troupe-test

ssh "$target" '
  set -eu
  for path in /opt/improv-troupe-test /etc/improv-troupe-test /var/lib/improv-troupe-test; do
    if [ -e "$path" ]; then
      echo "Refusing to overwrite existing S02 test path: $path" >&2
      exit 2
    fi
  done
  test -x /opt/improv-troupe/.venv/bin/python
'

tar -czf - \
  --exclude='.venv' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  -C "$repo_root" . \
| ssh "$target" 'cat > /tmp/improv-troupe-s02-test.tar.gz'

ssh -t "$target" '
  set -eu
  sudo install -d -m 750 -o root -g improv /opt/improv-troupe-test
  sudo tar --no-same-owner -xzf /tmp/improv-troupe-s02-test.tar.gz -C /opt/improv-troupe-test
  sudo rm -f /tmp/improv-troupe-s02-test.tar.gz
  sudo chgrp -R improv /opt/improv-troupe-test/src
  sudo chmod -R g+rX /opt/improv-troupe-test/src
  sudo cp -a /opt/improv-troupe/.venv /opt/improv-troupe-test/.venv
  # A copied venv can retain an absolute python link back into the S01 checkout.
  # Replace only its interpreter links before installing the editable test package.
  sudo rm -f /opt/improv-troupe-test/.venv/bin/python /opt/improv-troupe-test/.venv/bin/python3 /opt/improv-troupe-test/.venv/bin/python3.13
  sudo ln -s "$(command -v python3)" /opt/improv-troupe-test/.venv/bin/python3
  sudo ln -s python3 /opt/improv-troupe-test/.venv/bin/python
  sudo ln -s python3 /opt/improv-troupe-test/.venv/bin/python3.13
  # Some /opt mounts reject ownership changes.  The test runtime carries no
  # secrets, so allow the service account to traverse and read it instead.
  sudo chmod 751 /opt/improv-troupe-test
  sudo chmod -R a+rX /opt/improv-troupe-test/.venv
  sudo /opt/improv-troupe-test/.venv/bin/python -m pip install --no-deps -e /opt/improv-troupe-test
  sudo install -d -m 750 -o root -g improv /etc/improv-troupe-test
  sudo install -m 640 -o root -g improv /opt/improv-troupe-test/deploy/config.test.example.yaml /etc/improv-troupe-test/config.yaml
  sudo install -d -m 750 -o improv -g improv /var/lib/improv-troupe-test
  sudo install -m 644 /opt/improv-troupe-test/deploy/improv-troupe-test.service /etc/systemd/system/improv-troupe-test.service
  sudo install -m 644 /opt/improv-troupe-test/deploy/improv-troupe-test-green.service /etc/systemd/system/improv-troupe-test-green.service
  sudo install -m 644 /opt/improv-troupe-test/deploy/improv-troupe-test-green.timer /etc/systemd/system/improv-troupe-test-green.timer
  sudo systemctl daemon-reload
  sudo -u improv /opt/improv-troupe-test/.venv/bin/python /opt/improv-troupe-test/scripts/stage_first_run.py --approved-opening /opt/improv-troupe-test/benchmarks/s02-test-approved-opening-2026-08-30.json --manifest /opt/improv-troupe-test/benchmarks/s02-test-model-manifest-2026-08-30.json --config /etc/improv-troupe-test/config.yaml --data-root /var/lib/improv-troupe-test
  sudo systemctl enable --now improv-troupe-test.service
  sudo systemctl enable --now improv-troupe-test-green.timer
  sudo -u improv /opt/improv-troupe-test/.venv/bin/python -m improv_troupe.cli status --config /etc/improv-troupe-test/config.yaml
  systemctl status --no-pager --lines=8 improv-troupe-test.service
  systemctl list-timers --all --no-pager improv-troupe-test-green.timer
'
