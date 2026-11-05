# CodeCome Phase 2: Vulnerability Hypothesis Generation

You are performing CodeCome Phase 2: vulnerability hypothesis generation.

## Required reading

Read the following files (all paths are relative to the project/workspace root):

- `AGENTS.md`
- `codecome.yml`
- `templates/finding.md`
- `.opencode/agents/auditor.md`
- `.opencode/skills/finding-format/SKILL.md`
- `.opencode/skills/source-recon/SKILL.md`
- all relevant files under `itemdb/notes/`
- `itemdb/notes/threat-model.md` — operational threat model from Phase 1b: assets, attacker model, trust-boundary summary, existing controls, abuse-path themes, risk calibration, and open assumptions.

Use additional target-specific skills only if they clearly apply.

Examples:

- `.opencode/skills/c-cpp-security/SKILL.md`
- `.opencode/skills/juliet-benchmark/SKILL.md`

## Domain companion skills

Beyond the target-type skills above, load the domain companion skills that apply. Use `suggested_skills` in `itemdb/notes/file-risk-index.yml` and the Phase 1 notes to decide which ones are relevant:

- `.opencode/skills/web-protocol-auth/SKILL.md`
- `.opencode/skills/core-attack-classes/SKILL.md`
- `.opencode/skills/memory-safety-binary/SKILL.md`
- `.opencode/skills/data-isolation-lifecycle/SKILL.md`
- `.opencode/skills/resource-exhaustion/SKILL.md`
- `.opencode/skills/protocols-messaging-security/SKILL.md`
- `.opencode/skills/supply-chain-security/SKILL.md`
- `.opencode/skills/cloud-deployment-security/SKILL.md`
- `.opencode/skills/client-side-security/SKILL.md`
- `.opencode/skills/desktop-mobile-ipc/SKILL.md`
- `.opencode/skills/ai-llm-security/SKILL.md`

Load only the companions that clearly apply to the target; use their checklists to widen the vulnerability classes you consider, not to create findings from labels alone.

## Target & Scope

Analyze the source tree under:

    ./src

Use Phase 1 reconnaissance notes under:

    itemdb/notes/

If `itemdb/notes/file-risk-index.yml` exists, use it to guide your attention to high-risk areas. **CRITICAL RULE:** In this global Phase 2 pass, focus on **macro-level vulnerabilities**: cross-component trust boundaries, architectural flaws, project-wide logic, and broad attack surfaces.

Use `itemdb/notes/threat-model.md` to prioritize hypotheses around assets, attacker capabilities, explicit non-capabilities, existing controls, and abuse-path themes. Do not convert an abuse-path theme into a finding unless you identify a concrete, repository-backed vulnerable path with attacker control, trust-boundary crossing, security-relevant impact, and an actionable validation plan. 

Do NOT perform exhaustive line-by-line deep dives of individual files. Leave deep, line-by-line vulnerability hunting for the optional `make sweep` tool. Your goal here is to establish the broad, high-impact hypotheses that span the architecture.

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

## Fingerprint

Every new finding must set the `fingerprint` frontmatter field to a stable root-cause identifier, as described in `.opencode/skills/finding-format/SKILL.md`:

    <class>:<path>#<symbol>[:<qualifier>]

Example:

    authz:src/api/orders.py#get:missing-owner-check

Before creating a finding, search the `fingerprint` of every finding under `itemdb/findings/` (all status directories). If the same fingerprint already exists, update or extend that finding instead of creating a new one. Two live findings must not share a fingerprint.

## Variant search

When you identify a root cause, search the target for variants of the same pattern (same unsafe sink, same missing check, same trust assumption) in other files, handlers, and entry points. Record variants in the existing finding (`files`, `symbols`, `entry_points`, `# Affected code`) rather than creating a new finding, unless the exploit path, impact, or remediation differs materially.

## Semantic metadata

Populate existing frontmatter fields as precisely as possible:

- `files`
- `symbols`
- `entry_points`
- `sources`
- `sinks`
- `trust_boundary`
- `assets_at_risk`
- `category`
- `target_area`

These fields are used by Phase 3 for semantic deduplication. Two findings are likely duplicates when they share the same root cause, source, sink, affected security property, and validation path, even if they were discovered from different files.

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

Avoid duplicate root causes (compare `fingerprint` first, then semantic fields).

Create separate findings only when the affected component, exploit path, impact, or remediation differs.

## Optional Deep Sweeps

This global Phase 2 can be complemented with the optional deep-dive sweep mode:

    make sweep
    make sweep FILE=src/path/to/high-risk-file.ext

This mode is intentionally sequential by default so the operator can observe the model's reasoning and stop between files. Mention this tool in your final summary if there are high-risk files you skipped over during this global pass.

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
- highest-risk areas reviewed,
- threat-model themes consumed,
- assumptions from `threat-model.md` that materially influenced hypotheses,
- abuse-path themes not converted into findings and why,
- high-risk files left for optional deep sweeps,
- most important assumptions,
- recommended next phase,
- open questions for the user (same content as in the run summary),
- re-run prompt hints (same content as in the run summary; use `PROMPT_EXTRA` / `PROMPT_EXTRA_FILE` snippets),
- files created or modified.

## Run summary

Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-2-summary-YYYY-MM-DD-HHMMSS.md

You MUST fill in both sections. Questions must be complete, self-contained sentences ending in `?` — avoid terse noun phrases. Hints must use actual `PROMPT_EXTRA` or `PROMPT_EXTRA_FILE` snippets.
