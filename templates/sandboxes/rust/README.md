# Rust sandbox example

Baseline image for Rust projects.

## What's included

- `rust:__RUST_TOOLCHAIN_TAG__-bookworm` base image
- `clippy` and `rustfmt` rustup components preinstalled
- `lldb`, `strace` for runtime inspection
- Common Linux utilities: `git`, `make`, `python3`, `ripgrep`, `jq`,
  `curl`.

## Markers

| Marker | Purpose |
|---|---|
| `__TARGET_NAME__` | Target name. |
| `__RUST_TOOLCHAIN_TAG__` | Rust tag (e.g. `1.81`, `1.82`, `latest`). |
| `__APP_PORT__` | Exposed port. |

## Build heuristics

Requires `Cargo.toml`. Runs `cargo build --all-targets` and
`cargo test --all-targets`. Cargo target cache and registry are
persisted across runs.

## When to extend

- For miri or AddressSanitizer in nightly: use a `nightly` image
  instead of stable.
- For projects that need OpenSSL bindings: add `libssl-dev` to the
  Dockerfile.
- For workspace-wide formatting/lint: `cargo fmt --all -- --check`,
  `cargo clippy --all-targets -- -D warnings`.
