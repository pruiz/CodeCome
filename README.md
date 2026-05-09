# CodeCome

> The harness for building your own Mythos of vulnerability research at home!

CodeCome is an (open source) Agentic vulnerability research harness, or AI-assisted vulnerability research workspace.

It is designed to help language-model agents inspect source code, identify security-relevant attack surfaces, produce structured vulnerability hypotheses, validate those hypotheses inside an isolated execution environment, demonstrate real-world impact through exploit development, and produce reviewable Markdown reports.

CodeCome is not intended to be a traditional static analyzer, vulnerability scanner, or web pentest tool. Its core purpose is to provide a repeatable research workflow where every potential issue becomes a reviewable artifact.

## Goals

- Provide a reusable workspace for source code security research.
- Support different target types: web applications, services, CLI tools, libraries, benchmark corpora, infrastructure code, and mixed repositories.
- Keep the workflow simple enough to run with `make phase-1` through `make phase-6`.
- Store findings as Markdown files that can be reviewed by humans.
- Separate hypothesis generation from validation.
- Demonstrate real-world impact of confirmed vulnerabilities through exploit development.
- Support future parallel validation workers without requiring that complexity in the initial PoC.
- Keep the first PoC file-based: no database, no RAG, no external ticketing system.

## Non-goals

- CodeCome is not a fully automated vulnerability scanner.
- CodeCome does not guarantee complete coverage.
- CodeCome does not replace manual security review.
- CodeCome does not modify the target source code unless explicitly instructed.
- CodeCome does not require a specific programming language, framework, or application type.

## Core workflow

CodeCome uses a phased workflow:

1. **Target reconnaissance**

   The agent inspects the source tree and infers the target type, languages, frameworks, build model, execution model, attack surfaces, trust boundaries, assets, dangerous sinks, and likely vulnerability classes.

2. **Hypothesis generation**

   The agent creates precise vulnerability hypotheses as Markdown findings under `itemdb/findings/PENDING/`.

3. **Counter-analysis**

   A review pass attempts to disprove, weaken, deduplicate, or reject candidate findings.

4. **Validation**

   A validator agent uses the sandboxed environment under `sandbox/` to prove or disprove individual findings. Validation may involve building the target, running tests, writing small PoCs, exercising APIs, triggering CLI inputs, using sanitizers, inspecting logs, or producing a static proof.

5. **Exploit development**

   For selected confirmed findings, an exploiter agent develops proof-of-concept exploits that demonstrate real-world impact. This phase answers the question developers always ask: "So what? What can an attacker actually do with this?" The agent escalates from validation evidence (e.g., a crash) to concrete impact (e.g., code execution, data exfiltration, privilege escalation) and may adjust severity based on demonstrated impact.

6. **Reporting**

   Findings are summarized into Markdown reports with technical detail, demonstrated impact narratives, and evidence references. Exploited findings (with proven impact) are highlighted above confirmed findings.

## Workspace layout

    .
    ├── README.md
    ├── AGENTS.md
    ├── codecome.yml
    ├── src/
    ├── sandbox/
    ├── itemdb/
    ├── runs/
    ├── templates/
    ├── tools/
    ├── prompts/
    ├── docs/
    └── .opencode/

### `src/`

Target source code to audit.

This may be:

- a copied source tree,
- a git submodule,
- a checked-out repository,
- a benchmark corpus,
- or a generated/extracted source package.

### `sandbox/`

Sandboxed execution environment for validation and exploit development.

For the initial PoC this is expected to be Docker-based. Future versions may support per-finding containers, disposable VMs, or remote sandboxes.

### `itemdb/`

File-based item database.

This directory contains:

- reconnaissance notes,
- candidate findings,
- confirmed findings,
- exploited findings (with demonstrated impact),
- rejected findings,
- evidence and exploitation artifacts,
- reports,
- and indexes.

### `runs/`

Execution logs, prompts, transcripts, and summaries from agent runs.

### `templates/`

Markdown templates used by agents and helper tools.

### `tools/`

Python helper scripts for creating, listing, moving, validating, and reporting findings. All tools support colored terminal output (respects `NO_COLOR`).

### `prompts/`

Reusable phase prompts for driving the workflow with OpenCode.

### `.opencode/`

Agent and skill definitions used by OpenCode.

Agents:

- `recon` -- Phase 1: target reconnaissance
- `auditor` -- Phase 2: vulnerability hypothesis generation
- `reviewer` -- Phase 3: counter-analysis and deduplication
- `validator` -- Phase 4: finding validation
- `exploiter` -- Phase 5: exploit development and impact demonstration
- `reporter` -- Phase 6: Markdown report generation

### `codecome.yml`

Project configuration for the audit workspace. Key sections:

- **`project`** — project name, source path, language hints. Set `name` to
  identify your target in output and reports.
- **`audit.scope`** — include/exclude globs controlling which files agents
  inspect. Adjust `exclude` if your target has non-standard vendored or
  generated directories.
- **`audit.focus`** — vulnerability classes to prioritize during analysis.
  Remove or add entries to match your target's risk profile.
- **`audit.extra_prompts`** — optional per-phase extra instructions appended
  to the phase prompt. Useful for persistent customization (e.g., sandbox
  preferences, focus areas). For ad-hoc use, see `PROMPT_EXTRA` and
  `PROMPT_EXTRA_FILE` below.
- **`agents`** — optional per-agent model and variant pinning (see
  "Model selection" below).
- **`environment`** — sandbox paths and scripts. Typically left at defaults
  unless you use a custom sandbox layout.
- **`validation`** — confirmation policies, allowed write paths, and
  validation methods. Defaults are safe for most targets.

The shipped defaults work out of the box. Review and adjust `project.name`,
`audit.scope`, and `audit.focus` before starting phase-1.

## Finding lifecycle

Findings move through a structured lifecycle:

    PENDING
        ├── CONFIRMED
        │       └── EXPLOITED
        ├── REJECTED
        └── DUPLICATE

- A finding should only be marked as `CONFIRMED` when there is clear evidence.
- A finding should only be marked as `EXPLOITED` when a working proof-of-concept demonstrates concrete real-world impact beyond the initial validation.
- If exploitation is not feasible, the finding stays in `CONFIRMED`.

Valid evidence for confirmation may include:

- runtime reproduction,
- failing/passing test,
- sanitizer output,
- crash reproduction,
- HTTP/CLI/file-based exploit,
- log evidence,
- database evidence,
- or a strong static proof.

Benchmark labels alone are not enough to mark a finding as confirmed.

## Prerequisites

CodeCome runs on top of [OpenCode](https://opencode.ai), an open-source AI
coding agent.

1. **Install OpenCode** — follow the
   [installation guide](https://opencode.ai/docs/#install).

2. **Configure a provider** — connect at least one LLM provider with an API
   key. See [provider setup](https://opencode.ai/docs/#configure).

3. **Python 3.10+** — needed for workspace tooling (`make venv` creates a
   local virtualenv).

4. **GNU Make** — used to drive the workflow.

## Quick start

1. Place target source under `src/`.

2. Review `codecome.yml` — set `project.name` to your target's name and
   adjust `audit.scope` or `audit.focus` if needed. The defaults work for
   most projects.

3. Check workspace:

       make venv
       make check

   Before committing or pushing changes, run:

       make tests

4. Run the workflow:

       make phase-1                  # Reconnaissance
       make phase-2                  # Hypothesis generation
       make phase-3                  # Counter-analysis
       make phase-4 FINDING=CC-0001  # Validate one finding
       make phase-5 FINDING=CC-0001  # Develop exploit for one finding
       make phase-6                  # Generate report

5. Convenience targets:

       make validate-all             # Validate all PENDING findings
       make exploit-all              # Exploit all CONFIRMED findings

Each `make` target checks readiness gates before invoking the corresponding agent. Phase 4 and Phase 5 are invoked once per finding.

By default, phase targets use a CodeCome-owned styled wrapper around `opencode run --format json` so assistant output, tool calls, and tool results render with consistent colors and structure. The wrapper pretty-renders `read`, `write`, `edit`, `apply_patch`, `grep`, `glob`, `bash`, `todowrite`, and `skill` tool calls; all others get a generic JSON panel. The wrapper also detects bash invocations of `tools/sandbox-bootstrap.py --format json …` (and `make sandbox-* BOOTSTRAP_ARGS='--format json'` wrappers) and renders them as a structured Sandbox panel with capability tables, validation tier summaries, and color-coded gate badges. Some models prefer to invoke CLI helpers via the bash tool instead of the OpenCode-native Read/Grep/Glob tools (e.g. `rtk read FILE`, `rtk grep PAT PATH`, `rtk ls`, plain `rg PAT`, `cat FILE`, `head -n N FILE`, `tail -n N FILE`, `find PATH`, `tree`); the wrapper detects those calls and routes their output through the matching styled renderer so the panels look the same regardless of how the agent invoked the operation. Pipelines, redirections and command substitutions are intentionally left for the generic Bash panel.

All `make` targets that invoke Python tools expect a repo-local virtualenv at `.venv/`. If it is missing or stale, the command will stop with a setup message telling you to run `make venv`.

`make tests` runs the Python test suite under `tests/` and validates finding YAML frontmatter via `tools/check-frontmatter.py`. This catches regressions such as malformed finding metadata that can break helper scripts.

## Reusable prompts

CodeCome includes reusable phase prompts under:

    prompts/

Available prompts:

    prompts/phase-1-recon.md
    prompts/phase-2-audit.md
    prompts/phase-3-review.md
    prompts/phase-4-validate.md
    prompts/phase-5-exploit.md
    prompts/phase-6-report.md

## Running the workflow

The recommended way to run CodeCome is through `make` targets, which handle readiness gate checks and agent selection automatically.

### Phase 1: reconnaissance + sandbox bootstrap

    make phase-1

Phase 1 has two sub-stages run together:

- **1a — Source reconnaissance**: creates or updates reconnaissance notes under `itemdb/notes/`.
- **1b — Sandbox bootstrap**: picks a curated baseline from `templates/sandboxes/<id>/`, applies it to `sandbox/` (with marker substitution), validates it, and writes `itemdb/notes/sandbox-plan.md` plus `sandbox/CODECOME-GENERATED.md`.

`sandbox/` is semi-ephemeral; Phase 1b regenerates its contents based on what is in `src/`.

Bootstrap CLI:

    make sandbox-list
    make sandbox-detect
    make sandbox-inspect ID=python
    make sandbox-bootstrap ID=python
    make sandbox-validate
    make sandbox-status

Sandbox runtime helpers (one make target per canonical capability):

    make sandbox-setup        # sandbox setup (setup.sh or `docker compose build`)
    make sandbox-up           # sandbox start
    make sandbox-check        # sandbox sanity
    make sandbox-build        # target build
    make sandbox-test         # target test
    make sandbox-down         # sandbox stop
    make sandbox-shell        # open a shell
    make sandbox-logs         # tail logs
    make sandbox-clean        # clean runtime artifacts
    make sandbox-reset        # reset to a known state

See `docs/sandbox.md` for the full bootstrap workflow.

### Phase 2: vulnerability hypothesis generation

    make phase-2

Creates candidate findings under `itemdb/findings/PENDING/`. Phase 2 is gated by the sandbox: it blocks if `sandbox/` is missing or if the most recent validation failed. Override with `CODECOME_ALLOW_NO_SANDBOX=1`.

### Phase 3: counter-analysis

    make phase-3

Reviews candidate findings. May move findings to `itemdb/findings/REJECTED/` or `itemdb/findings/DUPLICATE/`.

### Phase 4: validation

Validate one finding at a time:

    make phase-4 FINDING=CC-0001

Stores evidence under `itemdb/evidence/<finding-id>/` and may move findings to `CONFIRMED/` or `REJECTED/`.

To validate all unvalidated findings:

    make validate-all

### Phase 5: exploit development

Develop a proof-of-concept exploit for one confirmed finding:

    make phase-5 FINDING=CC-0001

Stores exploitation artifacts under `itemdb/evidence/<finding-id>/exploits/` and may move findings to `EXPLOITED/`. The exploiter may adjust severity based on demonstrated impact.

To exploit all confirmed findings that have not already been marked as not feasible:

    make exploit-all

### Phase 6: reporting

    make phase-6

A basic local report can also be generated without an agent:

    make report

The default report path is `itemdb/reports/report.md`.

### Wrapper controls

The phase targets support these environment variables:

    CODECOME_USE_WRAPPER=0   # bypass the styled wrapper and use raw opencode run
    CODECOME_THINKING=1      # force --thinking on (default: per-provider, see below)
    CODECOME_THINKING=0      # force --thinking off
    CODECOME_RENDER_REASONING=0  # suppress on-screen Thinking panels even if --thinking is on
    CODECOME_REASONING_MAX_CHARS=4000  # truncate individual reasoning blocks past this length
    CODECOME_SANDBOX_RENDER=0  # disable the structured Sandbox panel (fall back to a plain Bash panel)
    CODECOME_SANDBOX_VALIDATE_STDERR_LINES=20  # cap stderr_tail lines shown per failed validate tier
    CODECOME_SANDBOX_FILES_CAP=15  # cap files listed in sandbox apply/inspect/detect panels
    CODECOME_BASH_SHIM_RENDER=0  # disable rtk/cat/head/tail/rg/ls/find/tree -> Read/Grep/Glob routing
    CODECOME_BASH_SHIM_LS_STRIP_LONG_FORMAT=0  # keep `ls -la` columns instead of stripping to filenames
    OPENCODE_ARGS='...'      # extra flags forwarded to opencode run
    CODECOME_MODEL=<id>      # pin the model per phase, e.g. anthropic/claude-opus-4-7
    CODECOME_MODEL_VARIANT=<v>  # pin the model variant, e.g. high, max

The wrapper resolves the effective model in this order: `OPENCODE_ARGS` (`--model …` / `--variant …`) > env (`CODECOME_MODEL`, `CODECOME_MODEL_VARIANT`) > `codecome.yml` (`agents.<name>.model` / `.variant`) > the model used in your most recent OpenCode session for this project (best-effort, read from OpenCode's local DB) > unknown. The chosen value is shown in the phase header banner along with its source. When the resolved value comes from env or YAML, the wrapper appends `--model` / `--variant` to `opencode run` so the banner is the truth. Discovered defaults (the last-session lookup) are display-only and are not enforced.

The wrapper picks a `--thinking` default per provider so all models produce comparable in-flight commentary:

- `anthropic/*` → off. Claude already interleaves thinking with normal `text` blocks via OpenCode's interleaved-thinking beta header, so `Assistant` panels already show the model's working.
- `openai/*`, `xai/*`, `github-copilot/*`, `groq/*`, `cerebras/*`, `google/*`, `google-vertex/*` → on. These providers hide reasoning unless `--thinking` is passed; without it the wrapper would only see one or zero `text` events per phase.
- Anything else (unknown / future provider) → on. Cheaper to over-surface than under-surface in vulnerability research.

Override precedence: `--thinking` already in `OPENCODE_ARGS` > `CODECOME_THINKING` env > per-provider default. Some providers bill reasoning tokens; set `CODECOME_THINKING=0` per phase to opt out without losing the styled wrapper.

Print the full resolution table for any agent without launching a phase:

    make show-model
    make show-model AGENT=auditor

The wrapper currently targets OpenCode 1.14.39 or newer.

If `.venv` is missing required packages, rerun:

    make venv

### Manual invocation

If you prefer direct `opencode run` commands instead of `make` targets:

    opencode run --agent recon "$(cat prompts/phase-1-recon.md)"
    opencode run --agent auditor "$(cat prompts/phase-2-audit.md)"
    opencode run --agent reviewer "$(cat prompts/phase-3-review.md)"
    opencode run --agent validator "$(sed 's#FINDING_PATH_OR_ID#CC-0001#g' prompts/phase-4-validate.md)"
    opencode run --agent exploiter "$(sed 's#FINDING_PATH_OR_ID#CC-0001#g' prompts/phase-5-exploit.md)"
    opencode run --agent reporter "$(cat prompts/phase-6-report.md)"

`make report` is a lightweight local summary generator. Use `make phase-6` when you want the full AI-written report flow.

Direct manual `opencode run` usage remains unchanged. The styled wrapper is only used by `make phase-*` targets.

## Local helper commands

Show available commands:

    make help

Validate workspace:

    make check

Show finding status:

    make status

Show next finding id:

    make next-id

Validate finding frontmatter:

    make frontmatter

Reset local audit artifacts:

    make itemdb-reset

Regenerate finding index:

    make index

Regenerate report:

    make report

List findings (optionally filter by status):

    make findings
    make findings STATUS=PENDING

Create a new finding from template:

    make findings-create TITLE="Buffer overflow in parser"

Move a finding to another status:

    make findings-move FINDING=CC-0001 STATUS=CONFIRMED

Create evidence directory for a finding:

    make findings-evidence FINDING=CC-0001

Check sandbox (requires phase-1 to bootstrap `sandbox/` first):

    make sandbox-check

Open sandbox shell:

    make sandbox-shell

## Starting over

If you want a completely clean workspace, the safest option is to clone a
fresh copy of CodeCome again.

If you only want to clear generated local audit artifacts without recloning,
use:

    make itemdb-reset

This removes local notes, findings, evidence, reports, run summaries, and
temporary artifacts, then recreates the expected `.gitkeep` files. Do not use
it if you want to preserve prior audit work.

## Customizing phase prompts

Extra instructions can be appended to any phase prompt from three sources,
applied in this order (all additive):

1. **`codecome.yml`** — persistent per-phase instructions under
   `audit.extra_prompts`. Always applied when the phase runs.

       audit:
         extra_prompts:
           reconnaissance: |
             Focus sandbox on ASAN builds.
             Skip fuzzing harness for now.

2. **`PROMPT_EXTRA_FILE`** — path to a file whose content is appended.

       make phase-1 PROMPT_EXTRA_FILE=my-notes.md

3. **`PROMPT_EXTRA`** — inline text appended directly.

       make phase-1 PROMPT_EXTRA="Also try clang for the sandbox setup."

All three can be combined in a single invocation.

## Design principles

### Findings are artifacts

Every relevant issue must be written as a Markdown file.

The model should not leave important security claims only in chat history or run transcripts.

### Hypotheses are not confirmed bugs

A plausible vulnerability is first a hypothesis.

Confirmation requires evidence.

### Impact must be demonstrated

Confirmed vulnerabilities should have their real-world impact demonstrated through exploit development whenever feasible. Without this, developers may dismiss findings as theoretical or low-impact.

### Counter-analysis is mandatory

Every finding should include an attempt to disprove it.

The reviewer should look for:

- unreachable code paths,
- input validation,
- authorization checks,
- framework-level protections,
- false assumptions,
- duplicate reports,
- and missing exploitability conditions.

### Validation is sandboxed

The validator and exploiter may freely experiment inside the sandbox environment, but should not modify target source code unless explicitly instructed.

### The core is target-agnostic

CodeCome should adapt to the target placed under `src/`.

Target-specific behavior should live in skills, adapters, notes, or config, not in the core workflow.

## Current status

This repository is in early PoC stage.

The initial implementation is intentionally simple:

- Markdown findings.
- File-based item database.
- Python helper scripts with colored terminal output.
- Docker-based validation environment.
- One agent at a time.
- One validation worker at a time.

## Target setup

CodeCome expects the audited target source code to be placed under:

    src/

See:

    docs/target-setup.md

That document explains supported target layouts, including copied source trees, git submodules, extracted archives, benchmark corpora, and the initial Juliet/SARD PoC target.

## Workflow

See:

    docs/workflow.md

for the complete phase-by-phase workflow.

## Development

See:

    docs/development.md

for repository conventions, helper tools, and development workflow.

## Sandbox

See:

    docs/sandbox.md

for sandbox usage, boundaries, evidence capture, and validation environment notes.

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
