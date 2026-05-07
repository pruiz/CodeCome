# Notes for the Python sandbox baseline

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
