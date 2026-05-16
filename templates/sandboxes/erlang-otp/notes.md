# Notes for the Erlang / OTP sandbox baseline

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

- Erlang / OTP repositories with `rebar.config`, `erlang.mk`, `mix.exs`,
  `.erl`, `.hrl`, or `.app.src` files.
- RabbitMQ-class broker and plugin repositories.
- Projects validated through Common Test, EUnit, Dialyzer, Xref, or
  BEAM runtime smoke checks.

## When NOT to use

- Target already ships a faithful multi-service runtime under `src/` that
  should be honored directly.
- Target is mostly frontend or JavaScript with only a thin BEAM helper.
- Target needs extra stateful services or cluster topology and should be
  combined with `multi-service-compose` or expanded into a fuller broker
  sandbox.
