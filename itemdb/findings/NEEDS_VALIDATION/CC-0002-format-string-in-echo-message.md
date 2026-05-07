---
id: "CC-0002"
title: "Attacker-controlled format string in echo_message()"
status: "NEEDS_VALIDATION"
severity: "LOW"
confidence: "HIGH"
category: "Injection"
cwe:
  - "CWE-134"
language: "c"
target_area: "CLI echo command"
files:
  - "src/sample-c-cli/src/greet.c"
  - "src/sample-c-cli/src/main.c"
symbols:
  - "main"
  - "echo_message"
entry_points:
  - "sample-c-cli echo <message>"
sources:
  - "argv[2]"
  - "message argument passed from main() to echo_message()"
sinks:
  - "printf(message)"
trust_boundary: "Untrusted CLI input crosses into variadic format-string interpretation"
assets_at_risk:
  - "Process memory confidentiality"
  - "Process memory integrity"
  - "CLI availability"
validation:
  status: "NOT_STARTED"
  methods:
    - "runtime_reproduction"
    - "symbolic_or_manual_trace"
  evidence_dir: "itemdb/evidence/CC-0002"
  summary: ""
exploitation:
  status: "NOT_STARTED"
  impact_demonstrated: ""
  exploit_type: ""
  severity_before: ""
  severity_after: ""
  artifacts_dir: "itemdb/evidence/CC-0002/exploits"
  summary: ""
created_at: "2026-05-07"
updated_at: "2026-05-07"
---

# Summary

The `echo` subcommand passes attacker-controlled CLI input directly to `printf(message)` in `echo_message()`, allowing format specifiers such as `%x`, `%p`, or `%n` to be interpreted rather than printed literally.

# Target context

This is a local C CLI with an `echo <message>` command. The command is intended to print user-supplied text, but the implementation treats the text as a format string.

The relevant boundary is untrusted CLI input reaching a variadic formatting sink that can read additional stack values or attempt writes through `%n`.

# Affected code

- `src/sample-c-cli/src/main.c:29-31` dispatches `argv[2]` into `echo_message(argv[2])`
- `src/sample-c-cli/src/greet.c:18-20` executes `printf(message)` followed by `putchar('\n')`

Relevant symbols:

- `main`
- `echo_message`

# Vulnerability hypothesis

Known from source review:

- The program accepts a caller-controlled `message` argument.
- `echo_message()` forwards that string as the format parameter to `printf()`.
- No escaping, allowlist validation, or fixed format wrapper such as `printf("%s", message)` is present.

Assumed pending validation:

- Crafted payloads like `%p %p %p` will disclose memory values from the running process.
- `%n` may crash or attempt an uncontrolled write depending on platform and calling convention.

# Source-to-sink reasoning

1. A local caller controls `argv[2]` when invoking `sample-c-cli echo <message>`.
2. `main()` passes that argument directly to `echo_message()`.
3. `echo_message()` calls `printf(message)` with no fixed format string.
4. `printf()` interprets `%` sequences in attacker input as formatting directives.
5. This crosses the boundary from inert user data into an executable formatting language inside the C runtime.
6. Depending on payload, the sink may disclose stack values, dereference unintended pointers, or perform writes via `%n`.

# Attackability / trigger conditions

Any user or script able to invoke the CLI can trigger the condition with a crafted message string.

Example payload classes:

- `%p %p %p` for pointer disclosure attempts
- `%x %x %x` for stack word disclosure attempts
- `%n` for write/crash testing

No authentication or special environment is needed. Impact remains bounded to the process context unless a higher-privilege wrapper executes the binary.

# Impact

Realistic impact is local information disclosure from process memory and process instability or crashes.

In the current standalone CLI model this is primarily a same-user issue, so low severity is appropriate. If the binary is later reused as a helper by privileged automation or exposed through another interface, the same bug class could support more meaningful disclosure or memory-corruption outcomes.

# Validation plan

1. Build the program in `src/sample-c-cli/` with `make`.
2. Run a literal control case and capture output:
   - `./bin/sample-c-cli echo hello`
3. Run format-string probes and capture stdout, stderr, and exit code for each:
   - `./bin/sample-c-cli echo '%p %p %p'`
   - `./bin/sample-c-cli echo '%x %x %x'`
4. If needed, test write-oriented behavior carefully inside the sandbox:
   - `./bin/sample-c-cli echo '%n'`
5. Expected vulnerable behavior: directives are interpreted, producing pointer-like values, stack words, or a crash instead of literal `%` sequences.
6. Expected safe behavior after remediation: the program prints `%p %p %p`, `%x %x %x`, and `%n` literally.
7. Evidence to capture during Phase 4:
   - build command,
   - exact payloads,
   - terminal output,
   - any crash log if `%n` destabilizes the process.
8. Reject the finding if a rebuilt binary prints the payloads literally and code inspection shows the reviewed source is not the code actually compiled or executed.

# Counter-analysis

Reviewer conclusion:

Keep in `NEEDS_VALIDATION`. The format-string sink is explicit and reachable. Counter-analysis mainly narrows the likely impact to local disclosure or instability in the current CLI deployment model.

Evidence reviewed:

- `src/sample-c-cli/src/main.c:29-31` dispatches `argv[2]` directly to `echo_message()`.
- `src/sample-c-cli/src/greet.c:18-20` calls `printf(message)` with attacker-controlled data as the format string.
- Recon notes show no wrapper, escaping layer, or alternate formatting helper between CLI input and `printf()`.

Disproof attempts:

- Checked for a fixed format wrapper such as `printf("%s", message)`: none exists.
- Checked for upstream filtering of `%` characters or argument normalization in `main()`: none exists.
- Considered whether this is only a benign echo feature: it is not, because the C runtime interprets the input as a format language rather than inert data.
- Considered whether the issue is non-security because the caller is local: that lowers severity, but does not negate the presence of an attacker-controlled memory-disclosure / memory-corruption primitive.

Remaining assumptions:

- Runtime validation still needs to show the exact observable effect on this platform, especially whether `%p`/`%x` disclose meaningful values and whether `%n` crashes.
- No higher-privilege execution context has been identified, so present impact should stay bounded to the CLI process context unless later evidence shows a privileged wrapper.

Confidence adjustment:

Kept at `HIGH`. The sink is direct and the hypothesis does not depend on labels or speculative routing.

Recommended next action:

Validate with literal-versus-format payload comparisons and capture whether the runtime prints interpreted values or crashes.

# Validation result

Pending validation.

# Evidence

Pending.

# Exploitation Result

Pending.

# Demonstrated Impact

Pending.

# Remediation idea

Always use a fixed format string for user-controlled text, e.g. `printf("%s", message)`, and consider compiler warnings such as `-Wformat -Wformat-security` during validation/build hardening.

# Notes

- This finding is source-backed by the exact `printf(message)` call.
- The validation step should distinguish literal output from interpreted output to avoid overstating impact.
