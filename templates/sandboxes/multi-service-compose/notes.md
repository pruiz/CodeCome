# Notes for the multi-service-compose sandbox baseline

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

## Honoring rules

1. If `src/docker-compose.yml` exists and is usable, both build and
   test scripts include it via a second `-f` flag.
2. The sandbox compose adds the `codecome-tools` service for shell
   utilities.
3. `codecome-app` is a placeholder: replace it with the actual
   primary service, or remove it if `src/docker-compose.yml`
   already provides one.

## Build-time vs runtime

Multi-stack repositories often contain build-time helpers (e.g. a
small Node.js layer that produces a static asset bundle consumed by
a Python or Go runtime). Those build-time stacks should not be
expressed as services here. Instead:

- Express them as multi-stage builds inside the runtime service's
  Dockerfile.
- Or, run them as one-off Compose `run` invocations, not always-on
  `services`.

## Common follow-up edits

- Replace `codecome-app` with the actual primary service.
- Add explicit `depends_on` and healthchecks.
- Add database services (Postgres, MySQL, Redis, etc.) as needed.
- Mount `tmp/` for evidence capture during runtime validation.
