# Notes for the Rust sandbox baseline

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
