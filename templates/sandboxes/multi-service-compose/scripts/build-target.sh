#!/usr/bin/env bash
# CodeCome multi-service compose build hook.
# Marker: __TARGET_NAME__.
#
# This hook honors src/docker-compose.yml when possible, falling back
# to the sandbox-only compose otherwise.
set -euo pipefail

if [ -f src/docker-compose.yml ] || [ -f src/docker-compose.yaml ]; then
  src_compose="$(find src -maxdepth 1 -name "docker-compose.y*ml" | head -n 1)"
  echo "Honoring existing ${src_compose} for target __TARGET_NAME__."
  docker compose \
    -f sandbox/docker-compose.yml \
    -f "${src_compose}" \
    build
else
  echo "No src/docker-compose.yml. Building sandbox-only stack for target __TARGET_NAME__."
  docker compose -f sandbox/docker-compose.yml build
fi
