#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome Erlang / OTP test hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome Erlang / OTP test hook"

if [ -f CONTRIBUTING.md ] && grep -q "ct-" CONTRIBUTING.md 2>/dev/null && [ -f Makefile ]; then
  if command -v gmake >/dev/null 2>&1; then
    echo "Detected documented Common Test targets. Running: gmake ct-unit_log_management"
    gmake ct-unit_log_management
  else
    echo "Detected documented Common Test targets. Running: make ct-unit_log_management"
    make ct-unit_log_management
  fi
elif [ -f rebar.config ]; then
  echo "Detected rebar.config. Running: rebar3 eunit"
  rebar3 eunit
elif [ -f mix.exs ]; then
  echo "Detected mix.exs. Running: mix test"
  mix local.hex --force
  mix local.rebar --force
  mix test
else
  echo "No known Erlang / OTP test runner detected for target __TARGET_NAME__."
fi
'
