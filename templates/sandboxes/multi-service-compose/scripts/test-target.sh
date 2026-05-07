#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome multi-service compose smoke test. Marker: __TARGET_NAME__.
set -euo pipefail

# Bring the stack up in detached mode, honor src/ compose when present.
src_compose=""
if [ -f src/docker-compose.yml ] || [ -f src/docker-compose.yaml ]; then
  src_compose="$(find src -maxdepth 1 -name "docker-compose.y*ml" | head -n 1)"
fi

if [ -n "${src_compose}" ]; then
  COMPOSE_ARGS=(-f sandbox/docker-compose.yml -f "${src_compose}")
else
  COMPOSE_ARGS=(-f sandbox/docker-compose.yml)
fi

docker compose "${COMPOSE_ARGS[@]}" up -d

trap "docker compose ${COMPOSE_ARGS[*]} down -v" EXIT

# Give services a moment to converge.
sleep 5

echo "CodeCome multi-service compose smoke test"
docker compose "${COMPOSE_ARGS[@]}" ps

echo "(Replace this script with target-specific health checks for __TARGET_NAME__.)"
