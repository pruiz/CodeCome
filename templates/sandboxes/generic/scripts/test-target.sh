#!/usr/bin/env bash
# CodeCome generic test hook. The agent may extend this for the
# specific target. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace

echo "CodeCome generic test hook"
echo "No test runner configured for the generic sandbox."
echo "Edit sandbox/scripts/test-target.sh for target __TARGET_NAME__."
'
