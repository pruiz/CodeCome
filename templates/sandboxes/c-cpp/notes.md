# Notes for the C/C++ sandbox baseline

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

- Target ships C or C++ source.
- Target ships a `Makefile`, `CMakeLists.txt`, `configure`, or
  `meson.build`.
- Target requires sanitizer or debugger tooling for validation.

## When NOT to use

- Target requires cross-compilation to non-host architectures (ARM
  firmware, RTOS targets) — use `nested-virt`.
- Target embeds C/C++ as a small build helper for a higher-level
  language (e.g. native Python extensions) — prefer the language's
  example and add the C toolchain as a delta.
