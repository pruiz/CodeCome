#!/usr/bin/env bash
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome Python build hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome Python build hook"

python3 -m venv /workspace/tmp/venv
. /workspace/tmp/venv/bin/activate

if [ -f pyproject.toml ]; then
  echo "Detected pyproject.toml. Running: pip install -e ."
  pip install -e .
elif [ -f requirements.txt ]; then
  echo "Detected requirements.txt. Running: pip install -r requirements.txt"
  pip install -r requirements.txt
elif [ -f setup.py ]; then
  echo "Detected setup.py. Running: pip install -e ."
  pip install -e .
elif [ -f Pipfile ]; then
  echo "Detected Pipfile. Use Pipenv outside this hook for full fidelity."
  pip install pipenv
  pipenv install --dev
else
  echo "No known Python manifest detected for target __TARGET_NAME__."
fi
'
