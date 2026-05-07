# Notes for the Rust sandbox baseline

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
