# C / C++ sandbox example

Baseline image for native C and C++ targets, including ASan/UBSan
runs.

## What's included

- gcc, g++, clang, clang-tools (clang-format, clang-tidy)
- cmake, make, ninja-build, meson via pip
- gdb, lldb, valgrind, strace
- pkg-config and common build essentials
- python3 + pip for sanitizer post-processing scripts

## Markers

| Marker | Purpose |
|---|---|
| `__TARGET_NAME__` | Target name used in messages and script comments. |
| `__DEBIAN_BASE_TAG__` | Debian base tag (e.g. `bookworm`, `trixie`). |

## Build heuristics

`scripts/build-target.sh` tries, in order: CMake, Makefile, Meson.
Adapt this for the specific target.

## Sanitizer example

```
clang -fsanitize=address,undefined -fno-omit-frame-pointer -g -O1 \
    src/example.c -o /workspace/tmp/example-asan
/workspace/tmp/example-asan
```
