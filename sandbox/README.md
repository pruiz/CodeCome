# CodeCome Sandbox

`sandbox/` contains the local execution environment used during validation.

The sandbox is intentionally generic, but the initial Docker image is optimized for C/C++ validation because the first planned PoC target is the NIST SARD Juliet C/C++ test suite.

## Current default tooling

The default sandbox image includes:

- GCC
- G++
- Clang
- CMake
- Make
- Ninja
- GDB
- LLDB
- Valgrind
- strace
- Python 3
- ripgrep
- jq
- curl
- wget
- unzip

This is enough for many C/C++ source review and validation workflows, including sanitizer-based testing.

## Not included by default

The default image does not currently include:

- .NET SDK
- Node.js / npm
- Java / Maven / Gradle
- Go
- Rust
- PHP
- Ruby
- database servers
- browsers
- Playwright
- mobile SDKs

If a target requires these, extend `sandbox/Dockerfile` or create a target-specific Dockerfile.

## Common commands

Check sandbox:

    ./sandbox/scripts/check.sh

Start sandbox:

    ./sandbox/scripts/up.sh

Stop sandbox:

    ./sandbox/scripts/down.sh

Open shell:

    ./sandbox/scripts/shell.sh

Show logs:

    ./sandbox/scripts/logs.sh

Clean sandbox:

    ./sandbox/scripts/clean.sh

Run generic build hook:

    ./sandbox/scripts/build-target.sh

Run generic test hook:

    ./sandbox/scripts/test-target.sh

## Target-specific adaptation

For each target, adapt these files as needed:

    sandbox/Dockerfile
    sandbox/docker-compose.yml
    sandbox/scripts/build-target.sh
    sandbox/scripts/test-target.sh

Additional target-specific scripts may be added under:

    sandbox/scripts/

Examples:

    sandbox/scripts/run-target.sh
    sandbox/scripts/reset-target.sh
    sandbox/scripts/build-cwe.sh
    sandbox/scripts/run-testcase.sh
    sandbox/scripts/asan-build.sh

## Rules

- The validator may freely experiment inside the sandbox.
- Do not attack third-party systems.
- Do not use production credentials.
- Do not exfiltrate secrets.
- Do not modify `src/` unless explicitly instructed.
- Store validation evidence under `itemdb/evidence/<finding-id>/`.
- Store temporary files under `tmp/`.

## C/C++ sanitizer example

For C/C++ targets, a useful starting point is:

    clang -fsanitize=address,undefined -fno-omit-frame-pointer -g -O1 input.c -o /workspace/tmp/input-asan
    /workspace/tmp/input-asan

Capture compiler commands, runtime commands, sanitizer output, and crash traces as evidence.

## Future isolation model

The initial PoC uses one validation worker at a time.

Future versions may run one isolated sandbox per finding using:

- one Docker Compose project per finding,
- one container per finding,
- one disposable VM per finding,
- one remote sandbox per finding.
