# CodeCome Phase 2: Vulnerability Hypothesis Generation

You are performing CodeCome Phase 2: vulnerability hypothesis generation.

## Required reading

Read:

- `AGENTS.md`
- `codecome.yml`
- `templates/finding.md`
- `.opencode/agents/auditor.md`
- `.opencode/skills/finding-format/SKILL.md`
- `.opencode/skills/source-recon/SKILL.md`
- all relevant files under `itemdb/notes/`

Use additional target-specific skills only if they clearly apply.

Examples:

- `.opencode/skills/c-cpp-security/SKILL.md`
- `.opencode/skills/juliet-benchmark/SKILL.md`

## Target

Analyze the source tree under:

    ./src

Use Phase 1 reconnaissance notes under:

    itemdb/notes/

## Goal

Create precise vulnerability hypotheses as Markdown findings under:

    itemdb/findings/PENDING/

Do not validate findings in this phase.

Do not mark anything as confirmed.

## Required output

For each candidate finding, create a Markdown file using the CLI tool:

    make findings-create TITLE="Short descriptive title"

This command uses the template and automatically assigns the next available ID.
Then, edit the generated file to fill in the finding details.

Do not manually copy `templates/finding.md` or pick IDs yourself.

## Finding requirements

Only create a finding when you can identify:

- affected component,
- affected file or symbol,
- attacker-controlled or externally influenced input/state/configuration,
- dangerous sink or security decision,
- trust boundary or security property,
- plausible impact,
- actionable validation plan.

Each finding must include:

- concrete affected code,
- source-to-sink or equivalent reasoning,
- attackability / trigger conditions,
- realistic impact,
- validation plan,
- counter-analysis placeholder,
- evidence placeholder.

## Quality bar

Do not create vague findings.

Bad examples:

    Potential SQL injection may exist because the project uses SQL.

    There may be buffer overflows in the C code.

    Authentication could be insecure.

    This file looks dangerous.

Good examples:

    User-controlled `sort` reaches raw SQL `ORDER BY` construction in
    `SearchRepository.BuildQuery()` without allowlist validation.

    The parser copies an attacker-controlled length into a fixed-size stack
    buffer using `memcpy()` without checking the destination size.

    The document download handler loads an object by id but does not check
    that the current tenant owns the object before returning it.

## Confidence

Use:

- `LOW`
- `MEDIUM`
- `HIGH`

Do not use:

- `CONFIRMED`

## Status

All new findings must use:

    status: "PENDING"

## Counter-analysis

For new findings, include this initial text in the `# Counter-analysis` section:

    Pending. This finding requires an independent counter-analysis pass.

## Validation result

For new findings, include this initial text in the `# Validation result` section:

    Pending validation.

## Evidence

For new findings, include this initial text in the `# Evidence` section:

    Pending.

## Avoid duplicates

Before creating each finding, check existing findings under:

    itemdb/findings/

Avoid duplicate root causes.

Create separate findings only when the affected component, exploit path, impact, or remediation differs.

## Benchmark targets

If the target is a benchmark corpus:

- do not rely only on filenames, directory names, comments, function names, or benchmark labels,
- explain the code-level weakness,
- distinguish vulnerable and safe variants when applicable,
- include benchmark label analysis when useful,
- keep confidence low if the issue is mostly inferred from labels.

## Final response

Run `make frontmatter` to ensure all created findings have valid frontmatter and fix any reported errors before finishing.

At the end, summarize:

- number of findings created,
- ids and titles,
- most important assumptions,
- recommended next phase,
- files created or modified.
