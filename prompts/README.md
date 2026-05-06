# CodeCome Prompts

This directory contains reusable prompts for running the CodeCome workflow with OpenCode.

Each prompt corresponds to one workflow phase.

## Prompts

    phase-1-recon.md
    phase-2-audit.md
    phase-3-review.md
    phase-4-validate.md
    phase-5-report.md

## Phase 1: reconnaissance

    opencode run "$(cat prompts/phase-1-recon.md)"

Creates or updates target reconnaissance notes under:

    itemdb/notes/

## Phase 2: hypothesis generation

    opencode run "$(cat prompts/phase-2-audit.md)"

Creates candidate findings under:

    itemdb/findings/NEEDS_VALIDATION/

## Phase 3: counter-analysis

    opencode run "$(cat prompts/phase-3-review.md)"

Reviews candidate findings and may move findings to:

    itemdb/findings/REJECTED/
    itemdb/findings/DUPLICATE/

## Phase 4: validation

Validate one finding at a time.

Example:

    opencode run "$(sed 's#FINDING_PATH_OR_ID#CC-0001#g' prompts/phase-4-validate.md)"

Alternative pipe form:

    sed 's#FINDING_PATH_OR_ID#CC-0001#g' prompts/phase-4-validate.md | opencode run

Validation stores evidence under:

    itemdb/evidence/<finding-id>/

and may move findings to:

    itemdb/findings/CONFIRMED/
    itemdb/findings/REJECTED/

## Phase 5: reporting

    opencode run "$(cat prompts/phase-5-report.md)"

A basic report can also be generated locally:

    make report

Default report path:

    itemdb/reports/report.md

## Notes

- Prompts assume they are run from the repository root.
- Prompts are intentionally target-agnostic.
- Target-specific behavior should come from skills under `.opencode/skills/`.
- Do not present unvalidated hypotheses as confirmed vulnerabilities.

