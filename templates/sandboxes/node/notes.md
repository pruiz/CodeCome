# Notes for the Node.js sandbox baseline

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
