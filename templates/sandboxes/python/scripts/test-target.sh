#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome Python test hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome Python test hook"

if [ -d /workspace/tmp/venv ]; then
  . /workspace/tmp/venv/bin/activate
fi

if command -v pytest >/dev/null 2>&1; then
  echo "Running: pytest"
  pytest
elif python3 -c "import unittest" >/dev/null 2>&1 && [ -d tests ]; then
  echo "Running: python3 -m unittest discover tests"
  python3 -m unittest discover tests
else
  echo "No test runner configured for target __TARGET_NAME__."
fi
'
