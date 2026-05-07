#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome generic build hook. The agent may extend this for the
# specific target. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace

echo "CodeCome generic build hook"
echo "Target source path: /workspace/src"
echo

if [ -f /workspace/src/Makefile ]; then
  echo "Detected Makefile. Running: make"
  cd /workspace/src
  make
else
  echo "No build configured for the generic sandbox."
  echo "Edit sandbox/scripts/build-target.sh for target __TARGET_NAME__."
fi
'
