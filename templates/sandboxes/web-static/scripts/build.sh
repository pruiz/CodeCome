#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome static-web build hook. Marker: __TARGET_NAME__.
set -euo pipefail

# Static content has no build step. We only verify there is content
# to serve.
if [ ! -d sandbox ]; then
  echo "sandbox/ missing." >&2
  exit 1
fi

if [ ! -d src ] || [ -z "$(ls -A src 2>/dev/null)" ]; then
  echo "src/ is empty for target __TARGET_NAME__."
  exit 1
fi

echo "Static content detected. No build step needed for target __TARGET_NAME__."
