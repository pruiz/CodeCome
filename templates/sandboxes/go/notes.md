# Notes for the Go sandbox baseline

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
