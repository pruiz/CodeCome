#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome Node.js build hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome Node.js build hook"

if [ -f pnpm-lock.yaml ]; then
  echo "Detected pnpm-lock.yaml. Running: pnpm install --frozen-lockfile"
  pnpm install --frozen-lockfile
  if pnpm run --if-present build >/dev/null 2>&1; then pnpm run build; fi
elif [ -f yarn.lock ]; then
  echo "Detected yarn.lock. Running: yarn install --frozen-lockfile"
  yarn install --frozen-lockfile
  yarn run --if-present build
elif [ -f package-lock.json ]; then
  echo "Detected package-lock.json. Running: npm ci"
  npm ci
  npm run --if-present build
elif [ -f package.json ]; then
  echo "Only package.json detected. Running: npm install"
  npm install --no-audit --no-fund
  npm run --if-present build
else
  echo "No Node.js manifest detected for target __TARGET_NAME__."
  exit 1
fi
'
