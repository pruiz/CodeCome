#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome Terraform "build" hook. Marker: __TARGET_NAME__.
# Treats `terraform init -backend=false` and `terraform validate` as
# the static-review build step. Provider auth is intentionally absent.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome Terraform static-review build hook"

if ls *.tf >/dev/null 2>&1; then
  terraform init -backend=false -input=false -no-color
  terraform fmt -check -recursive || echo "(fmt issues; not fatal)"
  terraform validate -no-color
else
  echo "No .tf files found in src/ for target __TARGET_NAME__."
  exit 1
fi
'
