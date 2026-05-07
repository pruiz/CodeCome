#!/usr/bin/env bash
# CodeCome nested-virt build hook. Marker: __TARGET_NAME__.
# This sandbox is rarely a "build" environment in the conventional
# sense; the target is usually pre-built. Use this hook to verify
# QEMU and the supplied target image are loadable.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace

echo "CodeCome nested-virt build hook"
echo "QEMU arch: __QEMU_ARCH__"

qemu-system-__QEMU_ARCH__ --version | head -n 1

if [ -d src ] && [ -n "$(ls -A src 2>/dev/null)" ]; then
  echo "Found target artifacts under src/."
else
  echo "No target artifacts under src/ for target __TARGET_NAME__."
  exit 1
fi
'
