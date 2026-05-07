#!/usr/bin/env bash
# CodeCome Java build hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome Java build hook"

if [ -f pom.xml ]; then
  echo "Detected pom.xml. Running: mvn -DskipTests package"
  mvn -DskipTests package
elif [ -f build.gradle ] || [ -f build.gradle.kts ]; then
  echo "Detected Gradle build script. Running: gradle assemble"
  gradle assemble --no-daemon
else
  echo "No Maven or Gradle build manifest found for target __TARGET_NAME__."
  exit 1
fi
'
