# Notes for the Python sandbox baseline

## Seed reminder

This template is a starting point, not a finished sandbox. During
Phase 1b the agent must extend it into a fully functional
`sandbox/` with durable ways to:

    start/build the environment
    run sandbox sanity checks
    build the target
    test the target

Prefer helpers such as `build-sandbox.sh`, `up.sh`, `check.sh`,
`build-target.sh`, and `test-target.sh` under `sandbox/scripts/`. Add
operational helpers such as `down.sh`, `shell.sh`, `logs.sh`,
`clean.sh`, and `reset.sh`
when they make sense for the target. Document any extras or omitted
helpers in `itemdb/notes/sandbox-plan.md`. See
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
