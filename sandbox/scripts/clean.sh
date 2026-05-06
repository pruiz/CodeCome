#!/usr/bin/env bash
set -euo pipefail

docker compose -f sandbox/docker-compose.yml down --remove-orphans
mkdir -p tmp
rm -rf tmp/*
mkdir -p tmp
echo "Environment cleaned."
