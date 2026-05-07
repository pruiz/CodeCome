# CodeCome ItemDB

`itemdb/` is the file-based database used by CodeCome.

It stores reconnaissance notes, vulnerability findings, validation evidence, reports, and generated indexes.

The initial PoC intentionally uses plain Markdown files instead of a database.

## Layout

    itemdb/
    ├── README.md
    ├── index.md
    ├── notes/
    ├── findings/
    │   ├── PENDING/
    │   ├── CONFIRMED/
    │   ├── EXPLOITED/
    │   ├── REJECTED/
    │   └── DUPLICATE/
    ├── evidence/
    └── reports/

## Notes

Reconnaissance notes are stored under:

    itemdb/notes/

Expected files include:

    target-profile.md
    attack-surface.md
    build-model.md
    execution-model.md
    trust-boundaries.md
    data-flow.md
    validation-model.md
    interesting-files.md
    security-assumptions.md

These files describe the target model and should be produced during Phase 1.

## Findings

Findings are stored under:

    itemdb/findings/

Each finding is a Markdown file with YAML frontmatter.

Findings should be named using this pattern:

    CC-0001-short-title.md
    CC-0002-short-title.md
    CC-0003-short-title.md

Use lowercase, hyphen-separated slugs after the id.

## Finding status directories

### `PENDING/`

Candidate findings that appear plausible but still require validation.

### `CONFIRMED/`

Findings that have been validated with clear evidence.

### `EXPLOITED/`

Confirmed findings with a demonstrated proof-of-concept exploit showing real-world impact.

Exploitation artifacts are stored under `itemdb/evidence/<finding-id>/exploits/`.

### `REJECTED/`

Findings that were disproven, are not security-relevant, are unreachable, lack attacker control, or are otherwise not actionable.

### `DUPLICATE/`

Findings that are already covered by another finding.

A duplicate finding should reference the canonical finding id.

## Evidence

Evidence is stored under:

    itemdb/evidence/<finding-id>/

Example:

    itemdb/evidence/CC-0001/
    ├── README.md
    ├── commands.txt
    ├── output.txt
    ├── sanitizer.log
    ├── request.http
    ├── response.txt
    ├── exploit.py
    └── exploits/
        ├── README.md
        ├── exploit.py
        ├── payload.bin
        └── captured-output.txt

Evidence should be enough for a human reviewer to understand how the finding was confirmed or rejected.

## Reports

Reports are stored under:

    itemdb/reports/

Reports should be Markdown files.

Examples:

    itemdb/reports/technical-report.md
    itemdb/reports/executive-summary.md
    itemdb/reports/validation-summary.md

## Index

`itemdb/index.md` is a generated or manually maintained summary of findings.

It should include:

- finding id,
- title,
- status,
- severity,
- confidence,
- affected area,
- validation status,
- evidence link.

## Rules

1. Keep findings precise.
2. Keep evidence close to the finding id.
3. Do not mark findings as `CONFIRMED` without evidence.
4. Do not delete rejected findings; move them to `REJECTED/`.
5. Do not overwrite human review notes.
6. Prefer Markdown that is easy to review in Git diffs.
