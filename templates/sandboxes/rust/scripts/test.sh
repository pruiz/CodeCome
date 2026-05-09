#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome Rust test hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome Rust test hook"

if [ -f Cargo.toml ]; then
  echo "Running: cargo test --all-targets"
  cargo test --all-targets
else
  echo "No Cargo.toml found for target __TARGET_NAME__."
fi
'
