# Notes for the PHP sandbox baseline

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
