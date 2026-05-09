# Notes for the C/C++ sandbox baseline

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
