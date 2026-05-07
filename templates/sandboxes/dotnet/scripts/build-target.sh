#!/usr/bin/env bash
# CodeCome .NET build hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome .NET build hook"

if compgen -G "*.sln" >/dev/null; then
  sln_file="$(ls *.sln | head -n 1)"
  echo "Detected solution: ${sln_file}"
  dotnet restore "${sln_file}"
  dotnet build "${sln_file}" --no-restore
elif compgen -G "**/*.csproj" >/dev/null; then
  echo "Detected one or more .csproj. Running dotnet build."
  dotnet restore
  dotnet build --no-restore
else
  echo "No .sln or .csproj found for target __TARGET_NAME__."
  exit 1
fi
'
