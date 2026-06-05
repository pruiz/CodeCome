# CodeQL + Sandbox Recipe Refactor Plan

Status: **WIP plan for review**

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

## 19. Implementation sequence

Recommended sequence for one WIP branch:

1. Rename/reorder Phase 1 prompts and orchestration.
2. Add `sandbox-recipe.yml` template/schema and validation helper.
3. Update sandbox prompt/skill to require recipe generation.
4. Update completion/gates/artifact checks for new Phase 1 order.
5. Update `codeql-plan.yml` schema to v2.
6. Add effective CodeQL plan resolver combining CodeQL plan + sandbox recipe.
7. Add run directory layout.
8. Add CodeQL health model.
9. Refactor runner/pipeline/artifacts around health and run directories.
10. Wire CodeQL after sandbox in Phase 1.
11. Update recon prompt to consume health/signals correctly.
12. Update docs/README/tests.
13. Run full test suite and fix regressions.
14. Test manually on at least:
    - Python/no-build target;
    - C/C++ target with Docker build;
    - multi-component target with one aggregate build;
    - target with CodeQL disabled.

## 20. Open implementation questions

1. Which CodeQL-in-Docker install strategy should be implemented first?
   - Recommended first: `mount-host-bundle`.
2. Do we want symlinks such as `itemdb/codeql/current` or plain marker files such as `current-run.txt`?
   - Recommended first: marker file for portability.
3. Should schema v1 `codeql-plan.yml` be supported during migration?
   - Since compatibility is not required, prefer failing with a clear upgrade error.
4. Should CodeQL repair be removed initially?
   - Recommended: remove or disable it initially, then reintroduce after deterministic execution/health is solid.
5. Should sandbox recipe validation live in `tools/sandbox-bootstrap.py` or a new module under `tools/sandbox/`?
   - Recommended: add a reusable module, expose through existing CLI.

## 21. Non-goals

1. Do not special-case Juliet or other benchmark corpora.
2. Do not create separate sandboxes per CodeQL unit.
3. Do not make CodeQL a mandatory sandbox validation tier.
4. Do not infer security absence from zero CodeQL alerts.
5. Do not make the model responsible for interpreting stale CodeQL outputs.
6. Do not preserve old CodeQL artifact layout compatibility unless needed during development.
