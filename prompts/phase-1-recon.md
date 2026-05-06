# CodeCome Phase 1: Target Reconnaissance

You are performing CodeCome Phase 1: target reconnaissance and attack surface recognition.

## Required reading

Read:

- `AGENTS.md`
- `codecome.yml`
- `templates/target-recon.md`
- `.opencode/agents/recon.md`
- `.opencode/skills/source-recon/SKILL.md`

Use additional target-specific skills only if they clearly apply.

Examples:

- `.opencode/skills/c-cpp-security/SKILL.md`
- `.opencode/skills/dotnet-security/SKILL.md`
- `.opencode/skills/web-security/SKILL.md`
- `.opencode/skills/juliet-benchmark/SKILL.md`

## Target

Analyze the source tree under:

    ./src

## Goal

Build a target model by creating these files under `itemdb/notes/`:

- `target-profile.md`
- `attack-surface.md`
- `build-model.md`
- `execution-model.md`
- `trust-boundaries.md`
- `data-flow.md`
- `validation-model.md`
- `interesting-files.md`
- `security-assumptions.md`

Document:

- target type,
- languages and frameworks,
- build system and execution model,
- attack surfaces and entry points,
- trust boundaries,
- data flow paths,
- dangerous sinks,
- security assumptions,
- interesting files for Phase 2,
- validation strategy.

## Important rules

- Do not assume the target is a web application.
- Do not assume the target can be built.
- Do not assume the target can be executed.
- Do not modify files under `src/`.
- Do not generate low-confidence vulnerability findings during reconnaissance.
- Do not rely only on filenames, comments, or labels.
- Be explicit about uncertainty.
- Prefer useful notes over exhaustive dumps.
- Focus on what later phases need.

## Final response

At the end, summarize:

- target type,
- most important attack surfaces,
- recommended Phase 2 focus,
- files created or updated,
- key limitations.
