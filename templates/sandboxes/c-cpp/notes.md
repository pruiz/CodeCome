# Notes for the C/C++ sandbox baseline

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
