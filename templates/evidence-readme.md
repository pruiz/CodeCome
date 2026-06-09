# Evidence for CC-0000

Date: YYYY-MM-DD

# Summary

Briefly summarize what this evidence proves or disproves.

# Validation method

Describe the validation method used.

Examples:

- static proof
- unit test
- integration test
- runtime reproduction
- sanitizer detection
- crash reproduction
- HTTP exploit
- CLI exploit
- file-based trigger
- config-based trigger
- benchmark oracle comparison

# Environment

Describe the environment used for validation.

Include:

- sandbox image or runtime,
- relevant tool versions,
- target build mode,
- relevant configuration,
- date of validation.

# Threat-model assumptions (if applicable)

When the validation result was materially affected by assumptions from the threat model, document them here.

Examples:

- Attacker capability constrained by threat-model non-capabilities
- Trust boundary documented in `itemdb/notes/threat-model.md` that shaped the validation path
- Existing control from the threat model that blocked or narrowed validation
- Open assumption from the threat model that affected exploitability assessment

If the threat model did not affect the result, this section may be omitted.

# Commands executed

List the exact commands executed.

    command goes here

# Inputs

Describe or reference any crafted inputs, requests, payloads, config files, test data, or fixtures.

# Observed result

Describe what happened.

Include relevant stdout, stderr, logs, crash traces, sanitizer output, HTTP responses, or generated files.

For large outputs, reference separate files instead of pasting everything here.

# Expected vulnerable behavior

Describe the behavior that would confirm the vulnerability.

# Expected safe behavior

Describe the behavior that would indicate the target is safe or the finding is rejected.

# Conclusion

State whether the evidence supports:

- CONFIRMED
- REJECTED
- UNRESOLVED

Explain why.

# Files

List evidence files in this directory.

Examples:

- `commands.txt`
- `output.txt`
- `logs.txt`
- `sanitizer.log`
- `crash.txt`
- `request.http`
- `response.txt`
- `exploit.py`
- `payload.bin`
- `test-output.txt`
- `debugger-notes.md`
- `static-proof.md`
- `limitations.md`

# Limitations

Document limitations, uncertainty, missing dependencies, incomplete reproduction, or assumptions.
