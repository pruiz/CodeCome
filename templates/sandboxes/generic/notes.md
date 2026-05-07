# Notes for the generic sandbox baseline

This baseline assumes nothing about the target. It is a fallback when
detection cannot match a more specific stack.

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

- Target stack is unknown.
- Target is a mixed-stack experiment that does not justify the
  multi-service example.
- Reconnaissance flagged the source as data-only or scripts-only.

## When NOT to use

- Target has clear C/C++ source — use `c-cpp`.
- Target has Python, Node, Go, Rust, etc. — use the matching example.
- Target needs nested virtualization — use `nested-virt`.
- Target ships its own `Dockerfile` — honor it via
  `multi-service-compose` or wrap it directly.
