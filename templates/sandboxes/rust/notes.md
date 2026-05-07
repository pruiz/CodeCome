# Notes for the Rust sandbox baseline

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

- Cargo-managed Rust projects.
- Workspace projects with multiple crates under one `Cargo.toml`.

## When NOT to use

- Target requires nightly-only features that the stable image cannot
  build — switch to the `nightly` rust image.
- Target depends on Postgres / Redis — combine with
  `multi-service-compose`.
- Target ships proc-macro crates with private build-time secrets — do
  not bring real secrets into the sandbox.

## Common follow-up edits

- Replace stable rust with a nightly tag for fuzzing / miri runs.
- Add `cargo install cargo-audit cargo-deny` for security auditing.
