# Multi-service compose sandbox example

For targets that need more than a single image: a primary app plus
auxiliary services (database, cache, message broker, frontend
worker, etc.).

## Honoring strategy

If the target ships its own `docker-compose.yml` under `src/`, the
build and test scripts pass it as a second `-f` argument:

```
docker compose -f sandbox/docker-compose.yml -f src/docker-compose.yml ...
```

That keeps the user's runtime definition authoritative while letting
the sandbox add its tooling container, ports, and labels.

## What's included

- `codecome-tools`: minimal Debian image with the usual CodeCome
  utilities for shell-driven validation.
- `codecome-app`: placeholder application service. Replace, rename,
  or remove according to the target.

## Markers

| Marker | Purpose |
|---|---|
| `__TARGET_NAME__` | Used in container names and labels. |
| `__PRIMARY_APP_PORT__` | Default port for the primary app. |

## When to use

- Target spans multiple runtime services.
- Target needs Postgres/Redis/Kafka/etc. alongside the application.
- Target ships its own compose file but lacks tooling for validation.

## When NOT to use

- Target is a single-stack project. Pick the matching language
  example.
- Target requires nested virtualization. Pick `nested-virt` instead.
