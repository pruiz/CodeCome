# Erlang / OTP sandbox example

Baseline image for Erlang, OTP, and mixed Erlang/Elixir targets.

## What's included

- `erlang:__ERLANG_OTP_TAG__-bookworm` base image
- Common Linux utilities: `git`, `make`, `gawk`, `python3`, `ripgrep`,
  `jq`, `curl`, `strace`
- `rebar3` installed from Debian packages for repos that do not vendor it

## Markers

| Marker | Purpose |
|---|---|
| `__TARGET_NAME__` | Target name used in messages and script comments. |
| `__ERLANG_OTP_TAG__` | OTP tag (e.g. `27`, `27.3`). Match the target's supported range. |
| `__APP_PORT__` | Primary listener port, often AMQP for RabbitMQ-like targets. |
| `__MANAGEMENT_PORT__` | Secondary management or HTTP port when applicable. |

## Build heuristics

`scripts/build.sh` prefers `gmake` when a `Makefile` is present. That fits
RabbitMQ and other `erlang.mk`-based projects. It falls back to `rebar3
compile` or `mix compile` for smaller OTP repositories.

## Test heuristics

`scripts/test.sh` prefers targeted `gmake ct-*` flows for repositories that
document Common Test suites, then falls back to `rebar3 eunit`, `rebar3 ct`,
or `mix test`.

## When to extend

- Add broker-specific runtime helpers when the target exposes protocol
  listeners, management APIs, or clustering behavior.
- Add `dialyzer`, `xref`, `eqwalizer`, or `elp` helpers when static analysis
  is part of the validation model.
- Add extra ports, volumes, or service dependencies when the target needs a
  realistic cluster or management stack.
