# Notes for the Node.js sandbox baseline

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
