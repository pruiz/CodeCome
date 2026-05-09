# Notes for the Go sandbox baseline

## Seed reminder

This template is a starting point, not a finished sandbox. During
Phase 1b the agent must extend it into a fully functional
`sandbox/` with durable ways to:

    sandbox setup
    sandbox start
    sandbox sanity
    target build
    target test
    sandbox stop

Use the canonical helper set under `sandbox/scripts/`:
`setup.sh`, `up.sh`, `check.sh`, `build.sh`, `test.sh`, `down.sh`.
Add operational helpers such as `shell.sh`, `logs.sh`, `clean.sh`,
and `reset.sh` when they make sense for the target. Document any
extras or omitted helpers in `itemdb/notes/sandbox-plan.md`. See
`.opencode/skills/sandbox-bootstrap/SKILL.md`.

## When to use

- Go modules with `go.mod` and `go.sum`.
- Go-only services without database dependencies, or those whose DBs
  can be emulated via in-process libraries (sqlite, etc.).

## When NOT to use

- Target requires Postgres / Redis / Kafka — combine with
  `multi-service-compose`.
- Target requires private Go modules behind auth — provide a
  prepared `~/.netrc` or use a vendored layout.
- Target uses GOEXPERIMENT or a custom toolchain — pin
  `__GO_VERSION__` and consider using `tip` images.
