# Notes for the C/C++ sandbox baseline

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
