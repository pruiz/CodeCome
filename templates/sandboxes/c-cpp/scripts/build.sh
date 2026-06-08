#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome C/C++ build hook. Marker: __TARGET_NAME__.
set -euo pipefail

if [ ! -f /.dockerenv ]; then
  exec docker compose -f sandbox/docker-compose.yml exec -T codecome-sandbox "$0" "$@"
fi

cd /workspace

echo "CodeCome C/C++ build hook"
echo "Target source path: /workspace/src"
echo

if [ -f /workspace/src/CMakeLists.txt ]; then
  echo "Detected CMakeLists.txt. Running CMake build."
  mkdir -p /workspace/tmp/build
  cd /workspace/tmp/build
  cmake /workspace/src
  cmake --build . -j
elif [ -f /workspace/src/Makefile ]; then
  echo "Detected Makefile. Running: make"
  cd /workspace/src
  make
elif [ -f /workspace/src/meson.build ]; then
  echo "Detected meson.build. Running meson + ninja build."
  meson setup /workspace/tmp/build /workspace/src
  ninja -C /workspace/tmp/build
else
  echo "No known build system detected for target __TARGET_NAME__."
  echo "Add target-specific build logic here."
  exit 1
fi
