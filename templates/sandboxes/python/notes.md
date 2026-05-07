# Notes for the Python sandbox baseline

## Seed reminder

This template is a starting point, not a finished sandbox. During
Phase 1b the agent must extend it into a fully functional
`sandbox/`, including authoring missing canonical scripts:

    check.sh   up.sh   down.sh   shell.sh   logs.sh
    clean.sh   reset.sh

The agent should also adapt the starter `build-target.sh` and
`test-target.sh` to the actual project layout, and add
target-specific scripts when they help. Document any extras in
`itemdb/notes/sandbox-plan.md`. See
`.opencode/skills/sandbox-bootstrap/SKILL.md`.

## When to use

- Pure Python target with `pyproject.toml`, `requirements.txt`,
  `setup.py`, `setup.cfg`, or `Pipfile`.
- Web frameworks: Flask, Django, FastAPI, Starlette — fine, just add
  the framework via `pyproject.toml`.

## When NOT to use

- Target needs Postgres / Redis / RabbitMQ — combine with
  `multi-service-compose`.
- Target uses heavy native dependencies (e.g. `numpy` from source,
  `psycopg2`-build, native ML wheels) — extend the Dockerfile to add
  build-essential / specific dev libraries.
- Target ships JS frontend alongside Python backend — use
  `multi-service-compose`.

## Common follow-up edits

- Pin a specific `python:X.Y` tag for reproducibility.
- Add `libpq-dev` for `psycopg2`.
- Add `gcc`, `g++`, `make` if building native wheels.
- Replace `EXPOSE`/`ports` with the actual app port.
