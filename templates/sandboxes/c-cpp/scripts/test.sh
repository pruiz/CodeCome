#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome C/C++ test hook. Marker: __TARGET_NAME__.
set -euo pipefail

if [ ! -f /.dockerenv ]; then
  exec docker compose -f sandbox/docker-compose.yml exec -T codecome-sandbox "$0" "$@"
fi

cd /workspace

echo "CodeCome C/C++ test hook"

if [ -f /workspace/src/Makefile ] && grep -qE "^test:" /workspace/src/Makefile; then
  echo "Detected Makefile test target. Running: make test"
  cd /workspace/src
  make test
elif [ -d /workspace/tmp/build ] && [ -f /workspace/tmp/build/CTestTestfile.cmake ]; then
  echo "Detected CMake CTest. Running ctest --output-on-failure."
  cd /workspace/tmp/build
  ctest --output-on-failure
else
  echo "No test runner configured for target __TARGET_NAME__."
fi
