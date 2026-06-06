#!/bin/bash
# CodeQL Docker wrapper — invoked by the harness to run CodeQL inside the
# sandbox container.  The harness supplies all CodeQL arguments after -- .
set -euo pipefail

# Resolve compose file and service from the recipe or sane defaults
COMPOSE_FILE="${CODECOME_COMPOSE_FILE:-./sandbox/docker-compose.yml}"
SERVICE="${CODECOME_SERVICE:-app}"
CODEQL_BIN="${CODECOME_CODEQL_BIN:-/opt/codeql/codeql}"

exec docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" "$CODEQL_BIN" "$@"
