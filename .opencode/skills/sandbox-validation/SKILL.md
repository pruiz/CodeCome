# Sandbox Validation Skill

Use this skill whenever validation requires building, running, testing, instrumenting, or probing the target inside the local CodeCome sandbox.

The sandbox lives under:

    sandbox/

The sandbox is the only place where validators should freely experiment.

## Purpose

The sandbox provides an isolated local environment for:

- building the target,
- running tests,
- executing proof-of-concept inputs,
- using sanitizers,
- using debuggers,
- inspecting logs,
- collecting evidence,
- validating or rejecting findings.

## Required reading

Before using the sandbox, read:

- `sandbox/README.md`
- `sandbox/docker-compose.yml`
- `sandbox/Dockerfile`
- relevant scripts under `sandbox/scripts/`
- the assigned finding,
- relevant files under `itemdb/notes/`.

## Common commands

Check sandbox health:

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

## Sandbox boundaries

Allowed inside the sandbox:

- install packages,
- compile code,
- run local services,
- run tests,
- run debuggers,
- run sanitizers,
- create payloads,
- create temporary files,
- reset local test data,
- inspect local logs.

Not allowed:

- attacking third-party systems,
- using production credentials,
- exfiltrating secrets,
- modifying production systems,
- performing destructive actions outside the workspace,
- modifying `src/` unless explicitly instructed.

## Write locations

Validation evidence must be written under:

    itemdb/evidence/<finding-id>/

Temporary files should be written under:

    tmp/

Run summaries may be written under:

    runs/

Do not leave important evidence only in terminal output.

## Evidence capture

For every validation attempt, capture:

- exact commands,
- inputs,
- outputs,
- observed result,
- expected safe behavior,
- expected vulnerable behavior,
- limitations.

Useful evidence files include:

    commands.txt
    output.txt
    logs.txt
    sanitizer.log
    crash.txt
    request.http
    response.txt
    exploit.py
    payload.bin
    test-output.txt
    debugger-notes.md
    static-proof.md
    limitations.md

## Build hooks

The generic build hook is:

    ./sandbox/scripts/build-target.sh

It attempts common build systems such as:

- Makefile,
- CMake,
- package.json,
- Python project files,
- .NET project files.

The default sandbox image is currently C/C++ oriented. Some branches may require extending the Dockerfile.

If the generic hook is insufficient, document what is missing and create a target-specific script under:

    sandbox/scripts/

Examples:

    sandbox/scripts/build-cwe.sh
    sandbox/scripts/run-testcase.sh
    sandbox/scripts/run-target.sh
    sandbox/scripts/asan-build.sh

## Test hooks

The generic test hook is:

    ./sandbox/scripts/test-target.sh

It attempts common test commands such as:

- `make test`,
- `ctest`,
- `npm test`,
- `pytest`,
- `dotnet test`.

If the hook does not fit the target, create or recommend a target-specific test script.

## C/C++ validation

For C/C++ targets, consider:

- AddressSanitizer,
- UndefinedBehaviorSanitizer,
- Valgrind,
- GDB,
- LLDB,
- crafted inputs,
- small harnesses,
- existing tests.

Useful compiler flags:

    -fsanitize=address,undefined -fno-omit-frame-pointer -g -O1

Record:

- compiler command,
- runtime command,
- sanitizer output,
- crash trace,
- relevant source path,
- observed behavior.

## HTTP validation

For HTTP targets, the sandbox may need:

- service startup script,
- database service,
- seed data,
- test users,
- local ports,
- HTTP client commands.

Capture:

- request,
- response,
- auth context,
- tenant/user ids,
- logs,
- expected safe response,
- observed vulnerable response.

## CLI validation

For CLI targets, capture:

- command,
- arguments,
- environment variables,
- input files,
- stdout,
- stderr,
- exit code,
- generated files,
- observed impact.

## File parser validation

For file parser targets, capture:

- crafted file,
- generation script,
- target invocation,
- crash or sanitizer output,
- expected safe behavior.

## Unresolved validation

If validation cannot be completed, do not fake confirmation.

Document:

- what was attempted,
- why it failed,
- missing dependencies,
- missing build steps,
- missing fixtures,
- missing credentials,
- sandbox changes needed,
- recommended next action.

Keep the finding in `NEEDS_VALIDATION`.

## Completion checklist

Before finishing sandbox validation:

- sandbox commands are recorded,
- evidence directory exists,
- evidence README exists when evidence was collected,
- relevant outputs are saved,
- finding validation result is updated,
- finding status is correct,
- limitations are documented,
- no important evidence is only in chat or terminal output.
