#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome Java test hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome Java test hook"

if [ -f pom.xml ]; then
  echo "Running: mvn test"
  mvn test
elif [ -f build.gradle ] || [ -f build.gradle.kts ]; then
  echo "Running: gradle test"
  gradle test --no-daemon
else
  echo "No Maven or Gradle build manifest found for target __TARGET_NAME__."
fi
'
