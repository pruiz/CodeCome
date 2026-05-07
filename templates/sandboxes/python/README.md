# Python sandbox example

Baseline image for Python projects.

## What's included

- Official `python:__PYTHON_VERSION__-bookworm` base image
- `pip`, `pipx`, `virtualenv`
- Common Linux utilities: `git`, `make`, `curl`, `jq`, `ripgrep`,
  `strace`.

## Markers

| Marker | Purpose |
|---|---|
| `__TARGET_NAME__` | Target name used in messages and script comments. |
| `__PYTHON_VERSION__` | Python tag for the base image (e.g. `3.12`, `3.11`). |
| `__APP_PORT__` | Exposed port for the dev server (e.g. `8000`). |

## Build heuristics

`scripts/build-target.sh` tries, in order: `pyproject.toml`,
`requirements.txt`, `setup.py`, `Pipfile`. Outputs a virtualenv at
`/workspace/tmp/venv`.

## Notes

- For database-backed projects, use `multi-service-compose` and add
  Postgres / Redis / etc.
- For typed projects requiring `mypy` or `ruff`, install them via
  `pyproject.toml` rather than baking them into the image.
