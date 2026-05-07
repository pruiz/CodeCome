# Go sandbox example

Baseline image for Go projects.

## What's included

- `golang:__GO_VERSION__-bookworm` base image (CGO enabled)
- Common Linux utilities: `git`, `make`, `python3`, `ripgrep`, `jq`,
  `strace`, `curl`.

## Markers

| Marker | Purpose |
|---|---|
| `__TARGET_NAME__` | Target name. |
| `__GO_VERSION__` | Go tag (e.g. `1.22`, `1.23`). |
| `__APP_PORT__` | Exposed port. |

## Build heuristics

Requires `go.mod`. Runs `go build ./...` and `go test ./...`.

## When to extend

- For race-detected runs: `go test -race ./...`.
- For coverage: `go test -coverprofile=cover.out ./...`.
- For binaries with `cgo` and native dependencies, ensure the
  toolchain has the correct `*-dev` headers.
