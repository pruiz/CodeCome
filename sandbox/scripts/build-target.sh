#!/usr/bin/env bash
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace

echo "CodeCome target build hook"
echo "Target source path: /workspace/src"
echo

if [ -f /workspace/src/Makefile ]; then
  echo "Detected Makefile. Running: make"
  cd /workspace/src
  make
elif [ -f /workspace/src/CMakeLists.txt ]; then
  echo "Detected CMakeLists.txt. Running CMake build."
  mkdir -p /workspace/tmp/build
  cd /workspace/tmp/build
  cmake /workspace/src
  cmake --build .
elif [ -f /workspace/src/package.json ]; then
  echo "Detected package.json. Running npm install and npm test/build if available."
  cd /workspace/src
  npm install
  npm run build --if-present
elif [ -f /workspace/src/pyproject.toml ] || [ -f /workspace/src/requirements.txt ]; then
  echo "Detected Python project. No default build action configured."
  echo "Target-specific build steps should be added to sandbox/scripts/build-target.sh."
elif find /workspace/src -maxdepth 2 -name "*.csproj" | grep -q .; then
  echo "Detected .NET project. Running dotnet build."
  cd /workspace/src
  dotnet build
else
  echo "No known build system detected."
  echo "Add target-specific build logic to sandbox/scripts/build-target.sh."
fi
'
