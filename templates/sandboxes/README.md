# CodeCome sandbox examples (seed templates)

This directory contains the curated **seed sandboxes** that
CodeCome's Phase 1b (sandbox bootstrap) uses as starting points.

Each subdirectory `<id>/` is a stack-specific seed:

- `c-cpp/`
- `dotnet/`
- `erlang-otp/`
- `generic/`
- `go/`
- `iac-terraform/`
- `java-maven/`
- `multi-service-compose/`
- `nested-virt/`
- `node/`
- `php/`
- `python/`
- `ruby/`
- `rust/`
- `web-static/`

Each seed contains:

- `manifest.yml` declaring `applies_when`, `template_vars`,
  `caveats`, and the recommended build / test commands,
- a `Dockerfile`, optionally a `docker-compose.yml`,
- `scripts/build.sh` and `scripts/test.sh` (starter
  versions; the agent must adapt them to the real target during
  Phase 1b),
- `README.md` and `notes.md` describing when the seed applies and
  what to extend.

See `.opencode/skills/sandbox-bootstrap/SKILL.md` for the full
authoring rules.

## Sandbox recipe

After bootstrap, Phase 1b writes `itemdb/notes/sandbox-recipe.yml`.
This machine-readable file is the contract between the sandbox and
later harness steps. See `templates/sandbox-recipe.yml.example`
for the schema.

To validate it:

    tools/sandbox-bootstrap.py recipe-validate

To print it:

    tools/sandbox-bootstrap.py recipe-print

## License

The files in this `templates/sandboxes/` subtree are licensed under
the **MIT License**. See `LICENSE` in this directory.

This is intentional: these files are designed to be copied into
user workspaces by the bootstrap CLI (`tools/sandbox-bootstrap.py
apply`). The MIT license lets users adopt and modify the seeds
inside their own (potentially proprietary) projects without any
copyleft contamination from the rest of the CodeCome project.

The rest of CodeCome is licensed under
`GPL-3.0-or-later OR AGPL-3.0-or-later` — see the top-level
`LICENSE`, `AGPL-LICENSE`, and `NOTICE` files.

Copyright (C) 2025-2026 Pablo Ruiz García
&lt;pablo.ruiz@gmail.com&gt;.
