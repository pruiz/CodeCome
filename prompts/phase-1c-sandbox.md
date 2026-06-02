# CodeCome Phase 1c: Sandbox Bootstrap

You are performing CodeCome **Phase 1c** — the third and final sub-stage of Phase 1.

This sub-stage bootstraps the sandbox environment. Phase 1a produced the target profile and build model. Phase 1b produced the full reconnaissance notes. Your job is to leave `sandbox/` in a state where Phase 2 can run.

## Required reading

Read the following files (all paths are relative to the project/workspace root):

- `AGENTS.md`
- `codecome.yml`
- `.opencode/agents/recon.md`
- `.opencode/skills/sandbox-bootstrap/SKILL.md`
- `itemdb/notes/target-profile.md`
- `itemdb/notes/build-model.md`

## Required output

- `itemdb/notes/sandbox-plan.md`

## Workflow

1. Inspect current sandbox state:

       make sandbox-status

2. Inspect target runtime artifacts under `src/`. At minimum consider:

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

   Decide what to honor. Document the decision in `sandbox-plan.md`.

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

   `apply` refuses to overwrite a user-managed `sandbox/` (one without `CODECOME-GENERATED.md`). If the user has accepted the loss, re-run with `--force` and the prior content is moved to `sandbox/.backup-<timestamp>/`.

5b. Implement the required sandbox capabilities.

    Templates are seeds, not finished sandboxes. Each `templates/sandboxes/<id>/` ships only `Dockerfile`, `docker-compose.yml`, a starter `build.sh`, and a starter `test.sh`. After `apply`, you must leave `sandbox/` with working mechanisms for:

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

    Prefer a realistic runtime environment when it is reasonably derivable from the repository. For web apps, APIs, and other services, Phase 1c should attempt to start the real application stack, not just compile it. If the target appears to need a database, cache, queue, reverse proxy, migrations, seed data, or health checks, include those when the source tree or docs make them inferable.

    Do not stop at a toolchain-only or build-only sandbox when later Phase 4 or Phase 5 validation would realistically require a running application. If full runtime is not feasible, document the closest achievable runtime model and the blocker in `itemdb/notes/sandbox-plan.md`.

    Adapt `build.sh` and `test.sh` to the actual project layout (the source may be nested under `src/<name>/`, not directly under `src/`). Author additional scripts when they help the target (sanitizer build, fuzzing harness, debugger attach, target-specific reset, etc.). Make every script executable. Document any extras in `itemdb/notes/sandbox-plan.md` under "Extra scripts authored".

    Do not record any validation tier as `skipped` because the required capability is missing. Either implement the helper and run the tier, or accept the `failed` outcome the validator emits.

    Do not replace authoring a script with an in-chat manual spot-check. Manual checks do not survive future runs.

    See `.opencode/skills/sandbox-bootstrap/SKILL.md` for authoring conventions and the sandbox capability contract.

6. Validate:

       make sandbox-validate

   Use `BOOTSTRAP_ARGS='--keep-going'` to run all tiers even after a failure, or `--scripts-only` / `--docker-only` to constrain which mode is used.

   `validate` appends a "Validation run <ISO>" table to `sandbox/CODECOME-GENERATED.md` and returns JSON with `--format json`. Capture per-tier outcomes (passed / failed / skipped, exit code, last 50 lines of stderr) into the validation matrix in `sandbox-plan.md`. A missing required capability makes the tier `failed`; that means you still need to complete step 5b.

7. If validation fails, attempt automatic remediations within the retry budget (`CODECOME_BOOTSTRAP_MAX_RETRIES`, default 3). Each attempt must be logged in `sandbox-plan.md`. When the budget is exhausted, write the halt protocol in `sandbox-plan.md` and stop Phase 1c.

8. Special validation models:

   - `static-only`: requires explicit justification in `sandbox-plan.md`.
   - `nested-virt`: requires explicit justification and arch declaration.

## Important rules

- Do not modify files under `src/`.
- Do not overwrite a `sandbox/` that lacks `CODECOME-GENERATED.md`. If the sandbox already works, move on; if it needs replacement, halt with the halt protocol and inform the user to re-run with `--force` (which moves the prior content to `sandbox/.backup-<timestamp>/`).
- Do not generate vulnerability findings.

## Final response

At the end, summarize:

- Chosen sandbox example and `validation_model`,
- Validation outcome (`passed`, `passed-with-warnings`, `halted`),
- `itemdb/notes/sandbox-plan.md` created,
- Key limitations,
- Halt requirements if sandbox bootstrap is blocked.

## Run summary

Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-1c-summary.md
