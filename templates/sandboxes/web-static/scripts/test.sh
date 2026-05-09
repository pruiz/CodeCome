#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome static-web smoke test. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml up -d

trap "docker compose -f sandbox/docker-compose.yml down -v" EXIT

# Give nginx a moment to start.
sleep 2

echo "CodeCome static-web smoke test"

# Use the host port for external reachability.
APP_PORT="$(grep -m 1 "__APP_PORT__" sandbox/docker-compose.yml | tr -dc 0-9 || echo 8080)"

if curl -fsSL "http://localhost:${APP_PORT}/" >/dev/null; then
  echo "Static site reachable on port ${APP_PORT} for target __TARGET_NAME__."
else
  echo "Static site not reachable on port ${APP_PORT} for target __TARGET_NAME__." >&2
  exit 1
fi
