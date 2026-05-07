# PHP sandbox example

Baseline image for PHP projects.

## What's included

- `php:__PHP_VERSION__-cli-bookworm` base image
- `composer` 2.x preinstalled
- Common PHP extensions: `mbstring`, `zip`, `xml`
- Common Linux utilities: `git`, `make`, `python3`, `ripgrep`, `jq`,
  `strace`, `curl`.

## Markers

| Marker | Purpose |
|---|---|
| `__TARGET_NAME__` | Target name. |
| `__PHP_VERSION__` | PHP tag (e.g. `8.3`, `8.2`). |
| `__APP_PORT__` | Exposed port (default 8000). |

## Build heuristics

Requires `composer.json`. Runs `composer install --prefer-dist` and
`phpunit` (or `pest`) when available.

## When to extend

- For Laravel: add `php artisan migrate` and rely on
  `multi-service-compose` for the database.
- For Symfony: ensure `bin/console` is executable inside the
  container.
- For projects requiring `pdo_mysql`, `pdo_pgsql`, etc., add the
  matching `docker-php-ext-install` line.
