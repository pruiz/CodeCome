# CodeCome Phase 1: Target Reconnaissance + Sandbox Bootstrap

You are performing CodeCome **Phase 1**, which has two sub-stages:

- **Phase 1a**: target reconnaissance and attack surface recognition.
- **Phase 1b**: sandbox bootstrap, validation, and provenance.

Both sub-stages must complete in the same invocation. Phase 1b
depends on the recon notes produced by Phase 1a.

## Required reading

Read the following files (all paths are relative to the project/workspace root):

- `AGENTS.md`
- `codecome.yml`
- `templates/target-recon.md`
- `templates/file-risk-index.yml`
- `.opencode/agents/recon.md`
- `.opencode/skills/source-recon/SKILL.md`
- `.opencode/skills/sandbox-bootstrap/SKILL.md`

Do not load target-specific security skills before first mapping the source
tree broadly. After broad structural mapping, you may consult target-specific
skills only for reconnaissance checklists, not for vulnerability deep dives or
finding generation. Do not load vulnerability-family-specific skills such as
`sql-injection` during reconnaissance unless needed only to improve
attack-surface terminology.

## Target

Analyze the source tree under:

    ./src

## Phase 1a: source reconnaissance

Build a target model by creating these files under `itemdb/notes/`:

- `target-profile.md`
- `attack-surface.md`
- `build-model.md`
- `execution-model.md`
- `trust-boundaries.md`
- `data-flow.md`
- `validation-model.md`
- `interesting-files.md`
- `file-risk-index.yml`
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

Recursively scan `src/` for high-signal documentation such as `README*`, `SECURITY*`, `THREAT_MODEL*`, `CONTRIBUTING*`, `docs/`, and similar. Also inspect `CHANGELOG*`, `HISTORY*`, and `NEWS*`, but prefer top-level or component-relevant files.

If the repository has dozens of changelog/history/news files, do not process them exhaustively. Summarize the pattern, prioritize files near the primary target or security-relevant components, and record that scope decision.

Review external public context for prior security advisories, CVE references, historical security fixes, release notes, and recurring bug classes affecting this project or closely related upstream components. Prefer project advisories, GitHub Security Advisories, NVD/CVE entries, issue trackers, release notes, and distribution advisories.

Use external context only as reconnaissance input: distill affected components, historical bug patterns, trust boundaries, and fixed attack surfaces into the notes. Do not treat external claims as proof that the current source tree is affected; verify everything against `src/` before creating findings.

Distill declared threat model, past CVEs, trust boundaries, and third-party components into the relevant notes; treat author claims as input to verify, not facts.

### File risk index

Create `itemdb/notes/file-risk-index.yml` using the schema in `templates/file-risk-index.yml`.

This is a structured, machine-readable companion to `interesting-files.md`. It is consumed by optional file-scoped Phase 2 sweeps.

Score files from 1 to 5 using the scoring scale in the template:

- `1`: low security interest,
- `2`: weak or indirect security relevance,
- `3`: moderate security interest,
- `4`: high security interest,
- `5`: very high security interest.

Prioritize files that contain or strongly influence:

- attacker-controlled or externally influenced input,
- trust-boundary crossings,
- authentication or authorization decisions,
- dangerous sinks,
- parsers and decoders,
- file upload or archive handling,
- cryptographic or secret-handling logic,
- privilege boundaries,
- tenant/account/resource isolation,
- network-facing protocol handlers,
- sandbox, policy, or permission enforcement.

For each high-risk file, include concrete reasons, likely entry points, sources, sinks, trust boundaries, suggested vulnerability classes, suggested skills, and suggested validation methods when inferable.

Do not include every source file. Prefer a concise ranked set that Phase 2 can act on. For large projects, include at least the top 20–50 files if that many are plausibly security-relevant. For small projects, include all meaningful security-relevant files.

Keep `interesting-files.md` human-readable, but make `file-risk-index.yml` the structured source for automated or semi-automated sweeps.

## Phase 1b: sandbox bootstrap

After Phase 1a notes are durable, perform sandbox bootstrap.

Goal: leave `sandbox/` in a state where Phase 2 can run.

Required output: `itemdb/notes/sandbox-plan.md`.

Workflow:

1. Inspect current sandbox state:

       make sandbox-status

2. Inspect target runtime artifacts under `src/`. At minimum
   consider:

       src/Dockerfile
       src/docker-compose.yml
       src/docker-compose.yaml
       src/compose.yml
       src/compose.yaml
       src/Makefile
       src/scripts/
       src/README*
       src/INSTALL*
       src/CONTRIBUTING*
       src/RUN*
       src/docs/

   Decide what to honor. Document the decision in
   `sandbox-plan.md`.

3. Detect candidates:

       make sandbox-detect

4. Inspect the chosen example:

       make sandbox-inspect ID=<chosen-id>

5. Apply the example:

       BOOTSTRAP_ARGS='--var KEY1=VAL1 --var KEY2=VAL2' \
         make sandbox-bootstrap ID=<chosen-id>

   Or, for a preview without writing:

       BOOTSTRAP_ARGS='--dry-run --var KEY=VAL' \
         make sandbox-bootstrap ID=<chosen-id>

   `apply` refuses to overwrite a user-managed `sandbox/` (one
   without `CODECOME-GENERATED.md`). If the user has accepted the
   loss, re-run with `--force` and the prior content is moved to
   `sandbox/.backup-<timestamp>/`.

5b. Implement the required sandbox capabilities.

    Templates are seeds, not finished sandboxes. Each
    `templates/sandboxes/<id>/` ships only `Dockerfile`,
    `docker-compose.yml`, a starter `build.sh`, and a
    starter `test.sh`. After `apply`, the agent must
    leave `sandbox/` with working mechanisms for:

        sandbox setup
        sandbox start
        sandbox sanity
        target build
        target test
        sandbox stop

    Prefer helper scripts under `sandbox/scripts/` such as:

        setup.sh   up.sh   check.sh   build.sh   test.sh

    Add operational helpers when they make sense for the target:

        down.sh   shell.sh   logs.sh   clean.sh   reset.sh

    Prefer a realistic runtime environment when it is reasonably
    derivable from the repository. For web apps, APIs, and other
    services, Phase 1b should attempt to start the real application
    stack, not just compile it. If the target appears to need a
    database, cache, queue, reverse proxy, migrations, seed data,
    or health checks, include those when the source tree or docs
    make them inferable.

    Do not stop at a toolchain-only or build-only sandbox when
    later Phase 4 or Phase 5 validation would realistically require
    a running application. If full runtime is not feasible,
    document the closest achievable runtime model and the blocker in
    `itemdb/notes/sandbox-plan.md`.

    Adapt `build.sh` and `test.sh` to the actual
    project layout (the source may be nested under
    `src/<name>/`, not directly under `src/`). Author additional
    scripts when they help the target (sanitizer build, fuzzing
    harness, debugger attach, target-specific reset, etc.).
    Make every script executable. Document any extras in
    `itemdb/notes/sandbox-plan.md` under "Extra scripts authored".

    Do not record any validation tier as `skipped` because the
    required capability is missing. Either implement the helper and
    run the tier, or accept the `failed` outcome the validator emits.

    Do not replace authoring a script with an in-chat manual
    spot-check. Manual checks do not survive future runs.

    See `.opencode/skills/sandbox-bootstrap/SKILL.md` for
    authoring conventions and the sandbox capability contract.

6. Validate:

       make sandbox-validate

   Use `BOOTSTRAP_ARGS='--keep-going'` to run all tiers even after
   a failure, or `--scripts-only` / `--docker-only` to constrain
   which mode is used.

   `validate` appends a "Validation run <ISO>" table to
   `sandbox/CODECOME-GENERATED.md` and returns JSON with
   `--format json`. Capture per-tier outcomes (passed / failed /
   skipped, exit code, last 50 lines of stderr) into the validation
    matrix in `sandbox-plan.md`. A missing required capability makes
    the tier `failed`; that means you still need to complete step 5b.

7. If validation fails, attempt automatic remediations within the
   retry budget (`CODECOME_BOOTSTRAP_MAX_RETRIES`, default 3). Each
   attempt must be logged in `sandbox-plan.md`. When the budget is
   exhausted, write the halt protocol in `sandbox-plan.md` and
   stop Phase 1b.

8. Special validation models:

   - `static-only`: requires explicit justification in
     `sandbox-plan.md`.
   - `nested-virt`: requires explicit justification and arch
     declaration.

## Important rules

- Do not assume the target is a web application.
- Do not assume the target can be built.
- Do not assume the target can be executed.
- Do not modify files under `src/`.
- Do not generate low-confidence vulnerability findings during
  reconnaissance.
- Do not rely only on filenames, comments, or labels.
- Do not silently overwrite a `sandbox/` that lacks
  `CODECOME-GENERATED.md`. Validate first; if it works, move on; if
  it does not, halt with the halt protocol.
- Be explicit about uncertainty.
- Prefer useful notes over exhaustive dumps.
- Focus on what later phases need.
- Do not let any target-specific skill narrow the target model before broad
  mapping is complete.
- Do not ask the user to choose Phase 2 scope when a reasonable default can
  be inferred. Pick the primary target from repository evidence, document
  secondary surfaces as optional follow-up, and continue.
- Do not phrase optional preferences as "User input requested". Use
  "Optional follow-up" unless Phase 1 halted.
- Reading `.env` files is allowed only in two places during reconnaissance:
  target inputs under `src/**` and CodeCome-generated sandbox metadata in
  `sandbox/.env`. Avoid unrelated `.env` files elsewhere in the workspace.

## Final response

At the end, summarize:

- target type,
- most important attack surfaces,
- recommended Phase 2 focus,
- highest-risk files from `file-risk-index.yml`,
- files created or updated (Phase 1a + Phase 1b),
- chosen sandbox example and `validation_model`,
- validation outcome (`passed`, `passed-with-warnings`, `halted`),
- key limitations,
- halt requirements if Phase 1 is blocked,
- optional follow-up scope controls users may pass via `PROMPT_EXTRA` or
  `PROMPT_EXTRA_FILE`.

Run `make frontmatter` to ensure the generated file risk index has valid YAML and fix any reported errors before finishing.
