# Node.js sandbox example

Baseline image for Node.js / TypeScript projects.

## What's included

- `node:__NODE_VERSION__-bookworm` base image
- `corepack`-managed `npm`, `yarn`, `pnpm`
- Common Linux utilities: `git`, `make`, `python3`, `ripgrep`, `jq`,
  `strace`, `curl`.

## Markers

| Marker | Purpose |
|---|---|
| `__TARGET_NAME__` | Target name used in messages and script comments. |
| `__NODE_VERSION__` | Node tag (e.g. `20`, `22`). |
| `__APP_PORT__` | Exposed dev port. |

## Build heuristics

`scripts/build.sh` chooses pnpm > yarn > npm by lockfile.
Calls `*.run --if-present build`.

## When to extend

- For browser-based E2E suites, add Playwright after install:
  `npx playwright install --with-deps chromium`.
- For native deps (`node-gyp`), extend the Dockerfile with
  `build-essential`, `libssl-dev`, etc.
