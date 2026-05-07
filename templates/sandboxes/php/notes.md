# Notes for the PHP sandbox baseline

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
