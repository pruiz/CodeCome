# Generic sandbox example

Last-resort baseline. Use when no other example fits the target stack.

## What's included

- Debian base image
- Common Linux utilities: `bash`, `curl`, `wget`, `git`, `make`,
  `python3`, `ripgrep`, `jq`, `strace`, `xxd`, `file`, `unzip`.

## Markers

| Marker | Purpose |
|---|---|
| `__TARGET_NAME__` | Target name used in messages and script comments. |
| `__DEBIAN_BASE_TAG__` | Debian base tag (e.g. `bookworm`, `trixie`). |

## How to extend

Add the toolchain you need to `Dockerfile` and update
`scripts/build-target.sh` and `scripts/test-target.sh`. If the target
fits a more specific example, prefer switching to that example
instead of bloating the generic one.
