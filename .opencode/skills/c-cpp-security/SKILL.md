# C/C++ Security Skill

Use this skill when the target contains C or C++ source code.

This skill supports source reconnaissance, vulnerability hypothesis generation, counter-analysis, and validation for C/C++ targets.

## Scope

Relevant file types include:

- `.c`
- `.cc`
- `.cpp`
- `.cxx`
- `.h`
- `.hh`
- `.hpp`
- `.hxx`
- `.inl`

Relevant build files include:

- `Makefile`
- `CMakeLists.txt`
- `configure`
- `meson.build`
- `SConstruct`
- `.vcxproj`
- shell build scripts
- CI build definitions

## High-risk vulnerability classes

Prioritize review for:

- stack-based buffer overflow,
- heap-based buffer overflow,
- out-of-bounds read,
- out-of-bounds write,
- use after free,
- double free,
- invalid free,
- memory leak with security impact,
- integer overflow or truncation,
- signedness errors,
- format string injection,
- command injection,
- path traversal,
- unsafe temporary file use,
- time-of-check/time-of-use race,
- null pointer dereference with security impact,
- uninitialized memory use,
- type confusion,
- unsafe deserialization or parsing,
- unsafe cryptographic usage,
- secrets in source or binaries.

## Dangerous functions and APIs

Review uses of:

    strcpy
    strncpy
    strcat
    strncat
    sprintf
    snprintf
    vsprintf
    vsnprintf
    gets
    scanf
    sscanf
    fscanf
    memcpy
    memmove
    memset
    malloc
    calloc
    realloc
    free
    new
    delete
    system
    popen
    execl
    execlp
    execle
    execv
    execvp
    execvpe
    CreateProcess
    ShellExecute
    fopen
    open
    read
    write
    access
    stat
    lstat
    realpath
    mktemp
    tmpnam
    getenv
    putenv
    setenv
    dlopen
    dlsym

Do not report a finding just because one of these functions appears.

A finding requires attacker control, reachability, impact, and validation plan.

## Source-to-sink patterns

Look for paths where untrusted data reaches:

- fixed-size buffers,
- pointer arithmetic,
- memory copy length,
- string formatting,
- array index,
- allocation size,
- shell command,
- filesystem path,
- dynamic library path,
- parser state machine,
- cryptographic operation,
- privilege-changing operation.

## Buffer handling review

Check:

- destination buffer size,
- source length,
- null termination,
- off-by-one conditions,
- loop boundaries,
- unit mismatch,
- character count vs byte count,
- signed/unsigned conversions,
- length derived from untrusted input,
- allocation size matching copy size,
- structure field size assumptions.

Good finding example:

    The parser copies `record->name_len` bytes from an input-controlled record
    into `char name[64]` using `memcpy()` without checking that `name_len <= 64`.

Bad finding example:

    The code uses memcpy, so there may be a buffer overflow.

## Integer review

Check arithmetic used for:

- allocation sizes,
- buffer lengths,
- loop bounds,
- indexes,
- offsets,
- packet lengths,
- file sizes,
- multiplication of element count by element size.

Look for:

- integer overflow,
- truncation,
- signedness conversion,
- negative value converted to large unsigned value,
- unchecked multiplication,
- off-by-one errors,
- inconsistent length fields.

## Lifetime review

Check:

- ownership rules,
- free paths,
- error paths,
- early returns,
- aliasing,
- use after free,
- double free,
- missing free,
- freeing stack memory,
- freeing memory owned elsewhere,
- C++ RAII violations,
- smart pointer misuse.

## Format string review

Check whether attacker-controlled data reaches format parameters.

High-risk examples:

    printf(user_input);
    syslog(LOG_ERR, user_input);
    fprintf(stderr, user_input);

Safer examples:

    printf("%s", user_input);
    syslog(LOG_ERR, "%s", user_input);

## Command execution review

Check whether attacker-controlled data reaches:

- `system()`
- `popen()`
- `exec*()`
- platform-specific process APIs.

Consider:

- shell metacharacters,
- argument separation,
- environment variables,
- working directory,
- PATH lookup,
- quoting,
- privilege context.

Prefer findings where the exact command construction path is shown.

## Filesystem review

Check:

- path traversal,
- symlink races,
- unsafe temporary files,
- permissions,
- relative paths,
- archive extraction,
- canonicalization mistakes,
- check-then-use patterns,
- attacker-controlled filenames.

## Parser review

For file, packet, protocol, or message parsers, check:

- length fields,
- nested lengths,
- offset calculations,
- recursion depth,
- compression bombs,
- malformed input handling,
- state machine inconsistencies,
- bounds checks before reads/writes,
- integer overflow in size calculations.

## Crypto review

For C/C++ crypto code, check:

- custom crypto,
- weak algorithms,
- insecure modes,
- missing authentication,
- predictable randomness,
- static IVs,
- poor key handling,
- missing certificate validation,
- unsafe signature verification,
- timing-sensitive comparisons.

## Build and hardening notes

During reconnaissance or validation, identify whether the target uses:

- stack protector,
- PIE,
- RELRO,
- NX,
- FORTIFY_SOURCE,
- ASAN,
- UBSAN,
- MSAN,
- compiler warnings,
- static analyzers.

Do not rely on hardening as a complete mitigation for memory safety findings.

## Validation methods

Useful validation methods for C/C++ include:

- compile with AddressSanitizer,
- compile with UndefinedBehaviorSanitizer,
- run under Valgrind,
- run under GDB or LLDB,
- create crafted input files,
- create minimal harnesses,
- run existing tests,
- compare good/bad variants in benchmark corpora,
- static proof when runtime is not practical.

## Suggested sanitizer flags

<!-- Sync: sanitizer flags shared with sandbox-validation, juliet-benchmark -->

For GCC or Clang:

    -fsanitize=address,undefined -fno-omit-frame-pointer -g -O1

For stricter warnings:

    -Wall -Wextra -Wformat -Wformat-security -Wconversion -Wsign-conversion

Use these only when appropriate. Some targets may not build cleanly with all flags.

## Evidence to capture

For confirmed C/C++ findings, capture:

- compiler command,
- runtime command,
- input payload,
- sanitizer output,
- crash trace,
- relevant source lines,
- debugger backtrace if useful,
- expected safe behavior,
- observed vulnerable behavior.

## Counter-analysis checklist

Before keeping a C/C++ finding open, check:

- Is the input actually attacker-controlled?
- Is the function reachable?
- Is the length bounded elsewhere?
- Is the buffer large enough under all conditions?
- Is there a wrapper enforcing safety?
- Is the dangerous call only used in tests?
- Is the issue platform-specific?
- Is the crash security-relevant?
- Is the same root cause already reported?

## Reporting guidance

Be precise.

Mention:

- affected function,
- affected file,
- vulnerable operation,
- attacker-controlled input,
- preconditions,
- impact,
- validation method,
- evidence path.

Avoid broad claims such as:

    Memory corruption exists in this module.

Prefer:

    `parse_record()` copies the input-controlled `name_len` field into
    `record.name[64]` without checking the upper bound, allowing an
    out-of-bounds write when `name_len > 64`.
