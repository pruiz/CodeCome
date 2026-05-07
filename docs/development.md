# CodeCome Development Notes

This document describes development conventions for the CodeCome repository.

## Python environment

Create a local virtual environment:

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    pip install -r requirements.txt

Run helper commands from the repository root.

## Repository conventions

Use these naming conventions:

- Markdown documents: lowercase kebab-case when possible.
- Executable helper scripts: kebab-case.
- Python internal functions and variables: snake_case.
- Finding files: `CC-0001-short-title.md`.
- Evidence directories: `itemdb/evidence/CC-0001/`.

Examples:

    tools/create-finding.py
    tools/list-findings.py
    tools/render-index.py
    tools/render-report.py
    prompts/phase-1-recon.md
    docs/target-setup.md

## Directory responsibilities

### `src/`

Target source code.

CodeCome tooling should not modify this directory unless explicitly instructed.

### `sandbox/`

Local validation environment.

Target-specific build, run, and validation scripts may live here.

### `itemdb/`

Markdown database for notes, findings, evidence, reports, and indexes.

### `templates/`

Reusable Markdown templates.

### `tools/`

Python helper scripts.

### `prompts/`

Reusable OpenCode prompts.

### `.opencode/`

OpenCode agents and skills.

## Helper tools

Check workspace:

    ./tools/codecome.py check

Show status:

    ./tools/codecome.py status

Show next finding id:

    ./tools/codecome.py next-id

Create a finding:

    ./tools/create-finding.py "Finding title"

List findings:

    ./tools/list-findings.py

Validate finding frontmatter:

    ./tools/check-frontmatter.py

Render index:

    ./tools/render-index.py

Render report:

    ./tools/render-report.py

Create evidence README:

    ./tools/create-evidence.py CC-0001

Move finding:

    ./tools/move-finding.py CC-0001 CONFIRMED

## Make targets

Show commands:

    make help

Recommended quality gate:

    make check
    make frontmatter
    make index
    make report

Sandbox smoke test:

    make sandbox-check

## Adding a new skill

Create:

    .opencode/skills/<skill-name>/SKILL.md

A skill should describe:

- when to use it,
- what inputs to read,
- what output to create,
- analysis checklist,
- validation guidance,
- false positive patterns,
- reporting guidance.

Keep skills target-specific when appropriate.

Do not hardcode target-specific behavior into the core workflow.

## Adding a new agent

Create:

    .opencode/agents/<agent-name>.md

An agent should describe:

- role,
- required reading,
- mission,
- allowed outputs,
- rules,
- completion checklist.

Core agents should remain generic.

## Adding a new prompt

Create:

    prompts/<phase-or-task>.md

Prompts should:

- state the phase or task,
- list required reading,
- define outputs,
- include important rules,
- define final response expectations.

Prompts should be usable with:

    opencode run "$(cat prompts/<phase-or-task>.md)"

## Finding frontmatter

All findings must start with YAML frontmatter.

Validate with:

    make frontmatter

If frontmatter checks fail, fix the finding before rendering reports.

## Git hygiene

Commit workflow changes separately from target source changes when possible.

Recommended commit groups:

1. CodeCome workflow/tooling.
2. Target source import or update.
3. Reconnaissance notes.
4. Candidate findings.
5. Counter-analysis updates.
6. Validation evidence.
7. Reports.

This makes review easier.

## Secrets

Do not commit:

- tokens,
- passwords,
- API keys,
- private keys,
- production credentials,
- customer data,
- sensitive logs.

Use `.env` for local settings and keep `.env` ignored.

## Large files

Avoid committing large generated artifacts.

Prefer small, reviewable evidence files.

If large artifacts are unavoidable, document why they are needed.

## Style

Keep Markdown concise and reviewable.

Use relative paths.

Avoid huge pasted logs in findings or reports.

Store large outputs under `itemdb/evidence/<finding-id>/`.

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
