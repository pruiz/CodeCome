#!/usr/bin/env bash
set -euo pipefail

docker compose -f sandbox/docker-compose.yml logs --tail=200 -f
