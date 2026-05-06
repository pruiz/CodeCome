#!/usr/bin/env bash
set -euo pipefail

docker compose -f sandbox/docker-compose.yml up -d --build
