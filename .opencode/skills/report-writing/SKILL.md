# Report Writing Skill

Use this skill during CodeCome Phase 6: reporting.

The goal of reporting is to turn reviewed findings and evidence into clear Markdown reports.

Reports must be useful for both technical reviewers and decision makers.

## Purpose

A CodeCome report should summarize:

- what was reviewed,
- how it was reviewed,
- what was found,
- what was confirmed,
- what was rejected or left unresolved,
- what evidence exists,
- what limitations apply,
- what should happen next.

## Inputs

Read:

- `AGENTS.md`
- `codecome.yml`
- `itemdb/README.md`
- `itemdb/index.md`
- `itemdb/notes/`
- `itemdb/findings/EXPLOITED/`
- `itemdb/findings/CONFIRMED/`
- `itemdb/findings/PENDING/`
- `itemdb/findings/REJECTED/`
- `itemdb/findings/DUPLICATE/`
- `itemdb/evidence/`
- If present, `itemdb/notes/threat-model.md` — operational threat model with attacker capabilities, non-capabilities, trust boundaries, existing controls, assets, and open assumptions. Use to ground Methodology, Scope, and Limitations sections without duplicating the full artifact.

## Outputs

Write reports under:

    itemdb/reports/

Recommended reports:

    itemdb/reports/technical-report.md
    itemdb/reports/executive-summary.md
    itemdb/reports/validation-summary.md

For the PoC, a single report is acceptable:

    itemdb/reports/report.md

Note:

- `make report` produces a lightweight local summary report.
- `make phase-6` is the full reporting workflow and should be preferred when a human-reviewable narrative report is needed.

## Report types

### Technical report

Audience:

- developers,
- security engineers,
- reviewers,
- maintainers.

Include technical detail, affected code, evidence paths, validation methods, and remediation guidance.

### Executive summary

Audience:

- managers,
- product owners,
- project stakeholders.

Include concise risk summary, confirmed impact, limitations, and recommended next steps.

Avoid excessive implementation detail.

### Validation summary

Audience:

- security engineers,
- PoC operators,
- reviewers.

Include validation attempts, confirmed issues, rejected issues, unresolved issues, and environment limitations.

## Main report structure

Use this structure for `itemdb/reports/report.md`:

    # CodeCome Report

    # Executive summary

    # Target overview

    # Methodology

    # Scope

    # Findings summary

    # Exploited findings

    # Confirmed findings

    # Findings needing validation

    # Rejected findings

    # Duplicate findings

    # Evidence summary

    # Limitations

    # Recommended next steps

    # Appendix

## Finding summary table

Include a table like:

    | ID | Status | Severity | Confidence | CWE | Target area | Title | Evidence | Recording |
    |---|---|---|---|---|---|---|---|---|
    | CC-0001 | EXPLOITED | HIGH | CONFIRMED | CWE-121 | parser | Missing owner check | itemdb/evidence/CC-0001/ | itemdb/evidence/CC-0001/exploits/recordings/README.md |

Cell rules:

- `CWE`: list one or more CWE ids; use `—` when none.
- `Recording`: relative path to the recordings README or to the GIF;
  use `—` when no recording exists.

Only include useful columns. Drop `Confidence` if every row has the same
value, but keep `CWE` and `Recording` so reviewers can scan them.

## Recording handling

Reference recordings by relative path. Never embed binary blobs (`.gif`,
`.mp4`) inline in the Markdown; link to them instead and let the
recordings README document play instructions.

Examples:

    Recording: [recordings/README.md](../evidence/CC-0001/exploits/recordings/README.md)
    Cast: ../evidence/CC-0001/exploits/recordings/exploit.cast
    GIF: ../evidence/CC-0001/exploits/recordings/exploit.gif

If a finding has no recording, write `—` in the table cell and explain
the absence briefly in the per-finding section.

## Vulnerable-code excerpts

For each CONFIRMED/EXPLOITED finding, include a short excerpt (≤ ~15
lines) of the vulnerable code, fenced and annotated with a `file:line`
header. Examples:

    ```c
    // src/parser/buf.c:42-58
    void parse_record(char *src) {
        char dst[50];
        memcpy(dst, src, 100);  // attacker-controlled length
        ...
    }
    ```

Rules:

- Keep excerpts focused on the vulnerable construct; do not paste whole
  files.
- Always include a `file:line` header so reviewers can navigate to the
  source.
- Redact any secrets, tokens, or production identifiers.
- When the finding spans multiple files, include the most relevant
  excerpt and reference the others by path.

## Exploited finding section

For each exploited finding, include:

- id,
- title,
- severity (note if adjusted from original),
- CWE id(s),
- impact demonstrated,
- exploit type,
- affected area,
- affected files,
- summary,
- vulnerable code excerpt (≤ ~15 lines, fenced, with `file:line` header),
- root cause analysis (1–3 sentences referencing the finding's `# Root cause analysis` section),
- demonstrated impact narrative,
- evidence and exploitation artifact references,
- recording references (cast / gif / optional mp4 / `reproduce.sh` / recordings README, all by relative path; or an absence note if no recording was produced),
- remediation idea (with corrected-code excerpt or unified diff from the finding).

## Confirmed finding section

For each confirmed finding, include:

- id,
- title,
- severity,
- confidence,
- CWE id(s) (if known),
- category,
- affected area,
- affected files,
- summary,
- vulnerable code excerpt (≤ ~15 lines, fenced, with `file:line` header),
- root cause analysis (1–3 sentences when the finding has a populated `# Root cause analysis`; otherwise omit gracefully),
- impact,
- validation method,
- evidence references,
- remediation idea.

Do not paste huge logs into the report.

Link to evidence files instead.

## Needs-validation section

For findings still under `PENDING`, summarize:

- id,
- title,
- current confidence,
- why it remains plausible,
- what validation is needed,
- blockers.

## Rejected section

For rejected findings, summarize:

- id,
- title,
- rejection reason,
- whether any related follow-up remains.

Do not over-emphasize rejected findings in executive reports.

## Duplicate section

For duplicates, summarize:

- duplicate id,
- canonical id,
- short reason.

## Evidence references

Evidence should be referenced by relative path.

Examples:

    itemdb/evidence/CC-0001/README.md
    itemdb/evidence/CC-0001/request.http
    itemdb/evidence/CC-0001/sanitizer.log

Do not include secrets.

Do not include unnecessary full payloads in executive summaries.

## Limitations

Always include limitations.

Examples:

- source-only review,
- incomplete build environment,
- missing credentials,
- missing test data,
- limited runtime validation,
- benchmark target instead of production app,
- manual review not yet performed,
- only one validation worker used,
- selected scope only,
- agent output not independently verified.

## Risk language

Be precise.

Prefer:

    The finding was confirmed in the local sandbox.

over:

    The application is definitely exploitable in production.

Prefer:

    The static path suggests a missing authorization check.

over:

    This is a critical vulnerability.

## Severity handling

Do not inflate severity.

Severity should reflect:

- realistic impact,
- required privileges,
- reachability,
- affected asset,
- exploit complexity,
- whether validation confirmed the issue,
- target context.

## Markdown style

Use clean Markdown.

Prefer:

- headings,
- short paragraphs,
- tables for summaries,
- bullet lists for evidence and remediation,
- relative paths.

Avoid:

- huge pasted logs,
- excessive prose,
- unsupported claims,
- raw terminal dumps in the main report,
- mixing confirmed and hypothetical issues without labels.

## Report freshness

Reports are snapshots.

Include:

- report date,
- target name,
- source path,
- run/phase context if available.

## Completion checklist

Before finishing a report:

- exploited findings (with demonstrated impact) are highlighted first,
- confirmed findings are summarized,
- open findings are clearly marked as not confirmed,
- rejected findings are not presented as vulnerabilities,
- evidence paths are included,
- limitations are included,
- next steps are actionable,
- Markdown is readable in GitHub/Gitea.
