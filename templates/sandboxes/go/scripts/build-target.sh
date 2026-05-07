#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome Go build hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome Go build hook"

if [ -f go.mod ]; then
  echo "Detected go.mod. Running: go build ./..."
  go build ./...
else
  echo "No go.mod found for target __TARGET_NAME__."
  exit 1
fi
'
