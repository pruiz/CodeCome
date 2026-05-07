# Notes for the Node.js sandbox baseline

## When to use

- JavaScript / TypeScript backend or library targets.
- Targets with `package.json` and any of `package-lock.json`,
  `yarn.lock`, or `pnpm-lock.yaml`.

## When NOT to use

- Target ships only a static frontend (HTML/CSS) — use `web-static`.
- Target needs Postgres / Redis — combine with `multi-service-compose`.
- Target needs full browsers for E2E — extend with Playwright deps,
  or use a Playwright-specific example if added later.
- Target is a Node service that depends on a separate frontend
  build step — express both via `multi-service-compose`.
