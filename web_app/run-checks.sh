#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[web_app] Backend unit tests"
cd "$ROOT_DIR/backend"
venv/bin/python3 -m pytest -q tests

echo "[web_app] Backend compile"
venv/bin/python3 -m compileall -q app

echo "[web_app] Frontend tests"
cd "$ROOT_DIR/frontend"
npm test

echo "[web_app] Frontend build"
npm run build

echo "[web_app] All checks passed"
