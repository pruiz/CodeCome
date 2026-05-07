# Notes for the static-web sandbox baseline

## When to use

- HTML / CSS / image content with no server-side runtime.
- Pre-built SPA bundles dropped into `src/` for review.
- Documentation sites or marketing pages where dynamic behaviour is
  optional.

## When NOT to use

- Target requires a build step (Vite, Webpack, etc.) — use `node`.
- Target requires server-side logic — use the matching language
  example.

## Common follow-up edits

- Add `gzip on;` and security headers to the nginx config for closer
  parity with production.
- Mount additional directories as `:ro` if assets live outside
  `src/`.
