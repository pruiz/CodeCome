# Notes for the nested-virt sandbox baseline

## When to use

- Firmware blobs (`.bin`, `.elf`, `.img`).
- Cross-architecture targets that cannot run via Docker alone.
- Kernels and bootloaders.
- Binary-only payloads where source review is impossible.

## When NOT to use

- Native x86_64 binaries built from source — use `c-cpp`.
- Userland tools — use the matching language example.
- Containerized runtimes — use `multi-service-compose`.

## Common follow-up edits

- Replace the test script with concrete QEMU invocations:
  - `qemu-system-arm -M virt -nographic ...`
  - `qemu-system-aarch64 -M virt -cpu cortex-a53 ...`
  - `qemu-system-x86_64 -drive file=image.qcow2 ...`
- Set up serial console capture into `tmp/` for evidence.
- Use `qemu-user-static` for one-off binary launches without a full
  guest OS.
