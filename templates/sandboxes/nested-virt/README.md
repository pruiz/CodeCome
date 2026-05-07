# Nested-virt sandbox example

Use only when the target requires real virtualization (firmware,
foreign architecture, binary-only images). Justification in
`itemdb/notes/sandbox-plan.md` is mandatory.

## What's included

- Debian bookworm base
- `qemu-system-arm`, `qemu-system-aarch64`, `qemu-system-x86_64`,
  `qemu-system-misc`
- `qemu-user-static`, `qemu-utils`
- `binutils`, `binutils-arm-none-eabi`, `binutils-aarch64-linux-gnu`,
  `gdb-multiarch`
- Common Linux utilities for evidence capture

## Markers

| Marker | Purpose |
|---|---|
| `__TARGET_NAME__` | Target name used in messages. |
| `__QEMU_ARCH__` | QEMU arch (e.g. `arm`, `aarch64`, `x86_64`). |

## KVM acceleration

The compose file mounts `/dev/kvm` from the host. If KVM is not
available, comment out the `devices:` entry. Without KVM, runs will
be much slower and some payloads may not be feasible.

## Why is justification required?

QEMU-in-Docker is a heavyweight setup, and many targets that look
like they need it actually do not. Examples:

- A C++ target that builds for x86_64 — use `c-cpp`.
- A static library that you intend to fuzz — use `c-cpp` plus
  AFL/libFuzzer.
- A Python project that loads native extensions — use `python` with
  the right `*-dev` libs.

If you are not sure, prefer one of those baselines first and only
fall back to `nested-virt` after confirmation.
