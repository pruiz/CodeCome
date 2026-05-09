#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome Ruby build hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome Ruby build hook"

if [ -f Gemfile ]; then
  echo "Detected Gemfile. Running: bundle install"
  bundle install
else
  echo "No Gemfile found for target __TARGET_NAME__."
  exit 1
fi
'
