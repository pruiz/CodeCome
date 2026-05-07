# Notes for the Ruby sandbox baseline

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
