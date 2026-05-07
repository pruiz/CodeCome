---
id: "CC-0001"
title: "Off-by-one stack write in greet_user() null termination"
status: "NEEDS_VALIDATION"
severity: "LOW"
confidence: "HIGH"
category: "Memory safety"
cwe:
  - "CWE-193"
  - "CWE-787"
language: "c"
target_area: "CLI greet command"
files:
  - "src/sample-c-cli/src/greet.c"
  - "src/sample-c-cli/src/util.c"
  - "src/sample-c-cli/src/main.c"
symbols:
  - "main"
  - "greet_user"
  - "clamp_copy_length"
entry_points:
  - "sample-c-cli greet <name>"
sources:
  - "argv[2]"
  - "name argument passed from main() to greet_user()"
sinks:
  - "memcpy(buffer, name, copy_len)"
  - "buffer[copy_len] = '\\0'"
trust_boundary: "Untrusted CLI input crosses into fixed-size stack memory management"
assets_at_risk:
  - "Process memory integrity"
  - "CLI availability"
validation:
  status: "NOT_STARTED"
  methods:
    - "runtime_reproduction"
    - "sanitizer_detection"
    - "symbolic_or_manual_trace"
  evidence_dir: "itemdb/evidence/CC-0001"
  summary: ""
exploitation:
  status: "NOT_STARTED"
  impact_demonstrated: ""
  exploit_type: ""
  severity_before: ""
  severity_after: ""
  artifacts_dir: "itemdb/evidence/CC-0001/exploits"
  summary: ""
created_at: "2026-05-07"
updated_at: "2026-05-07"
---

# Summary

The `greet` subcommand appears to contain an off-by-one stack write in `greet_user()`: when the supplied name is exactly 32 bytes long, `clamp_copy_length()` returns 32, `memcpy()` fills the whole `char buffer[32]`, and the subsequent `buffer[32] = '\0'` writes one byte past the end of the stack buffer.

# Target context

This target is a small local C CLI. The affected path is the `greet <name>` command implemented in `src/sample-c-cli/src/greet.c` and reached from `main()` in `src/sample-c-cli/src/main.c`.

The only directly observed attacker influence is CLI argument control. The security boundary here is untrusted user-controlled string length crossing into manual stack buffer management.

# Affected code

- `src/sample-c-cli/src/main.c:24-26` dispatches `argv[2]` into `greet_user(argv[2])`
- `src/sample-c-cli/src/greet.c:8-15` allocates `char buffer[32]`, copies `copy_len` bytes, then null-terminates using the same index
- `src/sample-c-cli/src/util.c:5-12` clamps using `if (length > max_len) return max_len;`, which still allows `copy_len == max_len`

Relevant symbols:

- `main`
- `greet_user`
- `clamp_copy_length`

# Vulnerability hypothesis

Known from source review:

- `buffer` is 32 bytes long.
- `copy_len` is derived from `strlen(name)` via `clamp_copy_length(name, sizeof(buffer))`.
- `clamp_copy_length()` returns `max_len` when `length > max_len`, and returns `length` unchanged when `length == max_len`.
- `greet_user()` always performs `buffer[copy_len] = '\0'` after the copy.

Assumed pending runtime validation:

- A 32-byte CLI argument is accepted unchanged by the program and reaches this code path.
- The one-byte out-of-bounds write is observable under ASan/UBSan and may crash or corrupt adjacent stack state depending on compiler layout.

# Source-to-sink reasoning

1. The caller controls `argv[2]` via `sample-c-cli greet <name>`.
2. `main()` passes that pointer directly to `greet_user()` with no length validation.
3. `greet_user()` computes `copy_len = clamp_copy_length(name, sizeof(buffer))` where `sizeof(buffer)` is 32.
4. `clamp_copy_length()` uses `>` instead of `>=`, so an input with `strlen(name) == 32` yields `copy_len == 32`.
5. `memcpy(buffer, name, copy_len)` writes exactly 32 bytes into the 32-byte destination.
6. The subsequent manual terminator write uses the same index and performs `buffer[32] = '\0'`, which crosses the stack buffer boundary.
7. The trust boundary crossed is untrusted CLI-controlled length influencing a fixed-size stack write without reserving space for the terminator.

# Attackability / trigger conditions

An attacker or calling script only needs the ability to invoke the CLI with a crafted 32-byte `name` argument.

Preconditions and assumptions:

- The `greet` command must be reachable, which it is via `main()`.
- No special privileges are required to trigger the bug.
- Security impact beyond self-crash depends on deployment context; the current notes do not show setuid execution or a privileged wrapper.

# Impact

Realistic baseline impact is a local denial of service or memory-corruption bug in the CLI process.

If the binary is ever embedded in a larger workflow, exposed through a wrapper, or run with elevated privileges, the same flaw could become more serious because even a one-byte stack overwrite may corrupt control or adjacent data. For the current standalone target, the most defensible severity is low pending validation.

# Validation plan

1. In `src/sample-c-cli/`, rebuild with sanitizers so the one-byte overwrite is observable:
   - `make clean`
   - `make CFLAGS='-Wall -Wextra -Wpedantic -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -Iinclude'`
2. Run a safe control input and capture output:
   - `./bin/sample-c-cli greet AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA`
   - Expected safe control behavior: normal `Hello, ...` output and no sanitizer finding for the 31-byte input.
3. Run the boundary input that should hit the bug:
   - `./bin/sample-c-cli greet AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA`
4. Capture stdout, stderr, exit code, and any sanitizer trace.
5. Expected vulnerable behavior: ASan or UBSan reports an out-of-bounds stack write at or immediately after `buffer[copy_len] = '\0'` in `greet_user()`.
6. Expected safe behavior after remediation: the 32-byte input is truncated safely or rejected, and no sanitizer finding occurs.
7. Evidence to capture during Phase 4:
   - build command and compiler output,
   - exact payload length used,
   - terminal output,
   - sanitizer log or crash trace.
8. Reject the finding if a rebuilt binary shows no out-of-bounds write for the 32-byte case and code inspection reveals a source/build mismatch rather than a real bug in the reviewed source.

# Counter-analysis

Reviewer conclusion:

Keep in `NEEDS_VALIDATION`. The off-by-one condition is strongly supported by the current source and is reachable from an attacker-controlled CLI argument. Counter-analysis reduced impact expectations, but did not disprove the memory-safety bug itself.

Evidence reviewed:

- `src/sample-c-cli/src/main.c:24-26` passes `argv[2]` directly to `greet_user()`.
- `src/sample-c-cli/src/greet.c:8-15` allocates `char buffer[32]`, copies `copy_len` bytes, and then writes `buffer[copy_len] = '\0'`.
- `src/sample-c-cli/src/util.c:5-12` returns `max_len` when input length exceeds 32 and returns 32 unchanged when input length is exactly 32.
- Recon notes under `itemdb/notes/` show no upstream length validation, wrapper enforcement, or alternate entrypoint that would constrain `argv[2]` before this sink.

Disproof attempts:

- Checked whether `main()` rejects long `greet` arguments: it only checks `argc >= 3`.
- Checked whether `clamp_copy_length()` reserves space for a terminator: it does not.
- Checked whether the copy could be unreachable or dead code: `greet` is a documented and directly dispatched subcommand.
- Considered whether compiler hardening or stack layout would negate the bug: those may affect exploitability or observability, but not the existence of the source-level out-of-bounds write.

Remaining assumptions:

- Runtime validation still needs to show that the reviewed source matches the built artifact used in Phase 4.
- The precise runtime effect may vary by compiler and optimization level; the most realistic current impact is local process crash or adjacent stack corruption rather than demonstrated code execution.

Confidence adjustment:

Kept at `HIGH`. Source-to-sink reasoning is direct and does not depend on benchmark labels, comments, or speculative reachability.

Recommended next action:

Validate with a sanitizer-enabled rebuild and compare a 31-byte control input against the 32-byte boundary input.

# Validation result

Pending validation.

# Evidence

Pending.

# Exploitation Result

Pending.

# Demonstrated Impact

Pending.

# Remediation idea

Reserve space for the terminator by clamping to `max_len - 1`, or avoid manual bounds logic entirely by using a safer copy pattern that always leaves room for `\0`.

# Notes

- This hypothesis is based on code behavior, not on filenames or benchmark labels.
- A follow-up counter-analysis should check whether compiler layout or optimization changes observability, but not whether the off-by-one condition exists in source.
