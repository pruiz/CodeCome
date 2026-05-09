---
id: "CC-0000"
title: "Short vulnerability title"
status: "PENDING"
severity: "MEDIUM"
confidence: "LOW"
category: "Unclassified"
cwe: []
language: "unknown"
target_area: "unknown"
files: []
symbols: []
entry_points: []
sources: []
sinks: []
trust_boundary: "unknown"
assets_at_risk: []
validation:
  status: "NOT_STARTED"
  methods: []
  evidence_dir: "itemdb/evidence/CC-0000"
  summary: ""
exploitation:
  status: "NOT_STARTED"
  impact_demonstrated: ""
  exploit_type: ""
  severity_before: ""
  severity_after: ""
  artifacts_dir: "itemdb/evidence/CC-0000/exploits"
  summary: ""
created_at: "YYYY-MM-DD"
updated_at: "YYYY-MM-DD"
---

# Summary

Briefly describe the suspected vulnerability.

The summary must be specific enough to understand the issue without reading the entire finding.

# Target context

Describe the relevant target type, component, feature, route, command, library API, testcase, configuration, or execution context.

Examples:

- HTTP endpoint in a web application.
- CLI command and argument parser.
- Public library function.
- Background job.
- File parser.
- C/C++ testcase entrypoint.
- Infrastructure configuration block.

# Affected code

List the relevant files, functions, classes, methods, symbols, routes, commands, configuration keys, or build targets.

Use precise paths and names.

# Vulnerability hypothesis

Explain the suspected vulnerability.

This section must clearly distinguish what is known from what is assumed.

# Source-to-sink reasoning

Describe the path from attacker-controlled or externally influenced input to the dangerous sink or security decision.

Include:

- source of input,
- transformations,
- validation or missing validation,
- security boundary crossed,
- sink reached,
- relevant conditions.

If the issue is not source-to-sink based, describe the equivalent reasoning model.

# Attackability / trigger conditions

Explain how an attacker, user, caller, input file, request, configuration, or environment condition could trigger the issue.

Mention required privileges, preconditions, and assumptions.

# Impact

Explain the realistic security impact.

Examples:

- unauthorized data access,
- privilege escalation,
- remote code execution,
- local code execution,
- denial of service,
- information disclosure,
- authentication bypass,
- authorization bypass,
- memory corruption,
- integrity violation,
- secret exposure.

# Validation plan

Describe exactly how to prove or disprove the finding.

The plan should be actionable inside the CodeCome workspace.

Include one or more of:

- static proof steps,
- build commands,
- test commands,
- runtime reproduction steps,
- HTTP requests,
- CLI invocations,
- crafted input files,
- sanitizer/debugger commands,
- expected vulnerable behavior,
- expected safe behavior.

# Counter-analysis

Try to disprove the finding.

Look for:

- input validation,
- authorization checks,
- framework protections,
- safe wrappers,
- unreachable code paths,
- impossible attacker control,
- non-security impact,
- duplicate issues,
- benchmark label leakage,
- misleading filenames or comments,
- false assumptions.

# Validation result

Pending.

When validation is performed, record:

- validation date,
- method used,
- commands executed,
- observed result,
- whether the finding was confirmed or rejected,
- limitations.

# Evidence

Pending.

List evidence files under:

`itemdb/evidence/<finding-id>/`

Examples:

- request/response files,
- logs,
- terminal output,
- sanitizer reports,
- crash traces,
- screenshots,
- exploit scripts,
- generated payloads,
- test output,
- database state,
- debugger notes.

# Exploitation Result

Pending.

When exploit development is performed, record:

- exploitation date,
- exploit type developed,
- impact achieved,
- escalation steps taken,
- whether severity was adjusted,
- limitations of the demonstration.

# Demonstrated Impact

Pending.

Describe in concrete terms what an attacker achieves:

- what data was accessed, modified, or exfiltrated,
- what privileges were gained,
- what systems were compromised,
- what the blast radius is,
- what the business impact is.

# Root cause analysis

Pending.

In 2–6 sentences, explain precisely why the quoted code is exploitable.

Examples of root causes:

- missing input validation,
- unsafe sink (e.g. `memcpy` with attacker-controlled size,
  `system()` with attacker-controlled string),
- broken or missing authorization check,
- unsafe deserialization,
- race window between check and use,
- incorrect type assumption,
- mismatched buffer sizes,
- trust placed in attacker-controlled metadata.

Required content (not `Pending.`) when the finding is `EXPLOITED`.

# Data flow

Pending.

When the bug is input-driven, list the path as an ordered chain:

    1. source: <component> -- file:line
    2. propagator: <function/transform> -- file:line
    3. sink: <dangerous operation> -- file:line

When the bug is not input-driven (e.g. configuration default, lifetime
bug not driven by external input) write `Not applicable.` and add a
brief reason.

Required content (`Not applicable.` is acceptable) when the finding is
`EXPLOITED`.

# Inputs and preconditions

Pending.

List:

- attacker-controlled inputs (parameters, headers, files, packets,
  environment variables, etc.),
- required preconditions (privileges, network position, prior state,
  feature flags, timing windows).

Required content (not `Pending.`) when the finding is `EXPLOITED`.

# Recording

Pending.

When a demonstration recording exists, list the relative paths and a
one-line description for each artifact, e.g.:

- `itemdb/evidence/CC-0000/exploits/recordings/exploit.cast` -- asciinema
  raw recording of the end-to-end exploit.
- `itemdb/evidence/CC-0000/exploits/recordings/exploit.gif` -- rendered
  preview of the exploit.
- `itemdb/evidence/CC-0000/exploits/recordings/reproduce.sh` -- driver
  script that the recording captures.
- `itemdb/evidence/CC-0000/exploits/recordings/README.md` -- play and
  re-run instructions.

If no recording exists, explain why (missing tooling, exploit cannot be
driven without human interaction, etc.). Absence does not block
`EXPLOITED` but must be explicit.

Required content (not `Pending.`) when the finding is `EXPLOITED`.

# Remediation idea

Describe the likely fix pattern.

Keep it technical and concise.

For `CONFIRMED` and `EXPLOITED` findings, include a corrected-code
excerpt or unified diff showing the proposed fix. Keep the patch
minimal.

# Notes

Additional reviewer notes, edge cases, or follow-up ideas.
