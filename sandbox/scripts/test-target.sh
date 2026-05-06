#!/usr/bin/env bash
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace

echo "CodeCome target test hook"
echo "Target source path: /workspace/src"
echo

if [ -f /workspace/src/Makefile ]; then
  echo "Detected Makefile. Trying: make test"
  cd /workspace/src
  make test
elif [ -f /workspace/src/CMakeLists.txt ]; then
  echo "Detected CMakeLists.txt. Trying CTest."
  mkdir -p /workspace/tmp/build
  cd /workspace/tmp/build
  cmake /workspace/src
  cmake --build .
  ctest --output-on-failure
elif [ -f /workspace/src/package.json ]; then
  echo "Detected package.json. Trying: npm test"
  cd /workspace/src
  npm test
elif [ -f /workspace/src/pyproject.toml ] || [ -f /workspace/src/requirements.txt ]; then
  echo "Detected Python project. Trying: pytest"
  cd /workspace/src
  python3 -m pytest
elif find /workspace/src -maxdepth 2 -name "*.csproj" | grep -q .; then
  echo "Detected .NET project. Trying: dotnet test"
  cd /workspace/src
  dotnet test
else
  echo "No known test command detected."
  echo "Add target-specific test logic to sandbox/scripts/test-target.sh."
fi
'
