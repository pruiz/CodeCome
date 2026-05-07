# Notes for the Ruby sandbox baseline

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

- Ruby projects with `Gemfile`.
- Rails, Sinatra, Sidekiq workers.
- Library gems with a `*.gemspec`.

## When NOT to use

- Target needs Postgres / Redis — combine with
  `multi-service-compose`.
- Target needs Webpacker, jsbundling-rails, or cssbundling-rails
  with Node.js — use `multi-service-compose`.
- Target depends on private gem servers — provide credentials via
  bundler config rather than baking them into the image.
