#!/usr/bin/env bash
# CodeCome Go test hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome Go test hook"

if [ -f go.mod ]; then
  echo "Running: go test ./..."
  go test ./...
else
  echo "No go.mod found for target __TARGET_NAME__."
fi
'
