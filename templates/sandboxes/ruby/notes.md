# Notes for the Ruby sandbox baseline

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
