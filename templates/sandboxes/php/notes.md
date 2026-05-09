# Notes for the PHP sandbox baseline

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

- PHP projects using Composer.
- Frameworks: Laravel, Symfony, Slim, plain PHP.

## When NOT to use

- Target requires a full LAMP stack — combine with
  `multi-service-compose`.
- Target depends on PHP-FPM behind Nginx in a specific topology —
  port that compose layout into `multi-service-compose`.
- Target ships only static PHP includes without Composer — use
  `web-static` plus a manual PHP installation.

## Common follow-up edits

- Add `pdo_mysql` / `pdo_pgsql` extensions.
- Pin Composer plugins via `composer.json` rather than installing
  globally.
