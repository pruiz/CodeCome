# CodeCome Agent Instructions

You are working inside a CodeCome vulnerability research workspace.

CodeCome is an AI-assisted vulnerability research workflow. Its purpose is to help inspect source code, identify attack surfaces, create structured vulnerability hypotheses, perform counter-analysis, validate findings inside a sandbox, and produce reviewable Markdown reports.

## Prime directive

Produce durable artifacts.

Important security claims must be written to files under `itemdb/`, not left only in chat history or transient run output.

## Workspace layout

- `src/`: target source code to audit.
- `sandbox/`: sandboxed execution and validation environment.
- `itemdb/`: file-based finding database, notes, reports, and evidence.
- `itemdb/notes/`: reconnaissance notes and target model.
- `itemdb/findings/NEEDS_VALIDATION/`: candidate findings requiring validation.
- `itemdb/findings/CONFIRMED/`: validated findings with evidence.
- `itemdb/findings/REJECTED/`: disproven or non-actionable findings.
- `itemdb/findings/DUPLICATE/`: duplicate findings.
- `itemdb/evidence/`: validation evidence, grouped by finding id.
- `itemdb/reports/`: generated Markdown reports.
- `runs/`: run prompts, summaries, and transcripts when available.
- `templates/`: required Markdown templates.
- `tools/`: helper scripts.
- `.opencode/agents/`: specialized agent definitions.
- `.opencode/skills/`: reusable skills.

## General rules

1. Do not modify target source code under `src/` unless explicitly instructed.
2. Prefer reading and analyzing before writing.
3. Do not create vague findings.
4. Do not mark a finding as confirmed without evidence.
5. Always distinguish hypothesis from confirmed vulnerability.
6. Always include counter-analysis for every finding.
7. Always include a validation plan for every finding.
8. Store validation evidence under `itemdb/evidence/<finding-id>/`.
9. Keep findings reviewable by humans.
10. Use precise file paths, function names, symbols, routes, commands, or configuration keys whenever possible.
11. If a target-specific skill applies, use it, but keep the core workflow target-agnostic.
12. Do not rely only on filenames, comments, benchmark labels, or directory names to claim a vulnerability.

## Allowed write locations

Unless explicitly instructed otherwise, write only under:

- `itemdb/`
- `runs/`
- `sandbox/`
- `templates/`
- `tools/`
- `.opencode/`

Do not write into `src/` except for temporary instrumentation when explicitly authorized.

## Target-agnostic mindset

The target under `src/` may be:

- a web application,
- a backend service,
- a CLI tool,
- a library,
- a benchmark corpus,
- infrastructure-as-code,
- a mobile project,
- a desktop app,
- a firmware tree,
- or a mixed repository.

During reconnaissance, infer the target model before reporting vulnerabilities.

## Core phases

### Phase 1: Target reconnaissance

Goal: understand the target.

Create or update these files:

- `itemdb/notes/target-profile.md`
- `itemdb/notes/attack-surface.md`
- `itemdb/notes/build-model.md`
- `itemdb/notes/execution-model.md`
- `itemdb/notes/trust-boundaries.md`
- `itemdb/notes/data-flow.md`
- `itemdb/notes/validation-model.md`
- `itemdb/notes/interesting-files.md`
- `itemdb/notes/security-assumptions.md`

Do not create findings during reconnaissance unless there is an extremely obvious, high-confidence, security-relevant issue.

### Phase 2: Hypothesis generation

Goal: create precise candidate findings.

Write findings under:

- `itemdb/findings/NEEDS_VALIDATION/`

Each finding must:

- use the template from `templates/finding.md` when available,
- have a stable id,
- identify affected code,
- describe source-to-sink or trust-boundary reasoning,
- explain attackability,
- explain impact,
- include validation plan,
- include counter-analysis placeholder,
- avoid generic claims.

### Phase 3: Counter-analysis

Goal: disprove weak findings.

For each finding under `NEEDS_VALIDATION`:

- look for existing mitigations,
- check reachability,
- check attacker control,
- check trust boundaries,
- check framework protections,
- check whether assumptions are false,
- check for duplicates,
- lower confidence when needed,
- move clearly invalid findings to `REJECTED`,
- move duplicates to `DUPLICATE`.

### Phase 4: Validation

Goal: prove or disprove one finding at a time.

Use `sandbox/` as the sandbox.

Validation may use:

- static proof,
- unit test,
- integration test,
- runtime reproduction,
- sanitizer output,
- crash reproduction,
- HTTP exploit,
- CLI exploit,
- crafted input file,
- config-based trigger,
- log evidence,
- database evidence,
- debugger trace,
- benchmark oracle comparison.

A finding may be marked `CONFIRMED` only when the evidence is clear and reproducible enough.

Benchmark labels alone are not enough for `CONFIRMED`.

### Phase 5: Reporting

Goal: produce Markdown reports.

Reports should include:

- executive summary,
- target summary,
- methodology,
- confirmed findings,
- rejected/duplicate summary if useful,
- evidence references,
- limitations,
- recommended next steps.

## Finding quality bar

A valid finding must answer:

- What is the vulnerable component?
- Where is the affected code?
- What is the attacker-controlled input?
- What trust boundary is crossed?
- What dangerous sink or security decision is reached?
- Why existing controls are insufficient?
- What is the impact?
- How can it be validated?
- What evidence confirms or rejects it?

Do not create findings like:

> Potential SQL injection may exist because the project uses SQL.

Create findings like:

> User-controlled `sort` reaches raw SQL `ORDER BY` construction in `SearchRepository.BuildQuery()` without allowlist validation.

## Confidence levels

Use these confidence levels:

- `LOW`: plausible but weak; assumptions are significant.
- `MEDIUM`: credible source-to-sink or trust-boundary path exists.
- `HIGH`: strong static evidence exists, but runtime validation is still pending.
- `CONFIRMED`: validated with evidence.

## Severity levels

Use these severity levels:

- `CRITICAL`
- `HIGH`
- `MEDIUM`
- `LOW`
- `INFO`

Do not over-focus on CVSS in the PoC. Prefer clear technical impact.

## Status values

Use only these status values:

- `NEEDS_VALIDATION`
- `CONFIRMED`
- `REJECTED`
- `DUPLICATE`

## Evidence rules

For each confirmed finding, create:

- `itemdb/evidence/<finding-id>/README.md`

Add relevant artifacts when available:

- requests,
- responses,
- logs,
- screenshots,
- terminal output,
- exploit scripts,
- generated inputs,
- sanitizer reports,
- crash dumps,
- debugger notes,
- database state,
- test output.

## Validation safety rules

The validator may freely experiment inside the sandbox environment under `sandbox/`.

The validator may install packages, build code, run tools, reset test data, and execute proof-of-concept inputs inside the sandbox.

The validator must not attack third-party systems.

The validator must not exfiltrate secrets.

The validator must not modify production systems.

The validator must not perform destructive actions outside the local sandbox.

## Target-specific behavior

Target-specific logic belongs in skills.

Examples:

- `.opencode/skills/c-cpp-security/`
- `.opencode/skills/web-security/`
- `.opencode/skills/dotnet-security/`
- `.opencode/skills/juliet-benchmark/`
- `.opencode/skills/iac-security/`

If the target appears to match a skill, apply the skill, but do not hardcode the whole workflow around a single target type.

## Run summaries

When practical, write a short run summary under `runs/`.

A run summary should include:

- date,
- phase,
- prompt or goal,
- files read,
- files created or modified,
- findings created,
- findings moved,
- important assumptions,
- next recommended step.
