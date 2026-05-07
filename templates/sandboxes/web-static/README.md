# Static web sandbox example

Serves the contents of `src/` over nginx for static-site review.

## What's included

- `nginx:1.27-bookworm` base image
- Common Linux utilities: `curl`, `git`, `jq`, `ripgrep`, `strace`.

## Markers

| Marker | Purpose |
|---|---|
| `__TARGET_NAME__` | Target name. |
| `__APP_PORT__` | Exposed port (default 8080). |

## How it works

`nginx.conf.template` contains an `__APP_PORT__` placeholder that the
container's entrypoint substitutes via `envsubst` at startup.

`src/` is mounted **read-only** at `/workspace/src` and served as
the document root.

## When NOT to use

- Target is a Single-Page App with a development server — use the
  matching node example instead.
- Target requires server-side rendering — use the matching language
  example.
