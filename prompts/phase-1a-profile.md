# CodeCome Phase 1a: Target Profile

You are performing CodeCome **Phase 1a** — the first sub-stage of Phase 1.

This sub-stage is scoped to: broad source tree mapping, language/framework detection, build model identification, and CodeQL plan generation. Do not produce full reconnaissance notes, file-risk-index, or sandbox artifacts here. Those are handled by Phase 1b and 1c.

## Required reading

Read the following files (all paths are relative to the project/workspace root):

- `AGENTS.md`
- `codecome.yml`
- `templates/target-recon.md`
- `templates/codeql-plan.yml`
- `.opencode/agents/recon.md`
- `.opencode/skills/source-recon/SKILL.md`

Do not load target-specific security skills or vulnerability-family skills during Phase 1a. Keep the scope structural.

## Target

Analyze the source tree under:

    ./src

## Required outputs

Create these files under `itemdb/notes/`:

- `target-profile.md`
- `build-model.md`
- `codeql-plan.yml`

### `target-profile.md`

Document:

- **Target type**: web application, CLI tool, library, service, firmware, IaC, mobile app, desktop app, benchmark corpus, or mixed repository.
- **Primary languages and frameworks**: detected language, version indicators, major frameworks.
- **Secondary languages**: tooling, scripting, configuration DSLs.
- **Repository structure**: top-level layout, key directories, monorepo vs single-project.
- **Primary target component**: the main application, service, or library. If multiple, identify the primary and note secondary surfaces as optional follow-up.

Do not yet produce detailed attack surface, trust boundary, data flow, or validation notes. Those are Phase 1b.

### `build-model.md`

Document:

- **Build system**: Make, CMake, Maven, Gradle, npm, pip, Cargo, Go modules, etc.
- **Build commands**: how to compile/build the target from source.
- **Dependencies**: package manager files, vendored dependencies, external dependencies.
- **Build prerequisites**: toolchain versions, system packages, Docker images.
- **Whether the target can be built** within the workspace. Be honest about blockers.

### `codeql-plan.yml`

Create `itemdb/notes/codeql-plan.yml` by filling in the template from `templates/codeql-plan.yml`.

Rules:

- Only include languages you have detected with **HIGH** or **MEDIUM** confidence.
- For each language, select the appropriate pack profiles:
  - `official` — always include for languages with CodeQL support.
  - `github-security-lab` — include for security-focused audits.
  - `trailofbits` — include for C/C++ and Go targets.
  - `coding-standards` — include for C/C++ targets where coding standards queries apply.
  - `local` — include if custom queries exist under `queries/codeql/<language>/`.
- Set `build_mode` to `none` for interpreted languages, `manual` for compiled languages with a known build command, or `autobuild` if CodeQL autobuild should be attempted.
- Fill in `build_command` when `build_mode` is `manual`.
- Set `recommended: false` if you cannot confidently profile any language.
- Add relevant `notes` explaining your language choices and any uncertainties.
- Update `exclude` patterns to match the target's test, fixture, vendor, and generated code directories if different from the defaults.

## Important rules

- Do not assume the target is a web application.
- Do not modify files under `src/`.
- Do not generate vulnerability findings.
- Do not produce full reconnaissance notes (attack-surface, trust-boundaries, etc.) — those are Phase 1b.
- Do not bootstrap the sandbox — that is Phase 1c.
- Do not run CodeQL manually. The harness runs it after this sub-stage.
- Be explicit about uncertainty.
- Prefer useful notes over exhaustive dumps.
- Focus on what later sub-stages need.

## Final response

At the end, summarize:

- Target type and primary language(s)
- Build system and buildability assessment
- Languages selected for CodeQL analysis and their confidence levels
- Files created: `target-profile.md`, `build-model.md`, `codeql-plan.yml`
- Key uncertainties or blockers
