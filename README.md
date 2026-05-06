# CodeCome

CodeCome is an AI-assisted vulnerability research workspace.

It is designed to help language-model agents inspect source code, identify security-relevant attack surfaces, produce structured vulnerability hypotheses, and validate those hypotheses inside an isolated execution environment.

CodeCome is not intended to be a traditional static analyzer, vulnerability scanner, or web pentest tool. Its core purpose is to provide a repeatable research workflow where every potential issue becomes a reviewable artifact.

## Goals

- Provide a reusable workspace for source code security research.
- Support different target types: web applications, services, CLI tools, libraries, benchmark corpora, infrastructure code, and mixed repositories.
- Keep the workflow simple enough to run with `opencode run ...`.
- Store findings as Markdown files that can be reviewed by humans.
- Separate hypothesis generation from validation.
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

   The agent creates precise vulnerability hypotheses as Markdown findings under `itemdb/findings/NEEDS_VALIDATION/`.

3. **Counter-analysis**

   A review pass attempts to disprove, weaken, deduplicate, or reject candidate findings.

4. **Validation**

   A validator agent uses the sandboxed environment under `sandbox/` to prove or disprove individual findings. Validation may involve building the target, running tests, writing small PoCs, exercising APIs, triggering CLI inputs, using sanitizers, inspecting logs, or producing a static proof.

5. **Reporting**

   Confirmed findings are summarized into Markdown reports with technical detail and evidence references.

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

Sandboxed execution environment for validation.

For the initial PoC this is expected to be Docker-based. Future versions may support per-finding containers, disposable VMs, or remote sandboxes.

### `itemdb/`

File-based item database.

This directory contains:

- reconnaissance notes,
- candidate findings,
- confirmed findings,
- rejected findings,
- evidence,
- reports,
- and indexes.

### `runs/`

Execution logs, prompts, transcripts, and summaries from agent runs.

### `templates/`

Markdown templates used by agents and helper tools.

### `tools/`

Python helper scripts for creating, listing, moving, validating, and reporting findings.

### `.opencode/`

Agent and skill definitions used by OpenCode.

## Finding lifecycle

Findings move through a simple lifecycle:

    NEEDS_VALIDATION
        ├── CONFIRMED
        ├── REJECTED
        └── DUPLICATE

A finding should only be marked as `CONFIRMED` when there is clear evidence.

Valid evidence may include:

- runtime reproduction,
- failing/passing test,
- sanitizer output,
- crash reproduction,
- HTTP/CLI/file-based exploit,
- log evidence,
- database evidence,
- or a strong static proof.

Benchmark labels alone are not enough to mark a finding as confirmed.

## First PoC target

The first planned PoC target is the NIST SARD Juliet C/C++ test suite.

Juliet is used as a benchmark target, not as a special case baked into the CodeCome core.

The workflow should remain generic:

    target reconnaissance
    → attack surface recognition
    → vulnerability hypotheses
    → counter-analysis
    → validation
    → Markdown reporting

For Juliet, the attack surface may map to testcase entrypoints, bad/good functions, input simulation functions, and source/sink patterns.

For a web application, the attack surface may map to routes, controllers, APIs, authentication flows, authorization checks, file uploads, and background workers.

For a CLI tool, the attack surface may map to command-line arguments, input files, config files, environment variables, stdin, and filesystem operations.

## Basic usage

The initial PoC is intended to be driven manually with OpenCode commands.

Example phases:

    opencode run "CodeCome phase 1: perform target reconnaissance. Read AGENTS.md and codecome.yml. Analyze ./src and write notes under ./itemdb/notes. Do not create findings yet."

    opencode run "CodeCome phase 2: generate vulnerability hypotheses from the target source. Use itemdb/notes as context. Create Markdown findings under itemdb/findings/NEEDS_VALIDATION."

    opencode run "CodeCome phase 3: review all findings under itemdb/findings/NEEDS_VALIDATION. Try to disprove, deduplicate, or reject weak findings."

    opencode run "CodeCome phase 4: validate itemdb/findings/NEEDS_VALIDATION/CC-0001.md using the sandbox under ./sandbox. Store evidence under itemdb/evidence/CC-0001 and update the finding."

    opencode run "CodeCome phase 5: generate a Markdown report from confirmed findings."

## Design principles

### Findings are artifacts

Every relevant issue must be written as a Markdown file.

The model should not leave important security claims only in chat history or run transcripts.

### Hypotheses are not confirmed bugs

A plausible vulnerability is first a hypothesis.

Confirmation requires evidence.

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

The validator may freely experiment inside the sandbox environment, but should not modify target source code unless explicitly instructed.

### The core is target-agnostic

CodeCome should adapt to the target placed under `src/`.

Target-specific behavior should live in skills, adapters, notes, or config, not in the core workflow.

## Current status

This repository is in early PoC stage.

The initial implementation is intentionally simple:

- Markdown findings.
- File-based item database.
- Python helper scripts.
- Docker-based validation environment.
- One agent at a time.
- One validation worker at a time.


## Reusable prompts

CodeCome includes reusable phase prompts under:

    prompts/

Available prompts:

    prompts/phase-1-recon.md
    prompts/phase-2-audit.md
    prompts/phase-3-review.md
    prompts/phase-4-validate.md
    prompts/phase-5-report.md

## Running the workflow

### Phase 1: reconnaissance

    opencode run "$(cat prompts/phase-1-recon.md)"

This phase creates or updates reconnaissance notes under:

    itemdb/notes/

### Phase 2: vulnerability hypothesis generation

    opencode run "$(cat prompts/phase-2-audit.md)"

This phase creates candidate findings under:

    itemdb/findings/NEEDS_VALIDATION/

### Phase 3: counter-analysis

    opencode run "$(cat prompts/phase-3-review.md)"

This phase reviews candidate findings, attempts to disprove them, and may move findings to:

    itemdb/findings/REJECTED/
    itemdb/findings/DUPLICATE/

### Phase 4: validation

Validate one finding at a time.

Example:

    opencode run "$(sed 's#FINDING_PATH_OR_ID#CC-0001#g' prompts/phase-4-validate.md)"

or:

    sed 's#FINDING_PATH_OR_ID#CC-0001#g' prompts/phase-4-validate.md | opencode run

This phase stores evidence under:

    itemdb/evidence/<finding-id>/

and may move findings to:

    itemdb/findings/CONFIRMED/
    itemdb/findings/REJECTED/

### Phase 5: reporting

    opencode run "$(cat prompts/phase-5-report.md)"

A basic local report can also be generated without an agent:

    make report

The default report path is:

    itemdb/reports/report.md

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

Regenerate finding index:

    make index

Regenerate report:

    make report

Check sandbox:

    make sandbox-check

Open sandbox shell:

    make sandbox-shell

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
