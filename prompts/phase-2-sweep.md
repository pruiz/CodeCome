# CodeCome Phase 2: Sweep Mode

You are performing CodeCome Phase 2 (hypothesis generation) in file-scoped sweep mode.

This is the same Phase 2 described in the standard `prompts/phase-2-audit.md` prompt, but with a narrower scope: instead of hunting for macro-level architectural flaws across the entire codebase, you focus on a single high-risk file from `itemdb/notes/file-risk-index.yml` with intense, line-by-line analysis. Read immediate dependencies needed to establish reachability and data flow, but avoid expanding the run into a full-project audit.

All Phase 2 expectations apply: produce durable findings under `itemdb/findings/PENDING/`, follow frontmatter quality rules, deduplicate against existing findings, run `make frontmatter`, and write a Phase 2 run summary.

## Required reading

Read the following files (all paths are relative to the project/workspace root):

- `AGENTS.md`
- `codecome.yml`
- `templates/finding.md`
- `.opencode/agents/auditor.md`
- `.opencode/skills/finding-format/SKILL.md`
- `.opencode/skills/source-recon/SKILL.md`
- all relevant files under `itemdb/notes/`
- existing findings under `itemdb/findings/`

Use additional target-specific skills only if they clearly apply.

## CodeQL signals (conditional)

If `itemdb/codeql/last-run-manifest.yml` exists, read its `health` block and `run_id`.
When `health.usable` is `true`, read:
- `itemdb/codeql/runs/<run_id>/normalized/alerts.yml`
- `itemdb/codeql/runs/<run_id>/normalized/file-signals.yml`
as enrichment for the target file. When
`health.usable` is `false`, the CodeQL run did not produce trustworthy
output — do not import its signals.

## Target file

Analyze this target file:

    FILE_PATH_OR_ID

## Scope rules

Primary focus:

- the target file,
- functions/classes/routes/types defined in the target file.

**CRITICAL RULE:** You MUST read imported dependencies, models, configuration, or routing files to establish complete context and prove source-to-sink reachability. Do not analyze the target file in isolation if it relies on external logic or if you cannot determine if the input is actually attacker-controlled.

Avoid drifting into a full-project audit. If you find a promising adjacent file, mention it in the final response as a recommended follow-up sweep instead of expanding the current run indefinitely.

## Goal

Create precise vulnerability hypotheses as Markdown findings under:

    itemdb/findings/PENDING/

Do not validate findings in this phase.

Do not mark anything as confirmed.

## Required output

For each candidate finding, create a Markdown file using the CLI tool:

    make findings-create TITLE="Short descriptive title"

This command uses the template and automatically assigns the next available ID. Then edit the generated file to fill in the finding details.

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

## Semantic deduplication metadata

When creating or updating findings, populate existing frontmatter fields as precisely as possible:

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

## Avoid duplicates

Before creating each finding, check existing findings under:

    itemdb/findings/

Avoid duplicate root causes. Create separate findings only when the affected component, exploit path, impact, or remediation differs.

## Counter-analysis

For new findings, include this initial text in the `# Counter-analysis` section:

    Pending. This finding requires an independent counter-analysis pass.

## Validation result

For new findings, include this initial text in the `# Validation result` section:

    Pending validation.

## Evidence

For new findings, include this initial text in the `# Evidence` section:

    Pending.

## Final response

Run `make frontmatter` to ensure all created findings have valid frontmatter and fix any reported errors before finishing.

**Pathing rule for outputs:** When writing any scratch file, summary, or temporary output, use workspace-relative paths such as `tmp/` or `runs/`. **Never use the absolute path `/tmp/`** — it will be rejected by the sandbox.

At the end, summarize in your response (or write a brief run summary under `runs/`):

- target file reviewed,
- number of findings created,
- ids and titles,
- adjacent files worth sweeping next,
- important assumptions,
- recommended next phase,
- open questions for the user (same content as in the run summary),
- re-run prompt hints (same content as in the run summary; use `PROMPT_EXTRA` / `PROMPT_EXTRA_FILE` snippets),
- files created or modified.

Print a concise end-of-run summary to the screen in addition to writing the durable run summary. The operator should see key results immediately without opening the summary file.

## Run summary

Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-2-summary-sweep-<slug>-YYYY-MM-DD-HHMMSS.md

Replace `<slug>` with a short sanitised version of the target file path
(e.g. `runs/phase-2-summary-sweep-src-app-controllers-upload-php-2026-06-09-143022.md`).

You MUST fill in both sections. Questions must be complete, self-contained sentences ending in `?` — avoid terse noun phrases. Hints must use actual `PROMPT_EXTRA` or `PROMPT_EXTRA_FILE` snippets.
