#!/usr/bin/env bash
# CodeCome PHP test hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome PHP test hook"

if [ -x vendor/bin/phpunit ]; then
  echo "Running: vendor/bin/phpunit"
  vendor/bin/phpunit
elif [ -x vendor/bin/pest ]; then
  echo "Running: vendor/bin/pest"
  vendor/bin/pest
else
  echo "No PHPUnit or Pest binary found for target __TARGET_NAME__."
fi
'
