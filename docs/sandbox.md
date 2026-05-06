# CodeCome Sandbox

The CodeCome sandbox is the local execution environment used to validate findings.

It lives under:

    sandbox/

The sandbox is intentionally separate from the target source code under:

    src/

## Purpose

The sandbox is used for:

- building targets,
- running targets,
- running tests,
- executing local proof-of-concept inputs,
- using sanitizers,
- using debuggers,
- collecting logs,
- producing validation evidence.

## Default implementation

The initial sandbox uses Docker Compose.

Main files:

    sandbox/Dockerfile
    sandbox/docker-compose.yml
    sandbox/README.md
    sandbox/scripts/

The default image is currently optimized for C/C++ validation.

## Common commands

Check sandbox:

    make sandbox-check

Start sandbox:

    make sandbox-up

Stop sandbox:

    make sandbox-down

Open shell:

    make sandbox-shell

Show logs:

    make sandbox-logs

Clean sandbox:

    make sandbox-clean

Run generic build hook:

    make sandbox-build-target

Run generic test hook:

    make sandbox-test-target

## Direct script usage

The Make targets call these scripts:

    ./sandbox/scripts/check.sh
    ./sandbox/scripts/up.sh
    ./sandbox/scripts/down.sh
    ./sandbox/scripts/shell.sh
    ./sandbox/scripts/logs.sh
    ./sandbox/scripts/clean.sh
    ./sandbox/scripts/build-target.sh
    ./sandbox/scripts/test-target.sh

## Sandbox boundaries

Validators may freely experiment inside the sandbox.

Allowed:

- install packages,
- compile code,
- run local services,
- run local tests,
- run debuggers,
- run sanitizers,
- create payloads,
- create temporary files,
- reset local test data,
- inspect local logs.

Not allowed:

- attack third-party systems,
- use production credentials,
- exfiltrate secrets,
- modify production systems,
- perform destructive actions outside the workspace,
- modify `src/` unless explicitly instructed.

## Write locations

Validation evidence belongs under:

    itemdb/evidence/<finding-id>/

Temporary files belong under:

    tmp/

Run summaries may be stored under:

    runs/

Important evidence should not exist only in terminal output.

## Evidence examples

Useful evidence files:

    itemdb/evidence/CC-0001/README.md
    itemdb/evidence/CC-0001/commands.txt
    itemdb/evidence/CC-0001/output.txt
    itemdb/evidence/CC-0001/logs.txt
    itemdb/evidence/CC-0001/sanitizer.log
    itemdb/evidence/CC-0001/crash.txt
    itemdb/evidence/CC-0001/request.http
    itemdb/evidence/CC-0001/response.txt
    itemdb/evidence/CC-0001/exploit.py
    itemdb/evidence/CC-0001/payload.bin
    itemdb/evidence/CC-0001/test-output.txt
    itemdb/evidence/CC-0001/debugger-notes.md
    itemdb/evidence/CC-0001/static-proof.md
    itemdb/evidence/CC-0001/limitations.md

## C/C++ validation

The default sandbox includes common C/C++ tooling:

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

Useful sanitizer build flags:

    -fsanitize=address,undefined -fno-omit-frame-pointer -g -O1

Example:

    clang -fsanitize=address,undefined -fno-omit-frame-pointer -g -O1 src/example.c -o tmp/example-asan
    ./tmp/example-asan

Capture:

- compiler command,
- runtime command,
- input payload,
- sanitizer output,
- crash trace,
- relevant source lines,
- observed behavior,
- expected safe behavior.

## Extending the sandbox

The default image does not include every stack.

For .NET, Node.js, Java, Go, Rust, browsers, database servers, or other target-specific dependencies, extend:

    sandbox/Dockerfile

or create target-specific scripts under:

    sandbox/scripts/

Examples:

    sandbox/scripts/run-target.sh
    sandbox/scripts/reset-target.sh
    sandbox/scripts/build-cwe.sh
    sandbox/scripts/run-testcase.sh
    sandbox/scripts/asan-build.sh

## Future isolation model

The initial PoC uses one validation worker at a time.

Future versions may isolate validation workers using:

- one Docker Compose project per finding,
- one container per finding,
- one disposable VM per finding,
- one remote sandbox per finding.

Each worker should write only to:

    itemdb/evidence/<finding-id>/
    runs/

and should not share mutable runtime state with other validation workers.
