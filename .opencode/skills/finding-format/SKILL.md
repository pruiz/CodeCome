# Finding Format Skill

Use this skill whenever you create, review, update, validate, or report a CodeCome finding.

A CodeCome finding is a durable Markdown artifact stored under `itemdb/findings/`.

The finding is the central unit of work in CodeCome.

## Purpose

A finding must describe a concrete vulnerability hypothesis or confirmed vulnerability in a way that is:

- precise,
- reviewable,
- reproducible,
- evidence-driven,
- easy to diff in Git,
- understandable by another agent or a human reviewer.

## Finding locations

Candidate findings:

    itemdb/findings/PENDING/

Confirmed findings:

    itemdb/findings/CONFIRMED/

Exploited findings (confirmed with demonstrated real-world impact):

    itemdb/findings/EXPLOITED/

Rejected findings:

    itemdb/findings/REJECTED/

Duplicate findings:

    itemdb/findings/DUPLICATE/

Evidence:

    itemdb/evidence/<finding-id>/

## File naming

Use this format:

    CC-0001-short-descriptive-slug.md

Rules:

- Use the `CC-` prefix.
- Use four digits for the numeric id.
- Use lowercase slugs.
- Use hyphens instead of spaces.
- Keep the slug short but meaningful.
- Do not reuse ids.
- Do not change ids after creation.

Examples:

    CC-0001-missing-owner-check.md
    CC-0002-stack-buffer-overflow-in-parser.md
    CC-0003-unsafe-yaml-deserialization.md
    CC-0004-command-injection-via-backup-name.md

## Required frontmatter

Every finding must start with YAML frontmatter.

Minimum fields:

    ---
    id: "CC-0001"
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
    created_at: "YYYY-MM-DD"
    updated_at: "YYYY-MM-DD"
    ---

## Status values

Use only:

- `PENDING`
- `CONFIRMED`
- `EXPLOITED`
- `REJECTED`
- `DUPLICATE`

Do not invent additional status values.

## CWE classification

The `cwe` frontmatter field holds a list of CWE ids that best match the
vulnerability. Use the most specific id first; broader parents may
follow.

Example:

    cwe:
      - "CWE-121"
      - "CWE-805"

Rules:

- **Required** when the finding is `EXPLOITED`.
- **Recommended** when the finding is `CONFIRMED`.
- Optional for `PENDING`, `REJECTED`, `DUPLICATE`.

Do not invent CWE ids. Use values from the official MITRE CWE catalog.

## Severity values

Use only:

- `CRITICAL`
- `HIGH`
- `MEDIUM`
- `LOW`
- `INFO`

Severity should reflect realistic impact, not just theoretical bug class.

## Confidence values

Use only:

- `LOW`
- `MEDIUM`
- `HIGH`
- `CONFIRMED`

Meaning:

- `LOW`: plausible but weak; assumptions are significant.
- `MEDIUM`: credible path exists, but important assumptions remain.
- `HIGH`: strong static evidence exists, but validation is still pending.
- `CONFIRMED`: validated with clear evidence.

A finding with confidence `CONFIRMED` must also have status `CONFIRMED` or `EXPLOITED`.

## Required sections

Every finding must include these sections:

    # Summary
    # Target context
    # Affected code
    # Vulnerability hypothesis
    # Source-to-sink reasoning
    # Attackability / trigger conditions
    # Impact
    # Validation plan
    # Counter-analysis
    # Validation result
    # Evidence
    # Exploitation Result
    # Demonstrated Impact
    # Root cause analysis
    # Data flow
    # Inputs and preconditions
    # Recording
    # Remediation idea
    # Notes

Do not omit sections. If a section is not yet complete, write `Pending.` and explain what is missing.

For `# Data flow`, when the bug is not input-driven (e.g. configuration
default, lifetime bug not driven by external input) write
`Not applicable.` and add a brief reason rather than `Pending.`.

The four sections `# Root cause analysis`, `# Data flow`,
`# Inputs and preconditions`, and `# Recording` are required to be filled
(not `Pending.`) when the finding reaches `EXPLOITED`. They may stay
`Pending.` for non-EXPLOITED findings.

`# Remediation idea` must include a corrected-code excerpt or a unified
diff for `CONFIRMED` and `EXPLOITED` findings. Keep the patch minimal.

## Quality bar

A valid finding must answer:

- What component is affected?
- Where is the relevant code?
- What input, state, or condition is attacker-controlled or externally influenced?
- What trust boundary is crossed?
- What dangerous sink or security decision is reached?
- Why existing controls may be insufficient?
- What is the realistic impact?
- How can the issue be validated?
- What evidence confirms or rejects it?

## Bad finding examples

Do not create vague findings like:

    Potential SQL injection may exist because the project uses SQL.

    There may be buffer overflows in the C code.

    Authentication could be insecure.

    This file looks dangerous.

    The code uses crypto and might be wrong.

These are not acceptable because they lack concrete affected code, attacker control, source-to-sink reasoning, impact, and validation plan.

## Good finding examples

Create precise findings like:

    User-controlled `sort` reaches raw SQL `ORDER BY` construction in
    `SearchRepository.BuildQuery()` without allowlist validation.

    The `archiveName` CLI argument is concatenated into a shell command in
    `BackupRunner.run()` and executed with `system()`.

    The HTTP handler `GET /documents/{id}` loads a document by id but does not
    check that the current tenant owns the document before returning it.

    The parser copies an attacker-controlled string into a fixed-size stack
    buffer using `strcpy()` in `parse_record()`.

## Source-to-sink reasoning

Prefer explicit source-to-sink reasoning when possible.

Describe:

1. Source of attacker-controlled input.
2. Propagation path.
3. Validation, normalization, or missing validation.
4. Trust boundary crossed.
5. Dangerous sink or security decision.
6. Preconditions.
7. Resulting impact.

If the issue is not source-to-sink based, use the closest equivalent model.

Examples:

- insecure default configuration,
- missing authorization check,
- unsafe cryptographic construction,
- memory lifetime issue,
- exposed secret,
- dangerous build/deployment behavior.

## Counter-analysis requirement

Every finding must include counter-analysis.

Counter-analysis should try to disprove the finding.

Look for:

- input validation,
- output encoding,
- authorization checks,
- framework-level protections,
- safe wrappers,
- type guarantees,
- unreachable code,
- impossible attacker control,
- non-security impact,
- duplicate findings,
- misleading filenames,
- comments or benchmark labels that may bias the analysis.

If counter-analysis has not been performed yet, write:

    Pending. This finding has not yet received an independent counter-analysis pass.

## Validation requirement

Every finding must include a validation plan.

The plan must be actionable.

Depending on the target, validation may involve:

- static proof,
- unit test,
- integration test,
- runtime reproduction,
- HTTP request,
- CLI invocation,
- crafted input file,
- configuration change,
- sanitizer output,
- crash reproduction,
- debugger trace,
- benchmark oracle comparison.

A finding may only be marked `CONFIRMED` when there is clear evidence.

Benchmark labels, filenames, comments, or directory names alone are not enough for confirmation.

## Evidence handling

For every finding id, evidence belongs under:

    itemdb/evidence/<finding-id>/

The evidence directory should contain a `README.md` when evidence is collected.

Evidence examples:

- `commands.txt`
- `output.txt`
- `sanitizer.log`
- `crash.txt`
- `request.http`
- `response.txt`
- `exploit.py`
- `payload.bin`
- `test-output.txt`
- `debugger-notes.md`
- `db-state.sql`

The finding should reference the evidence files by path.

## Updating findings

When updating a finding:

- update `updated_at`,
- preserve the id,
- preserve human review notes,
- append evidence instead of deleting useful context,
- do not erase counter-analysis unless replacing it with a stronger version,
- move the file to the correct status directory when status changes.

## Duplicate findings

If a finding is duplicate:

- move it to `itemdb/findings/DUPLICATE/`,
- set `status: "DUPLICATE"`,
- reference the canonical finding id in the body,
- preserve any useful additional evidence or notes.

## Rejected findings

If a finding is rejected:

- move it to `itemdb/findings/REJECTED/`,
- set `status: "REJECTED"`,
- explain clearly why it was rejected.

Common rejection reasons:

- input is not attacker-controlled,
- code path is unreachable,
- existing validation is sufficient,
- authorization is enforced elsewhere,
- impact is not security-relevant,
- finding is based only on label or filename,
- duplicate of another finding,
- target is out of scope.

## Confirmed findings

If a finding is confirmed:

- move it to `itemdb/findings/CONFIRMED/`,
- set `status: "CONFIRMED"`,
- set `confidence: "CONFIRMED"`,
- update `validation.status`,
- summarize the evidence,
- reference evidence files,
- explain limitations.

Do not mark a finding confirmed without evidence.

## Exploited findings

If a confirmed finding has a demonstrated proof-of-concept exploit showing real-world impact:

- move it to `itemdb/findings/EXPLOITED/`,
- set `status: "EXPLOITED"`,
- set `confidence: "CONFIRMED"`,
- populate `cwe` (required for EXPLOITED) with one or more CWE ids,
- update `exploitation.status` to `"DEMONSTRATED"`,
- fill `exploitation.impact_demonstrated` with a description of the impact achieved,
- fill `exploitation.exploit_type` with the type of exploit (e.g., `buffer_overflow_rce`, `sqli_data_dump`),
- record `exploitation.severity_before` and `exploitation.severity_after`,
- adjust `severity` if the demonstrated impact warrants it,
- update `# Exploitation Result` with details of the exploit,
- update `# Demonstrated Impact` with a plain-language narrative,
- fill `# Root cause analysis`, `# Data flow` (or `Not applicable.`),
  `# Inputs and preconditions`, `# Recording`, and `# Remediation idea`
  (with corrected-code excerpt or unified diff),
- store exploitation artifacts under `itemdb/evidence/<finding-id>/exploits/`,
- store the demonstration recording (when produced) under
  `itemdb/evidence/<finding-id>/exploits/recordings/`. Mandatory effort
  when a working PoC exists; document absence in `exploits/README.md`
  Limitations and the finding's `# Recording` section if not feasible.

If exploitation is not feasible, the finding stays in `CONFIRMED/` with `exploitation.status` set to `"NOT_FEASIBLE"` and a documented explanation.

Valid `exploitation.status` values:

- `NOT_STARTED` -- exploitation has not been attempted.
- `IN_PROGRESS` -- exploitation is underway.
- `DEMONSTRATED` -- a working PoC demonstrates concrete impact.
- `NOT_FEASIBLE` -- exploitation was attempted but is not feasible in the sandbox.
