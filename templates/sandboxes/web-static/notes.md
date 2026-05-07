# Notes for the static-web sandbox baseline

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
