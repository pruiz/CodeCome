# CodeQL + Sandbox Recipe Refactor Plan

Status: **Locked plan — implementation in progress**

Branch purpose: define the target architecture and implementation plan before changing runtime code.

## 1. Problem statement

The current CodeQL integration is fragile because Phase 1 runs CodeQL before CodeCome has built a reliable sandbox/build environment. For compiled languages such as C/C++, Java/Kotlin, Go, C#, and Swift, CodeQL database creation needs to observe or execute the real build. Today the model generates a `codeql-plan.yml` in Phase 1a, then the harness executes CodeQL directly from the host, and only later Phase 1c creates the sandbox.

This creates several issues:

1. CodeQL build commands are guessed too early.
2. The harness executes CodeQL in the host environment even when the target's real build belongs inside Docker.
3. Sandbox build discovery and CodeQL build discovery are duplicated.
4. CodeQL can appear successful even when the database is effectively useless.
5. Phase 1b/Phase 2 can consume stale or misleading CodeQL artifacts.
6. The current Phase 1 subphase naming and documentation have already drifted: sandbox is currently implemented as Phase 1c, while some sandbox bootstrap docs still describe it as Phase 1b.

The refactor should make CodeQL best-effort but trustworthy: failures or empty/invalid databases must be detected and reported as unusable, not silently treated as useful zero-alert analysis.

## 2. Design goals

1. Keep CodeQL optional. `CODEQL=0` or an equivalent configuration must let all later phases run without CodeQL dependencies.
2. Keep CodeQL best-effort by default. A failed or unusable CodeQL run should not block Phase 1 under soft policy.
3. Prevent false success. A CodeQL run that returns exit code 0 but produces no usable extraction/SARIF must be classified as unusable.
4. Use the sandbox build environment as the source of truth for compiled-language CodeQL database creation.
5. Preserve multi-unit CodeQL analysis. A target may contain multiple analysis units with different languages/stacks.
6. Avoid forcing multiple sandboxes. Prefer one sandbox per target, with multiple build targets declared in a machine-readable recipe when needed.
7. Keep `codeql-plan.yml` as the CodeQL-specific analysis control document, but reduce its responsibility: it should describe what to analyze, not invent the final build environment.
8. Add `sandbox-recipe.yml` under `itemdb/notes/` as the durable machine-readable contract between sandbox bootstrap and later harness steps.
9. Reorder Phase 1 so sandbox/bootstrap happens before CodeQL and detailed recon happens after CodeQL.
10. Do a full naming/documentation/test sweep so Phase 1a/1b/1c references are consistent.

## 3. Target architecture

### 3.1 New Phase 1 order

Current order:

```text
Phase 1a: Target Profile + build model + CodeQL plan
CodeQL: host-side execution
Phase 1b: Detailed Reconnaissance
Phase 1c: Sandbox Bootstrap
```

Target order:

```text
Phase 1a: Target Profile + build model + CodeQL intent
Phase 1b: Sandbox Bootstrap + sandbox-recipe.yml
CodeQL: run using codeql-plan.yml + sandbox-recipe.yml
Phase 1c: Detailed Reconnaissance enriched with CodeQL health/signals
```

Rationale:

- The sandbox phase has the best chance of discovering and stabilizing the real build/runtime model.
- CodeQL for compiled languages should run after that environment exists.
- Recon should consume reliable CodeQL health/signals, not stale or misleading outputs.

### 3.2 Responsibilities by artifact

#### `itemdb/notes/codeql-plan.yml`

Purpose: CodeQL analysis intent.

Should define:

- analysis units;
- source paths;
- languages and confidence;
- CodeQL profiles/packs;
- exclude patterns;
- whether a unit/language is recommended for CodeQL;
- which sandbox build target should be used, when a build is required.

Should not be responsible for:

- installing toolchains;
- deciding Docker compose details;
- generating long shell snippets;
- fully describing sandbox runtime;
- repairing build scripts.

#### `itemdb/notes/sandbox-plan.md`

Purpose: human-readable sandbox decisions.

Already exists conceptually. It should continue to document:

- detected stack;
- selected sandbox seed;
- runtime model;
- services;
- validation matrix;
- limitations;
- remediation attempts;
- open questions.

#### `itemdb/notes/sandbox-recipe.yml`

Purpose: machine-readable recipe for later harness steps.

It should describe how to use the generated sandbox and how buildable units map to commands/services/workdirs. CodeQL consumes this file.

## 4. `sandbox-recipe.yml` schema proposal

Initial schema:

```yaml
schema_version: 1
generated_by: phase-1b-sandbox
validation_model: docker  # docker | static-only | nested-virt

sandbox:
  path: ./sandbox
  managed: true
  compose_file: ./sandbox/docker-compose.yml
  default_service: app
  workspace_root: /workspace
  source_root: /workspace/src

commands:
  setup: ./sandbox/scripts/setup.sh
  up: ./sandbox/scripts/up.sh
  check: ./sandbox/scripts/check.sh
  build: ./sandbox/scripts/build.sh
  test: ./sandbox/scripts/test.sh
  down: ./sandbox/scripts/down.sh
  shell: ./sandbox/scripts/shell.sh
  logs: ./sandbox/scripts/logs.sh
  clean: ./sandbox/scripts/clean.sh
  reset: ./sandbox/scripts/reset.sh

build_targets:
  - id: root
    description: Default target build
    source_path: ./src
    service: app
    workdir: /workspace/src
    build_command: ./sandbox/scripts/build.sh
    test_command: ./sandbox/scripts/test.sh
    environment:
      type: docker-compose
      compose_file: ./sandbox/docker-compose.yml
      service: app
    codeql:
      supported: true
      preferred_execution_mode: docker-inside
      install_strategy: mount-host-bundle
      notes: []

codeql:
  supported: true
  default_execution_mode: docker-inside
  install_strategy: mount-host-bundle
  notes:
    - CodeQL is optional and best-effort.
    - Compiled-language database creation should use build_targets rather than host guesses.

limitations: []
```

### 4.1 Multi-unit / multi-target handling

One sandbox can expose several `build_targets`:

```yaml
build_targets:
  - id: native-lib
    source_path: ./src/native
    service: app
    workdir: /workspace/src/native
    build_command: ./sandbox/scripts/build-native-lib.sh
    codeql:
      supported: true
      preferred_execution_mode: docker-inside

  - id: cli
    source_path: ./src/cli
    service: app
    workdir: /workspace/src/cli
    build_command: ./sandbox/scripts/build-cli.sh
    codeql:
      supported: true
      preferred_execution_mode: docker-inside
```

Rules:

1. Simple targets may define only `root` or `default`.
2. Multi-component targets should define one build target per materially distinct build component only when it improves reproducibility.
3. `sandbox/scripts/build.sh` may remain the canonical aggregate build hook.
4. Specific scripts such as `build-native-lib.sh` are optional and should be generated only when useful.
5. CodeQL analysis units map to build targets through `codeql-plan.yml`.
6. A missing build target for a compiled-language CodeQL unit should soft-fail that unit honestly under soft policy.

## 5. `codeql-plan.yml` schema direction

Keep a CodeQL-specific plan, but update the schema to version 2.

Example:

```yaml
schema_version: 2
generated_by: phase-1a-profile
source_path: ./src
recommended: true

analysis_units:
  - id: native-lib
    path: ./src/native
    kind: library
    primary: true
    sandbox_build_target: native-lib
    languages:
      - id: c-cpp
        confidence: HIGH
        build_mode: manual
        build_provider: sandbox-recipe
        profiles:
          - official
          - github-security-lab
          - trailofbits

  - id: scripts
    path: ./src/scripts
    kind: tooling
    primary: false
    sandbox_build_target: root
    languages:
      - id: python
        confidence: MEDIUM
        build_mode: none
        build_provider: none
        profiles:
          - official

exclude:
  - src/**/tests/**
  - src/**/fixtures/**
  - src/**/vendor/**

notes:
  - Build commands are resolved through sandbox-recipe.yml after sandbox bootstrap.
```

### 5.1 Build rules

For languages with `build_mode: none`:

- `sandbox_build_target` is optional.
- CodeQL may run host-side or docker-side depending on runner support.
- No build command is required.

For compiled languages with `build_mode: manual`:

- prefer `build_provider: sandbox-recipe`;
- require `sandbox_build_target` unless a legacy/manual host command is explicitly supported;
- resolve final command from `sandbox-recipe.yml`.

For `build_mode: autobuild`:

- only use as fallback;
- record why a sandbox build target was not available;
- classify health carefully, because autobuild success can still produce poor extraction.

## 6. CodeQL execution backends

Add explicit execution modes:

```text
host
  Run CodeQL on the host. Suitable for no-build languages or legacy fallback.

docker-inside
  Run CodeQL inside the sandbox container/service. Preferred for compiled languages.

docker-wrapper
  Host-side CodeQL invokes a Docker command as build command. Not preferred because extraction may not observe compilation correctly.

unavailable
  CodeQL cannot run for this unit in this environment.
```

### 6.1 Preferred compiled-language path

For compiled languages:

1. Resolve analysis unit from `codeql-plan.yml`.
2. Resolve `sandbox_build_target` from `sandbox-recipe.yml`.
3. Ensure sandbox has passed setup/check/build validation.
4. Ensure CodeQL CLI is available inside the sandbox environment.
5. Execute `codeql database create` inside the same container/service and workdir used to build the target.
6. Run `codeql database analyze` for selected profiles.
7. Run health checks.
8. Publish normalized signals only if usable.

### 6.2 CodeQL installation strategy in Docker

Support multiple strategies:

```yaml
install_strategy: mount-host-bundle
```

Mount the locally installed CodeQL bundle into the sandbox container read-only.

```yaml
install_strategy: copy-host-bundle
```

Copy CodeQL into a temporary location mounted or copied into the container.

```yaml
install_strategy: image-preinstalled
```

Assume the sandbox image already includes CodeQL.

Initial implementation can support only `mount-host-bundle`, then add others if needed.

## 7. CodeQL health model

Create a new health layer, probably `tools/codeql/health.py`.

### 7.1 Health output

Every CodeQL run should write a health block to the manifest:

```yaml
health:
  usable: false
  classification: extraction-failed
  reason: CodeQL database create returned success but extractor_successes was 0 and extractor_failures was 1.
  checks:
    database_create_exit_zero: true
    database_exists: true
    analyze_exit_zero: false
    official_profile_analyzed: false
    sarif_fresh: false
    normalized_fresh: false
    extractor_successes: 0
    extractor_failures: 1
    trap_files_detected: 0
```

### 7.2 Classifications

Use stable classifications:

```text
disabled
skipped
unavailable
failed
soft-failed
extraction-failed
analysis-failed
completed-empty-valid
completed-with-signals
completed-partial
stale-output-detected
```

### 7.3 Usability rules

A run is usable only if:

1. CodeQL database creation exit code is 0.
2. The database directory exists and passes basic sanity checks.
3. At least the official profile analyze step succeeds, or an explicit profile-equivalent step succeeds.
4. At least one fresh SARIF file exists for the current run.
5. Normalized outputs were generated from fresh SARIF from the current run.
6. For compiled languages, extraction is non-empty.

A run may have zero alerts and still be usable. Zero alerts is not a failure.

A run is not usable if:

1. SARIF is missing.
2. normalized outputs are stale.
3. extractor successes are zero for a compiled language.
4. all query profiles fail.
5. database creation returns success but no analyzable content is present.

### 7.4 Compiled-language extraction checks

Prefer robust signals in this order:

1. CodeQL diagnostics that report extractor successes/failures.
2. TRAP/import counts if available.
3. Database metadata containing source/archive information.
4. Presence of extracted files under expected source roots.

The plan implementation should include a spike task to inspect real CodeQL DB layout and diagnostic files for C/C++, Java/Kotlin, Go, C#, and Swift.

## 8. Artifact layout

No need to maintain backward compatibility, but keep the layout understandable.

Recommended layout:

```text
itemdb/codeql/
  runs/
    <run-id>/
      run-manifest.yml
      health.yml
      selected-query-packs.yml
      sarif/
      normalized/
      databases/
      logs/
      codeql-summary.md
  last-run-manifest.yml
  current-run.txt
```

Rules:

1. Every run gets a unique run id.
2. The runner never normalizes stale SARIF.
3. The runner never reports `Total alerts: 0` unless SARIF was fresh and normalized for the current run.
4. `last-run-manifest.yml` always describes the last attempt, even if unusable.
5. `current-run.txt` points to the latest usable run if one exists, or may be absent if none exists.
6. Recon consumes `last-run-manifest.yml` for health and the current usable run for normalized signals.

## 9. Phase 1 orchestration changes

Update `tools/codecome/phase_1.py`:

1. Rename or relabel subphases:
   - `1a`: Target Profile
   - `1b`: Sandbox Bootstrap
   - `1c`: Detailed Reconnaissance
2. Move CodeQL execution after `check_phase_1b` and before Phase 1c.
3. Run CodeQL only after sandbox recipe validation succeeds.
4. If CodeQL is disabled, record a skipped/disabled manifest and continue.
5. If CodeQL soft-fails or is unusable, continue but make health explicit.
6. Remove or rewrite the current CodeQL repair loop that resumes the model to patch `codeql-plan.yml` after host-side failures. Re-introduce repair only around sandbox recipe/build target problems if it is still useful.
7. Ensure all gates point to the correct renamed phase artifacts.

## 10. Prompt changes

### 10.1 `prompts/phase-1a-profile.md`

Update to:

- produce `target-profile.md`, `build-model.md`, and schema v2 `codeql-plan.yml`;
- identify analysis units and desired CodeQL coverage;
- avoid concrete build shell snippets unless obvious and stable;
- set `build_provider: sandbox-recipe` for compiled languages when a build is required;
- state that the sandbox phase will resolve the final build recipe.

### 10.2 New/renamed `prompts/phase-1b-sandbox.md`

Update from current sandbox prompt:

- sandbox is now Phase 1b;
- required outputs:
  - `itemdb/notes/sandbox-plan.md`;
  - `itemdb/notes/sandbox-recipe.yml`;
- require validation of both sandbox and recipe;
- require multi-target recipe entries when the target has materially distinct build components;
- do not force per-unit scripts if a single aggregate build is correct.

### 10.3 New/renamed `prompts/phase-1c-recon.md`

Update from current recon prompt:

- recon is now Phase 1c;
- read Phase 1a and 1b outputs;
- read CodeQL health from `itemdb/codeql/last-run-manifest.yml` when present;
- only consume normalized CodeQL signals when health says usable;
- never infer "no issues" from unusable CodeQL;
- include CodeQL health in `threat-model.md`, `interesting-files.md`, and `file-risk-index.yml` only when relevant.

## 11. Skill/documentation updates

Audit and update all references to old Phase 1 ordering.

Required search terms:

```text
Phase 1b
Phase 1c
phase-1b
phase-1c
phase_1b
phase_1c
Detailed Reconnaissance
Sandbox Bootstrap
CodeQL analysis between 1a and 1b
between 1a and 1b
```

Likely files:

- `tools/codecome/phase_1.py`
- `tools/phases/completion.py`
- `tools/phases/phase_1_gates.py`
- `tools/phases/artifact_checks.py`
- `prompts/phase-1a-profile.md`
- `prompts/phase-1b-recon.md`
- `prompts/phase-1c-sandbox.md`
- `.opencode/skills/sandbox-bootstrap/SKILL.md`
- `.opencode/skills/sandbox-validation/SKILL.md`
- `.opencode/agents/recon.md`
- `docs/workflow.md`
- `docs/sandbox.md`
- `templates/sandboxes/README.md`
- `README.md`
- tests referencing subphase names, required artifacts, or phase order.

## 12. Sandbox bootstrap CLI changes

Update `tools/sandbox-bootstrap.py` to support recipe validation/generation helpers.

Potential subcommands:

```text
sandbox-recipe-validate
sandbox-recipe-print
```

Or integrate into existing `validate` output.

Minimum required checks:

1. `itemdb/notes/sandbox-recipe.yml` exists after Phase 1b.
2. `schema_version` is supported.
3. `validation_model` is valid.
4. `sandbox.path` exists.
5. Declared command paths exist when applicable.
6. `build_targets` is non-empty unless validation model is `static-only` or explicitly buildless.
7. Each build target has unique id.
8. Each build target source path exists.
9. Each build target workdir is absolute inside the sandbox environment.
10. Each build target command is present or explicitly marked not applicable.
11. CodeQL hints use supported values.

The agent may write the recipe, but the harness must validate it.

## 13. CodeQL module changes

### 13.1 `tools/codeql/packs.py`

Update plan loader to support schema v2.

Tasks:

- accept schema v2;
- validate `sandbox_build_target` and `build_provider`;
- preserve schema v1 only if we intentionally support migration during development, otherwise fail with actionable message;
- update tests.

### 13.2 `tools/codeql/runner.py`

Refactor to:

- load `codeql-plan.yml`;
- load and validate `sandbox-recipe.yml`;
- build an effective execution plan;
- execute per unit/language using selected backend;
- write per-run artifacts under `itemdb/codeql/runs/<run-id>/`;
- record per-unit command logs;
- never reuse stale SARIF/normalized outputs;
- call health evaluation before publishing usable results.

### 13.3 `tools/codeql/pipeline.py`

Refactor around run directories.

Tasks:

- create run id;
- pass run directory to runner;
- normalize only current-run SARIF;
- import file risk only from usable current-run signals;
- write summary from health and normalized results;
- update `last-run-manifest.yml`.

### 13.4 `tools/codeql/artifacts.py`

Replace current weak artifact gate.

Current gate mainly checks manifest status and normalized files. New gate should check health classification and usability.

Rules:

- hard policy may block on `health.usable=false` when CodeQL was expected and enabled;
- soft policy never blocks Phase 1, but emits clear warnings;
- disabled/skipped CodeQL is not an error under soft policy;
- stale output is always warning or failure depending on policy.

### 13.5 New `tools/codeql/health.py`

Implement health classification.

Inputs:

- effective execution plan;
- process exit statuses;
- generated DB paths;
- CodeQL logs;
- SARIF paths;
- normalized paths;
- diagnostics/extractor metadata.

Outputs:

- health dict;
- `health.yml`;
- warnings/failures for manifest.

## 14. Repair/resume model

The current CodeQL repair loop resumes the model after CodeQL database creation fails. That model is less effective because CodeQL currently runs outside the sandbox/build context.

Target behavior:

1. Repair sandbox in Phase 1b if sandbox validation or `sandbox-recipe.yml` validation fails.
2. Run CodeQL after sandbox validation.
3. If CodeQL fails because the recipe is inconsistent, classify the unit and optionally request a targeted sandbox-recipe repair in the same Phase 1b session only if safe.
4. Avoid repeated expensive CodeQL retries by default.
5. Use a small retry budget and only rerun affected units.

Initial implementation can remove CodeQL model-repair entirely and rely on clear health output. Add repair back only after the deterministic path is solid.

## 15. Handling user-managed sandboxes

Current sandbox gate allows user-managed sandboxes with warnings. This should remain possible.

If sandbox is user-managed:

1. Phase 1b must still create `itemdb/notes/sandbox-recipe.yml`, either by inspecting the user-managed sandbox or documenting that no recipe can be derived.
2. If no recipe can be derived, CodeQL compiled-language units should become `unavailable` under soft policy.
3. Phase 1 can continue under soft policy.
4. The user should see clear remediation instructions.

## 16. Handling static-only and nested-virt

For `static-only`:

- `sandbox-recipe.yml` may have no build targets or build targets marked `not_applicable`.
- CodeQL no-build languages may still run.
- Compiled-language CodeQL should be `unavailable` unless a build target exists.

For `nested-virt`:

- CodeQL probably defaults to `unavailable` unless the recipe explicitly declares support.
- Do not try to force CodeQL into VM-based targets during initial refactor.

## 17. Tests

Add or update tests for:

1. Phase 1 orchestration order.
2. New subphase labels and prompts.
3. Phase completion artifact lists.
4. `sandbox-recipe.yml` validation success/failure.
5. Simple single-target recipe.
6. Multi-target recipe.
7. CodeQL plan schema v2 validation.
8. CodeQL plan mapping to sandbox build targets.
9. Missing build target for compiled language => soft-failed/unavailable.
10. `build_mode: none` language works without build target.
11. Run directory creation.
12. No stale SARIF normalization.
13. Health classification: no SARIF.
14. Health classification: extractor successes = 0.
15. Health classification: zero alerts but fresh SARIF => usable empty valid.
16. Health classification: partial extraction => usable with warnings.
17. Soft policy does not block Phase 1.
18. Hard policy blocks on unusable CodeQL when enabled.
19. Recon prompt uses health rules.
20. Docs/skills no longer contain old contradictory Phase 1b/1c descriptions.

## 18. Acceptance criteria

Implementation is complete when:

1. `make phase-1` runs phases in the new order.
2. Phase 1b creates both `sandbox-plan.md` and `sandbox-recipe.yml`.
3. CodeQL runs after sandbox validation.
4. CodeQL compiled-language database creation uses sandbox recipe by default.
5. A CodeQL run with no real extraction is not classified as successful/usable.
6. A CodeQL run with zero alerts but valid SARIF/extraction is classified as usable empty valid.
7. Stale SARIF/normalized outputs cannot be mistaken for current run results.
8. Phase 1c recon only uses CodeQL signals when health says usable.
9. Phase 2+ does not depend on CodeQL when CodeQL is disabled or unusable.
10. Soft policy continues the audit with clear warnings.
11. Hard policy blocks only according to explicit, documented health rules.
12. All references to old Phase 1b/1c responsibilities are updated.
13. Tests cover single-target and multi-target recipe mapping.
14. Docs explain the new architecture and how to troubleshoot CodeQL health.

## 19. Implementation sequence (8 incremental commits)

Each commit must compile (no import errors) and pass `make tests` independently.
Existing `itemdb/` content is ignored — the refactor does not read, migrate, or delete
any data under `itemdb/notes/` or `itemdb/findings/`.

### Commit 1 — `chore: introduce sandbox-recipe schema + validator`

- Add `templates/sandbox-recipe.yml.example` (the schema sample from §4).
- Add `tools/sandbox/__init__.py` and `tools/sandbox/recipe.py` with `load_recipe(path)`,
  `validate_recipe(recipe)`, and the validation rule list from plan §12.
- Expose `recipe-validate` and `recipe-print` subcommands on `tools/sandbox-bootstrap.py`
  (extend, don't fork; CLI flags per `tools/AGENTS.md` rule 1).
- Add `tests/test_sandbox_recipe.py` covering: minimal valid recipe, missing required keys,
  duplicate build_target ids, workdir not absolute, validation_model not in allow-list,
  build_targets empty under docker model, codeql.install_strategy not in allow-list.
- Update `docs/sandbox.md` and `templates/sandboxes/README.md` to mention the recipe.

### Commit 2 — `feat(codeql-plan): bump schema to v2 + v1 hard-fail`

- Add `schema_version: 2` loader path in `tools/codeql/packs.py`; v1 raises `PackResolverError`
  with a clear "re-run Phase 1a" message (per decision on no auto-migration).
- Extend `analysis_units[].languages[]` to accept `build_provider: sandbox-recipe | none`
  and `sandbox_build_target: <id>` on the parent analysis unit.
- Edit `templates/codeql-plan.yml` in place to v2 schema.
- Update `tools/phases/phase_1_gates.py` for v2; add a test in `tests/test_phase_1_gates.py`
  asserting v1 raises error at gate 1a.
- Update `prompts/phase-1a-profile.md` content to v2 + the no-build-shell-snippet rule (§10.1).
- Update `tests/test_codecome_check_codeql.py` and `tests/test_codeql_packs.py` fixtures.

### Commit 3 — `feat(sandbox-bootstrap): require recipe output in Phase 1b`

- Rename `prompts/phase-1c-sandbox.md` → `prompts/phase-1b-sandbox.md` and update internal
  references ("Phase 1c" → "Phase 1b", "third and final" → "second", "after Phase 1a/1b" →
  "after Phase 1a").
- Update prompt to require `sandbox-recipe.yml` as a **durable output** alongside
  `sandbox-plan.md`, with the per-target structure and CodeQL hints.
- Add `validate_recipe` call to the existing `tools/sandbox-bootstrap.py validate` flow.
- New test in `tests/test_sandbox_bootstrap.py` covering the recipe-required gate.

### Commit 4 — `feat(codeql): add per-run layout, run-id, and health model`

- New `tools/codeql/health.py` implementing the schema from plan §7 (`compute_health(plan,
  recipe, run_dir, manifest)` returning a `health` dict, the full `health.yml`, and
  warnings/failures).
- Update `tools/codeql/pipeline.py`:
  - create run_id (UTC timestamp + short hash);
  - lay out under `itemdb/codeql/runs/<run-id>/{sarif,normalized,databases,logs,
    codeql-summary.md}`;
  - copy per-run `run-manifest.yml` and `health.yml` into the run dir;
  - write `itemdb/codeql/last-run-manifest.yml`;
  - write `itemdb/codeql/current-run.txt` only when `health.usable == true`.
- Update `tools/codeql/runner.py` to consume the new layout and pass a per-run dir.
- Update `tools/codeql/artifacts.py` to gate on `health.usable` for hard policy;
  remain warning-only under soft policy (§13.4).
- Add `tests/test_codeql_health.py` with cases for every classification in §7.2.

### Commit 5 — `feat(codeql): docker-inside execution + host/sandbox platform guard`

- New `tools/codeql/platform.py` with `host_platform() -> str` and
  `container_platform(service_path, compose_path) -> str` (runs `uname -sm` in container
  via `docker compose exec`).
- New `tools/codeql/in_docker.py` helper that wraps CodeQL invocation through
  `docker compose exec` against the recipe's declared service.
- New `sandbox/scripts/codeql.sh` added to `templates/sandboxes/_shared/` (the wrapper
  script that the runner calls; resolves the compose file and service from recipe and
  forwards args to the in-container codeql binary).
- Update all `templates/sandboxes/<id>/docker-compose.yml` templates to bind-mount the
  host CodeQL bundle read-only at `/opt/codeql` and ensure it is on PATH.
- **Host/sandbox platform guard**: before each `docker-inside` invocation, the runner
  compares `host_platform()` to `container_platform()`. If they differ (e.g. macOS host
  with a Linux container — the exact case in many developer workspaces), the unit is
  classified as `unavailable` with reason `"CodeQL bundle is for {host_platform};
  sandbox service runs {container_platform}. install_strategy=mount-host-bundle cannot
  cross platforms."`. `health.usable` becomes false; the manifest records the failure
  clearly. Future implementation may add `download-in-container` or `image-preinstalled`
  to handle the cross-platform case.
- Add `tests/test_codeql_platform.py` and `tests/test_codeql_in_docker.py`.
- Add a "CodeQL install strategy" section to `docs/sandbox.md` documenting the limitation.

### Commit 6 — `refactor(phase-1): reorder to 1a→1b(sandbox)→CodeQL→1c(recon), stop referencing repair`

- Rename `prompts/phase-1b-recon.md` → `prompts/phase-1c-recon.md`; update internal copy
  ("Phase 1b" → "Phase 1c", "second" → "third and final") and add the health-aware
  language from plan §10.3.
- `tools/codecome/phase_1.py`:
  - Delete `_run_codeql_repair_if_needed`, `_codeql_repair_needed`,
    `_codeql_repair_failure_context`, `_file_digest`, `_validate_codeql_plan_for_repair`,
    all `_validate_codeql_build_command*` helpers. Build-command validation moves to the
    runner's resolver and to `load_recipe`.
  - Delete the `phase-1-codeql-repair` branch in `_subphase_should_validate_codeql_plan`.
  - Reorder `run_phase_1` to: `1a → 1b (sandbox) → _run_codeql (post-sandbox) → 1c (recon)`.
  - `_check_codeql_artifacts` now reads `health.usable` from `last-run-manifest.yml`.
- `tools/phases/completion.py`: drop `build_codeql_plan_resume_prompt` and
  `build_codeql_build_failure_resume_prompt`. Keep `build_artifact_repair_resume_prompt`
  (still used for Phase 1b artifact repair).
- `tools/phases/phase_1_gates.py`: rename message strings for the new 1b/1c order.
- `tools/codecome/phase_1.py`: stop calling `prompts/phase-1-codeql-repair.md`
  (keep the file in tree until cleanup in commit 8).
- `tools/gate-check.py` and `tools/codecome.py check-phase-artifacts`: update subphase
  labels in messages (no logic change).
- Update all affected tests: `test_phase_1_gates.py`, `test_phase_1_mid_turn_forgiveness.py`,
  `test_phase_graceful_completion_subphases.py`, `test_phase_1_prompts_threat_model.py`,
  `test_phases_completion.py`.

### Commit 7 — `docs+prompts+skills: full sweep of Phase 1b/1c references`

- `docs/workflow.md` and `docs/sandbox.md`: rewrite Phase 1 sections per §3.1 new order.
- `Makefile` help text only: "Sandbox bootstrap (Phase 1c)" → "Sandbox bootstrap (Phase 1b)".
- `prompts/phase-1a-profile.md` (line ~97): change "Do not bootstrap the sandbox — that is
  Phase 1c" → "The sandbox will be built by Phase 1b. Do not attempt sandbox work here."
- `prompts/phase-1b-sandbox.md`: add explicit "you MUST write `sandbox-recipe.yml`" section.
- `prompts/phase-1c-recon.md`: add explicit "you MUST read `last-run-manifest.yml`" section
  and the health-aware reading rules (§10.3).
- `prompts/sweep.md` and `prompts/phase-6-report.md`: add a one-liner that consumers
  consult `itemdb/codeql/last-run-manifest.yml` for `health.usable` before importing signals.
- `.opencode/skills/sandbox-validation/SKILL.md` and `.opencode/agents/recon.md`:
  spot-check and update any stale subphase-label references.
- Add `tests/test_prompts.py` grep guard that asserts no prompt files contain contradictory
  Phase 1b/1c language.
- `templates/sandboxes/README.md`: update if needed.

### Commit 8 — `chore: delete obsolete repair files, add future-repair section, full test + smoke`

- Delete `prompts/phase-1-codeql-repair.md` and `tests/test_phase_1_codeql_plan_repair.py`.
- Append the "Future: targeted sandbox-recipe repair" section (§22) to this plan file.
- Run `make tests` (pytest + frontmatter gate) and fix any remaining regressions.
- Manual smoke matrix:
  - Python/no-build target;
  - C/C++ target with Docker build;
  - multi-component target with one aggregate build;
  - target with CodeQL disabled.
- **Skip** the macOS-host × Linux-container CodeQL smoke case (known unsupported under
  the current `mount-host-bundle` only strategy) and link to the platform-guard test.
- Record results in `runs/smoke-2026-MM-DD.md`.

## 20. Resolved implementation decisions

1. **CodeQL-in-Docker install strategy**: `mount-host-bundle` only for initial
   implementation. A host-vs-sandbox platform guard classifies cross-platform
   cases (e.g. macOS host with Linux container) as `unavailable`. Future
   strategies (`download-in-container`, `image-preinstalled`) are documented
   for follow-up.
2. **Run tracking**: plain marker file `current-run.txt` for portability (no
   symlinks). `last-run-manifest.yml` always describes the last attempt
   regardless of usability.
3. **Schema v1 migration**: no auto-migration. v1 raises a clear upgrade error.
   The user re-runs Phase 1a to regenerate as v2.
4. **CodeQL repair**: removed in code but the prompt file
   (`prompts/phase-1-codeql-repair.md`) stays in tree until the final cleanup
   (commit 8). A future-design section (§23) describes how it may be
   reintroduced if needed.
5. **Sandbox recipe validation**: lives in new `tools/sandbox/recipe.py`
   module; exposed through the existing `tools/sandbox-bootstrap.py` CLI.
6. **Existing itemdb data**: ignored during the refactor. No migration, no
   reads, no deletes of content under `itemdb/notes/` or `itemdb/findings/`.
7. **Multi-target invocation**: the runner resolves `Sandbox_build_target` from
   the recipe per (analysis unit, language) pair and invokes CodeQL with the
   resolved `build_command`. Identical commands across targets are allowed;
   CodeQL's extractor is per-database so observing the same build multiple
   times is harmless.
8. **Per-target script contract**: the recipe's `build_targets[].build_command`
   is a free-form shell command (not a path to a script). The model may write
   the same command for all targets or different commands per target.
9. **Recon health trigger**: Phase 1c reads `last-run-manifest.yml`. When
   `health.usable == true`, CodeQL signals are imported into
   `file-risk-index.yml` and `interesting-files.md`. When `health.usable ==
   false`, recon skips signal import but records the health summary in
   `threat-model.md` under a new `# CodeQL health` heading.
10. **`test_mock_llm_parity.py`**: no update needed — it does not simulate
    Phase 1 subphases (its scope is event normalization and generic end-to-end
    mock LLM runs).
11. **Files under `.opencode/`**: skills (`*.md`) and agent definitions are
    part of the harness and may be read and modified during the refactor.
    Root `AGENTS.md` and `codecome.yml` remain untouched.

## 21. Scope

**Modify** (allowed write paths per commit plan):
- `tools/` (all packages: codecome, codeql, phases, sandbox)
- `prompts/` (rename, rewrite, delete)
- `templates/` (codeql-plan.yml, sandbox-recipe.yml.example, sandboxes/)
- `docs/` (workflow.md, sandbox.md)
- `Makefile` (help text only, no orchestration changes)
- `.opencode/skills/*/SKILL.md` and `.opencode/agents/*.md` (spot-check + update)
- `tests/` (add new, update existing, delete obsolete)
- `.project/codeql-sandbox-recipe-refactor-plan.md` (this file)

**Do NOT modify**:
- Root `AGENTS.md`
- `codecome.yml`
- `README.md`
- `LICENSE`, `CONTRIBUTING.md`, `NOTICE`
- `src/` (target source code)
- `itemdb/` (existing audit data)
- `.venv/`, `.cache/`
- `sandbox/` (existing sandbox state — templates under `templates/sandboxes/` are modified, not `sandbox/` itself)

## 22. Non-goals

1. Do not special-case Juliet or other benchmark corpora.
2. Do not create separate sandboxes per CodeQL unit.
3. Do not make CodeQL a mandatory sandbox validation tier.
4. Do not infer security absence from zero CodeQL alerts.
5. Do not make the model responsible for interpreting stale CodeQL outputs.
6. Do not preserve old CodeQL artifact layout compatibility unless needed during development.
7. Do not implement `download-in-container` or `image-preinstalled` CodeQL install
   strategies in the initial refactor. The `mount-host-bundle` strategy with the
   platform guard is sufficient for same-platform host/container scenarios.
8. Do not update `tests/test_mock_llm_parity.py` (its scope does not include Phase 1
   subphase simulation).

## 23. Future: targeted sandbox-recipe repair

*This section describes a design reserved for a follow-up branch. The initial
refactor deliberately does not ship this repair loop. It is included here so
the design is not lost.*

If post-merge testing shows that the deterministic runner still produces too
many `extraction-failed` or `analysis-failed` results from recipe/build issues,
the following narrow repair flow may be introduced:

1. **Trigger**: after Phase 1 orchestrator, `health.classification in
   {extraction-failed, analysis-failed}` **and** at least one analysis unit
   has `health.reason` referencing a recipe problem (e.g. "build target X
   missing", "workdir not absolute", "service not running").

2. **Scope**: a single sub-phase session (`phase_id: 1-recipe-repair`) that
   may rewrite **only** `sandbox-recipe.yml`. No changes to `codeql-plan.yml`,
   `sandbox-plan.md`, or helper scripts are permitted. The prompt is a fresh
   `prompts/phase-1-recipe-repair.md` (small, target-agnostic, no security
   content from the source tree).

3. **Retry budget**: `CODECOME_RECIPE_REPAIR_RETRIES` env var (default 1).
   After budget exhaustion, classify the unit as `recipe-soft-failed` and
   continue with explicit warnings.

4. **Re-run**: only re-run CodeQL for affected `(analysis_unit, language)`
   pairs, not the entire matrix.

5. **Agent**: uses the recon agent. The harness gates it behind the new subphase
   label `1-recipe-repair` so it shows up distinctly in `runs/`.

6. **Acceptance**: at least one previously-failing unit transitions to
   `health.usable == true` in the next run, and no previously-usable units
   regress.

7. **Off by default**: this section stays in the plan as a reference. The
   implementation is not part of commits 1–8.
