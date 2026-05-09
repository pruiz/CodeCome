#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome Node.js test hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome Node.js test hook"

if [ -f pnpm-lock.yaml ]; then
  pnpm test --if-present || true
elif [ -f yarn.lock ]; then
  yarn test --if-present || true
elif [ -f package.json ]; then
  npm test --if-present || true
else
  echo "No Node.js manifest detected for target __TARGET_NAME__."
fi
'
