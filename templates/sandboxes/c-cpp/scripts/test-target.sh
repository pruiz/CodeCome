#!/usr/bin/env bash
# CodeCome C/C++ test hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

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
'
