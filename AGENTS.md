# CodeCome Agent Instructions

You are working inside a CodeCome vulnerability research workspace.

CodeCome is an AI-assisted vulnerability research workflow. Its purpose is to help inspect source code, identify attack surfaces, create structured vulnerability hypotheses, perform counter-analysis, validate findings inside a sandbox, and produce reviewable Markdown reports.

## Prime directive

Produce durable artifacts.

Important security claims must be written to files under `itemdb/`, not left only in chat history or transient run output.

## Workspace layout

- `codecome.yml`: project configuration and audit settings.
- `src/`: target source code to audit.
- `sandbox/`: sandboxed execution and validation environment.
- `itemdb/`: file-based finding database, notes, reports, and evidence.
- `itemdb/notes/`: reconnaissance notes and target model.
- `itemdb/findings/PENDING/`: candidate findings requiring validation.
- `itemdb/findings/CONFIRMED/`: validated findings with evidence.
- `itemdb/findings/EXPLOITED/`: confirmed findings with demonstrated real-world impact.
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
- `tmp/`
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

- `itemdb/findings/PENDING/`

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

For each finding under `PENDING`:

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

### Phase 5: Exploit development

Goal: demonstrate real-world impact of confirmed vulnerabilities.

For selected `CONFIRMED` findings, develop proof-of-concept exploits that show what an attacker can actually achieve. This phase answers the question developers always ask: "So what? What can an attacker actually do with this?"

The exploiter agent:

- starts from existing validation evidence,
- escalates impact (crash to code execution, read to secret exfiltration, bypass to full admin access),
- produces self-contained, reproducible PoC scripts,
- writes clear impact narratives,
- adjusts severity based on demonstrated impact,
- stores exploitation artifacts under `itemdb/evidence/<finding-id>/exploits/`.

A finding may be moved to `EXPLOITED` only when a working proof-of-concept demonstrates concrete impact beyond the initial validation.

If exploitation is not feasible within the sandbox, the finding stays in `CONFIRMED` with a documented explanation.

### Phase 6: Reporting

Goal: produce Markdown reports.

Reports should include:

- executive summary,
- target summary,
- methodology,
- exploited findings (with demonstrated impact),
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

- `PENDING`
- `CONFIRMED`
- `EXPLOITED`
- `REJECTED`
- `DUPLICATE`

## Evidence rules

For each confirmed or exploited finding, create:

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

For exploited findings, also create:

- `itemdb/evidence/<finding-id>/exploits/README.md` (using `templates/exploit-readme.md`)

With additional artifacts such as:

- proof-of-concept exploit scripts,
- crafted payloads,
- captured output demonstrating impact,
- impact logs.

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

## Phase handoff protocol

CodeCome phases are executed sequentially and orchestrated by the user via `make` commands.

Each phase has readiness gates that must be satisfied before it can run:

### Phase 1 readiness

- `src/` must contain target source code.
- No other prerequisites.

### Phase 2 readiness

- `itemdb/notes/target-profile.md` must exist.
- `itemdb/notes/attack-surface.md` must exist.
- At least one reconnaissance note file must exist under `itemdb/notes/`.

### Phase 3 readiness

- At least one finding must exist under `itemdb/findings/PENDING/`.

### Phase 4 readiness

- A specific finding ID must be provided (e.g., `CC-0001`).
- The finding must be in `PENDING` status.

### Phase 5 readiness

- A specific finding ID must be provided (e.g., `CC-0001`).
- The finding must be in `CONFIRMED` status.
- Validation evidence must exist under `itemdb/evidence/<finding-id>/`.

### Phase 6 readiness

- At least one finding must exist in any status directory.

### Orchestration model

The user drives phase transitions by running:

    make phase-1                  # Reconnaissance
    make phase-2                  # Hypothesis generation
    make phase-3                  # Counter-analysis
    make phase-4 FINDING=CC-0001  # Validate one finding
    make phase-5 FINDING=CC-0001  # Develop exploit for one finding
    make phase-6                  # Reporting

Each `make` target checks readiness gates before invoking the corresponding agent.

Phase 4 is invoked once per finding, not as a batch.
Phase 5 is invoked once per finding, not as a batch.

For convenience, `make validate-all` iterates over all `PENDING` findings sequentially.
For convenience, `make exploit-all` iterates over all `CONFIRMED` findings sequentially.

No automatic handoff occurs between phases. The user decides when to advance.

## Run summaries

When practical, write a short run summary under `runs/`.

Use the template: `templates/run-summary.md`

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
