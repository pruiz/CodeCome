#!/usr/bin/env bash
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash
