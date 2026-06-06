# CodeCome Prompts

This directory contains reusable prompts for running the CodeCome workflow with OpenCode.

Each prompt corresponds to one workflow phase.

## Prompts

    phase-1a-profile.md
    phase-1b-sandbox.md
    phase-1c-recon.md
    phase-2-audit.md
    phase-3-review.md
    phase-4-validate.md
    phase-5-exploit.md
    phase-6-report.md

## Recommended usage

Use `make` targets for the simplest workflow:

    make venv                     # Create/update repo-local virtualenv
    make phase-1                  # Reconnaissance
    make phase-2                  # Hypothesis generation
    make phase-3                  # Counter-analysis
    make phase-4 FINDING=CC-0001  # Validate one finding
    make phase-5 FINDING=CC-0001  # Develop exploit for one finding
    make phase-6                  # Reporting
    make validate-all             # Validate all PENDING findings
    make exploit-all              # Exploit all CONFIRMED findings

Each `make` target checks readiness gates before invoking the corresponding agent.

`make phase-*` targets use CodeCome's styled wrapper by default. Manual `opencode run` commands below remain the raw, direct path.

If `.venv/` is missing or out of date, the `make` targets will stop and tell you to run `make venv`.

## Manual invocation

If you prefer direct invocation:

### Phase 1: reconnaissance

Use `make phase-1` to run the full reconnaissance workflow (Phase 1a, Phase 1b sandbox, CodeQL enrichment, Phase 1c).

    make phase-1

Or invoke subphases manually:

    opencode run --agent recon "$(cat prompts/phase-1a-profile.md)"
    opencode run --agent recon "$(cat prompts/phase-1b-sandbox.md)"
    opencode run --agent recon "$(cat prompts/phase-1c-recon.md)"

Creates or updates target reconnaissance notes under:

    itemdb/notes/

### Phase 2: hypothesis generation

    opencode run --agent auditor "$(cat prompts/phase-2-audit.md)"

Creates candidate findings under:

    itemdb/findings/PENDING/

### Phase 3: counter-analysis

    opencode run --agent reviewer "$(cat prompts/phase-3-review.md)"

Reviews candidate findings and may move findings to:

    itemdb/findings/REJECTED/
    itemdb/findings/DUPLICATE/

### Phase 4: validation

Validate one finding at a time.

    opencode run --agent validator "$(sed 's#FINDING_PATH_OR_ID#CC-0001#g' prompts/phase-4-validate.md)"

Validation stores evidence under:

    itemdb/evidence/<finding-id>/

and may move findings to:

    itemdb/findings/CONFIRMED/
    itemdb/findings/REJECTED/

### Phase 5: exploit development

Develop an exploit for one confirmed finding by id.

    opencode run --agent exploiter "$(sed 's#FINDING_PATH_OR_ID#CC-0001#g' prompts/phase-5-exploit.md)"

Exploitation artifacts are stored under:

    itemdb/evidence/<finding-id>/exploits/

When the PoC works, a demonstration recording is also produced under
`itemdb/evidence/<finding-id>/exploits/recordings/`. EXPLOITED findings
must carry CWE id(s) and populated root-cause / data-flow /
preconditions / recording / remediation-diff sections.

Findings may move to:

    itemdb/findings/EXPLOITED/

`make exploit-all` skips findings already marked with `exploitation.status: NOT_FEASIBLE`.

### Phase 6: reporting

    opencode run --agent reporter "$(cat prompts/phase-6-report.md)"

A basic report can also be generated locally without AI:

    make report

Default report path:

    itemdb/reports/report.md

This local report is a lightweight snapshot. Use `make phase-6` for the
full reporting pass. Phase 6 surfaces `CWE` and `Recording` columns,
vulnerable-code excerpts, and root-cause summaries; recordings are
referenced by relative path (binaries are never embedded).

## Notes

- Prompts assume they are run from the repository root.
- Prompts are intentionally target-agnostic.
- Target-specific behavior should come from skills under `.opencode/skills/`.
- Do not present unvalidated hypotheses as confirmed vulnerabilities.
- `make check` warns when optional recording tools (`asciinema`, `agg`,
  `ffmpeg`, `Xvfb`) are missing; warnings do not fail the gate.

## License

CodeCome is dual-licensed under your choice of:

- GNU General Public License version 3 or later (`GPL-3.0-or-later`), or
- GNU Affero General Public License version 3 or later (`AGPL-3.0-or-later`).

SPDX expression: `GPL-3.0-or-later OR AGPL-3.0-or-later`.

The files under `templates/sandboxes/` are an exception: they are
licensed under the **MIT License** so they can be copied into user
workspaces without imposing copyleft obligations on those user
projects.

See `LICENSE`, `AGPL-LICENSE`, `templates/sandboxes/LICENSE`, and
`NOTICE`. Contributions are accepted under the terms described in
`CONTRIBUTING.md`.

Copyright (C) 2025-2026 Pablo Ruiz García &lt;pablo.ruiz@gmail.com&gt;.
