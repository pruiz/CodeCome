#!/usr/bin/env bash
# CodeCome PHP build hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome PHP build hook"

if [ -f composer.json ]; then
  echo "Detected composer.json. Running: composer install --prefer-dist"
  composer install --prefer-dist --no-progress
else
  echo "No composer.json found for target __TARGET_NAME__."
  exit 1
fi
'
