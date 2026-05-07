# Notes for the static-web sandbox baseline

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
