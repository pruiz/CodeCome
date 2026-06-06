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

- Set `schema_version: 2`. The v2 schema adds two new optional fields (see below).
- Discover analysis units under `./src`. An analysis unit is a coherent project/component with one source root and one or more languages/stacks, such as an API service, frontend app, native library, CLI, package, firmware tree, or benchmark corpus.
- Use stable, lowercase `analysis_units[].id` values such as `api`, `frontend`, `native-lib`, or `root`. These IDs are discovered here; users do not define them in `codecome.yml`.
- Set `analysis_units[].path` to the real source path under `./src` for that unit. Do not use CodeQL-generated helper paths such as `_codeql_detected_source_root`.
- Use one `analysis_units` entry for a single-project repository and multiple entries for monorepos or mixed stacks.
- Only include languages you have detected with **HIGH** or **MEDIUM** confidence.
- For compiled languages (c-cpp, go, csharp, java-kotlin, swift) set `analysis_units[].sandbox_build_target` to the `build_targets[].id` from `sandbox-recipe.yml` that provides the build command for this unit. If the recipe has not been generated yet (this is Phase 1a), pick a sensible id such as `root` — Phase 1b will flesh out the recipe and the id can be updated if needed.
- For each language, set `build_provider`:
  - `"sandbox-recipe"` — for compiled languages whose build command should be resolved from `sandbox-recipe.yml` after Phase 1b. Leave `build_command` empty (the runner resolves it from the recipe).
  - `"none"` — for no-build languages (python, javascript-typescript, ruby).
- Avoid concrete build shell snippets in `build_command` unless the build is obvious and stable and no recipe is available. Prefer `build_provider: sandbox-recipe` for everything that needs a build.
- For each language in each analysis unit, select the appropriate pack profiles:
  - `official` — always include for languages with CodeQL support.
  - `github-security-lab` — include for security-focused audits.
  - `trailofbits` — include for C/C++ and Go targets.
  - `coding-standards` — include for C/C++ targets where coding standards queries apply.
  - `local` — include if custom queries exist under `queries/codeql/<language>/`.
- Set `build_mode` according to CodeQL language support:
  - `none`: python, javascript-typescript, ruby, csharp, java-kotlin.
  - `manual` or `autobuild`: c-cpp, go, csharp, java-kotlin, swift.
- Do not set `build_mode: none` for C/C++, Go, or Swift.
- Use `manual` only when you identified a concrete build command for that analysis unit.
- Use `autobuild` only as an explicit choice when build files exist but the exact command is uncertain.
- Fill in `build_command` when `build_mode` is `manual`.
- Estimate `db_create_timeout` (seconds) for each language when `build_mode` is `manual` or `autobuild`:
  - For `none` mode leave it unset; harness default is 600s.
  - Estimate based on approximate source file count, build complexity, and whether compilation is involved.
  - Rule of thumb: ~300s for small projects, ~600s for medium, ~1200-1800s for large C/C++ corpora.
  - Round up to be safe; CodeQL extraction adds significant overhead per compiled file.
- Estimate `analyze_timeout` (seconds) per profile if query packs are known to be heavy (e.g. security suites on large codebases); otherwise omit to use harness default.
- Set `recommended: false` if you cannot confidently profile any language.
- Add relevant `notes` explaining your language choices and any uncertainties.
- Update `exclude` patterns to match the target's test, fixture, vendor, and generated code directories if different from the defaults.

## Important rules

- Do not assume the target is a web application.
- Do not modify files under `src/`.
- Do not generate vulnerability findings.
- Do not produce full reconnaissance notes (attack-surface, trust-boundaries, etc.) — those are Phase 1c.
- The sandbox will be built by Phase 1b. Do not attempt sandbox work here.
- Do not run CodeQL manually. The harness runs it after Phase 1b.
- Be explicit about uncertainty.
- Prefer useful notes over exhaustive dumps.
- Focus on what later sub-stages need.
- Phase 1a does not produce attack-surface, trust-boundary, or data-flow notes.
- Phase 1a does not bootstrap sandbox.
- Non-blocking open questions should go into the run summary file.

## Final response

At the end, summarize:

- Target type and primary language(s)
- Build system and buildability assessment
- Languages selected for CodeQL analysis and their confidence levels
- Files created: `target-profile.md`, `build-model.md`, `codeql-plan.yml`
- Key uncertainties or blockers

Before ending, validate that `itemdb/notes/codeql-plan.yml` is valid and follows CodeCome rules by running:

    rtk python3 tools/codecome.py check-codeql-plan

If validation fails, repair only the reported issue before summarizing.

## Run summary

Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-1a-summary-YYYY-MM-DD-HHMMSS.md
