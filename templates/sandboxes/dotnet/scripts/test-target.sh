#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome .NET test hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome .NET test hook"

if compgen -G "*.sln" >/dev/null; then
  sln_file="$(ls *.sln | head -n 1)"
  dotnet test "${sln_file}" --no-build
elif compgen -G "**/*.Tests.csproj" >/dev/null || compgen -G "**/*.csproj" >/dev/null; then
  dotnet test --no-build
else
  echo "No .NET test project detected for target __TARGET_NAME__."
fi
'
