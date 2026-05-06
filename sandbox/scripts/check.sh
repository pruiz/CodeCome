#!/usr/bin/env bash
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
  echo "== System =="
  uname -a

  echo
  echo "== Toolchain =="
  gcc --version | head -n 1 || true
  g++ --version | head -n 1 || true
  clang --version | head -n 1 || true
  cmake --version | head -n 1 || true
  make --version | head -n 1 || true
  python3 --version || true
  rg --version | head -n 1 || true

  echo
  echo "== Workspace =="
  pwd
  test -d /workspace/src
  test -d /workspace/itemdb
  test -d /workspace/sandbox
  test -f /workspace/AGENTS.md
  test -f /workspace/codecome.yml

  echo
  echo "Sandbox OK"
'
