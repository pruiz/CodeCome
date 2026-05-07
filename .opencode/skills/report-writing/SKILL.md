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

    | ID | Status | Severity | Confidence | Title | Evidence |
    |---|---|---|---|---|---|
    | CC-0001 | CONFIRMED | HIGH | CONFIRMED | Missing owner check | itemdb/evidence/CC-0001/ |

Only include useful columns.

## Confirmed finding section

For each confirmed finding, include:

- id,
- title,
- severity,
- confidence,
- category,
- affected area,
- affected files,
- summary,
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
