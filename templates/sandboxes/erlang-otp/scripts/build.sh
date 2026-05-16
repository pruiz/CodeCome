#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome Erlang / OTP build hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome Erlang / OTP build hook"

if [ -f Makefile ] && command -v gmake >/dev/null 2>&1; then
  echo "Detected Makefile. Running: gmake"
  gmake
elif [ -f Makefile ]; then
  echo "Detected Makefile. Running: make"
  make
elif [ -f rebar.config ]; then
  echo "Detected rebar.config. Running: rebar3 compile"
  rebar3 compile
elif [ -f mix.exs ]; then
  echo "Detected mix.exs. Running: mix deps.get && mix compile"
  mix local.hex --force
  mix local.rebar --force
  mix deps.get
  mix compile
else
  echo "No known Erlang / OTP build manifest detected for target __TARGET_NAME__."
fi
'
