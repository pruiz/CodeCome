#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome Terraform static-review test hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome Terraform static-review test hook"

if command -v tflint >/dev/null 2>&1; then
  tflint --recursive --no-color || true
else
  echo "tflint not available; skipping for target __TARGET_NAME__."
fi
'
