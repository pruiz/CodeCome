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
  # Phase 1b agent should adapt this targeted command to match the real target's CONTRIBUTING.md
  if command -v gmake >/dev/null 2>&1; then
    echo "Detected documented Common Test targets. Running: gmake test"
    gmake test
  else
    echo "Detected documented Common Test targets. Running: make test"
    make test
  fi
elif [ -f rebar.config ]; then
  echo "Detected rebar.config. Running: rebar3 do eunit, ct"
  rebar3 do eunit, ct
elif [ -f mix.exs ]; then
  echo "Detected mix.exs. Running: mix test"
  mix local.hex --force
  mix local.rebar --force
  mix test
else
  echo "No known Erlang / OTP test runner detected for target __TARGET_NAME__."
fi
'
