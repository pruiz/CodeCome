# CodeCome Phase 1: Target Reconnaissance + Sandbox Bootstrap

You are performing CodeCome **Phase 1**, which has two sub-stages:

- **Phase 1a**: target reconnaissance and attack surface recognition.
- **Phase 1b**: sandbox bootstrap, validation, and provenance.

Both sub-stages must complete in the same invocation. Phase 1b
depends on the recon notes produced by Phase 1a.

## Required reading

Read:

- `AGENTS.md`
- `codecome.yml`
- `templates/target-recon.md`
- `.opencode/agents/recon.md`
- `.opencode/skills/source-recon/SKILL.md`
- `.opencode/skills/sandbox-bootstrap/SKILL.md`

Use additional target-specific skills only if they clearly apply.

Examples:

- `.opencode/skills/c-cpp-security/SKILL.md`
- `.opencode/skills/dotnet-security/SKILL.md`
- `.opencode/skills/web-security/SKILL.md`
- `.opencode/skills/juliet-benchmark/SKILL.md`

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

6. Validate:

       make sandbox-validate

   Use `BOOTSTRAP_ARGS='--keep-going'` to run all tiers even after
   a failure, or `--scripts-only` / `--docker-only` to constrain
   which mode is used.

   `validate` appends a "Validation run <ISO>" table to
   `sandbox/CODECOME-GENERATED.md` and returns JSON with
   `--format json`. Capture per-tier outcomes (passed / failed /
   skipped, exit code, last 50 lines of stderr) into the validation
   matrix in `sandbox-plan.md`.

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

## Final response

At the end, summarize:

- target type,
- most important attack surfaces,
- recommended Phase 2 focus,
- files created or updated (Phase 1a + Phase 1b),
- chosen sandbox example and `validation_model`,
- validation outcome (`passed`, `passed-with-warnings`, `halted`),
- key limitations and any user-input requests.
