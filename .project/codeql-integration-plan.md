# CodeQL Integration Plan

Status: WIP planning document  
Branch: `wip/codeql-integration-plan`  
Scope: planning + phased implementation (install, config, pack resolver, runner, SARIF normalization).

## Goals

Integrate CodeQL into CodeCome as a first-class static-analysis capability used by the normal workflow, not as a manual side tool.

The integration should:

- run automatically during Phase 1 unless explicitly disabled;
- run after the model has produced an initial target/build/language profile;
- enrich `itemdb/notes/file-risk-index.yml` and related reconnaissance notes;
- feed Phase 2 candidate hypothesis generation;
- inject per-file CodeQL context into `make sweep`;
- support official, GitHub Security Lab, Trail of Bits, coding standards, and local CodeCome query packs;
- keep the implementation simple and maintainable;
- avoid over-engineering such as external phase-definition YAMLs or a generic workflow engine.

## Non-goals

- Do not make CodeQL a replacement for model reasoning, counter-analysis, or validation.
- Do not confirm findings solely because CodeQL reported an alert.
- Do not require CodeQL for every target or make failures fatal by default.
- Do not introduce a `config/` directory just for CodeQL.
- Do not add declarative YAML phase orchestration.
- Do not keep the old raw `opencode run` bypass inside official phase targets.

## Key design decisions

### 1. Use `templates/codeql-packs.yml`

Use a small, easy-to-maintain catalog at:

```text
./templates/codeql-packs.yml
```

This avoids adding a new `config/` directory and keeps the pack mapping close to other CodeCome templates/schemas.

The catalog should be a simple mapping from CodeQL language id to pack profile names and package references.

### 2. Use `tools/codeql.py` as the dedicated CodeQL CLI

Prefer:

```bash
tools/codeql.py install
tools/codeql.py check
tools/codeql.py run --plan itemdb/notes/codeql-plan.yml
tools/codeql.py normalize
tools/codeql.py import-risk
tools/codeql.py create-candidates
tools/codeql.py context --file src/path/file.ext
tools/codeql.py check-artifacts
```

rather than:

```bash
tools/codecome.py codeql ...
```

Rationale:

- `tools/codecome.py` is currently a small workspace helper for `check`, `status`, and `next-id`.
- CodeQL will have enough subcommands and internal logic to deserve a focused CLI wrapper.
- The harness can call `tools/codeql.py` directly without bloating `tools/codecome.py`.
- This does not prevent a future CLI consolidation if/when `tools/codecome.py` becomes the single public entrypoint.

Implementation shape:

```text
tools/codeql.py                  # thin argparse CLI

tools/codeql/
  __init__.py
  config.py                      # env/config resolution
  install.py                     # managed CodeQL CLI install
  packs.py                       # templates/codeql-packs.yml resolver
  runner.py                      # database create/analyze orchestration
  sarif.py                       # SARIF loading/extraction helpers
  normalize.py                   # SARIF -> normalized alerts
  risk.py                        # normalized alerts -> file-risk-index enrichment
  candidates.py                  # normalized alerts -> candidate findings/briefing
  context.py                     # per-file sweep context
  artifacts.py                   # manifest/check-artifact helpers
```

### 3. `run-agent.py` remains the CodeCome harness

`run-agent.py` is not just a phase runner. It is the CodeCome harness used for phases and chat mode.

For this integration, extend the existing harness directly. Do not introduce a YAML workflow definition or a generic step engine.

Phase orchestration should be explicit Python code, for example:

```python
def run_phase_1(args: Args) -> int:
    run_gate("1")

    run_agent_step(
        phase="1a",
        label="Target Profile",
        agent="recon",
        prompt_file="prompts/phase-1a-profile.md",
    )
    run_gate("1a")

    run_codeql_phase_1()
    run_codeql_artifact_gate()

    run_agent_step(
        phase="1b",
        label="CodeQL-assisted Reconnaissance",
        agent="recon",
        prompt_file="prompts/phase-1b-codeql-recon.md",
    )
    run_gate("1b")

    run_agent_step(
        phase="1c",
        label="Sandbox Bootstrap",
        agent="recon",
        prompt_file="prompts/phase-1c-sandbox.md",
    )
    run_gate("1c")

    return 0
```

Chat mode should continue to use the existing chat path and should not be forced into phase semantics.

### 4. Remove `CODECOME_USE_WRAPPER`

Remove the raw `opencode run` bypass from official phase targets immediately.

Official phases must always pass through the CodeCome harness because the harness is now responsible for:

- subphase orchestration;
- CodeQL execution;
- deterministic gates;
- candidate briefing/precreation;
- prompt enrichment;
- run logs and artifacts;
- future deterministic tooling.

If a raw debug path is useful, add an explicit non-workflow target such as:

```bash
make opencode-raw AGENT=auditor PROMPT_FILE=prompts/foo.md
```

but do not keep raw mode as an alternative implementation of `make phase-*`.

## Updated Phase 1 flow

Use clear subphase names:

```text
Phase 1a — Target profile
Phase 1b — CodeQL-assisted reconnaissance
Phase 1c — Sandbox bootstrap
```

CodeQL runs between Phase 1a and Phase 1b.

```text
make phase-1
  -> tools/run-agent.py --phase 1

     1. gate-check phase 1

     2. model: Phase 1a target profile
        outputs:
          itemdb/notes/target-profile.md
          itemdb/notes/build-model.md
          itemdb/notes/codeql-plan.yml

     3. gate-check phase 1a
        verifies:
          - required 1a outputs exist
          - codeql-plan.yml is valid YAML
          - codeql-plan.yml has the required fields
          - no accidental findings were created

     4. deterministic CodeQL step
        command:
          tools/codeql.py run --plan itemdb/notes/codeql-plan.yml
        outputs:
          itemdb/codeql/run-manifest.yml
          itemdb/codeql/selected-query-packs.yml
          itemdb/codeql/sarif/*.sarif
          itemdb/codeql/normalized/alerts.yml
          itemdb/codeql/normalized/file-signals.yml
          itemdb/codeql/codeql-summary.md

     5. CodeQL artifact gate
        verifies:
          - skipped/soft-failed/running outcome is recorded clearly
          - normalized artifacts exist when analysis succeeded
          - run-manifest.yml exists even on skip/failure

     6. model: Phase 1b CodeQL-assisted reconnaissance
        reads:
          - 1a notes
          - CodeQL artifacts
        outputs:
          itemdb/notes/attack-surface.md
          itemdb/notes/execution-model.md
          itemdb/notes/trust-boundaries.md
          itemdb/notes/data-flow.md
          itemdb/notes/validation-model.md
          itemdb/notes/interesting-files.md
          itemdb/notes/file-risk-index.yml
          itemdb/notes/security-assumptions.md

     7. gate-check phase 1b
        verifies:
          - required recon notes exist
          - file-risk-index.yml is valid
          - scores are 1..5
          - paths are workspace-relative and under src/
          - no template placeholder entries remain
          - no accidental findings were created

     8. model: Phase 1c sandbox bootstrap
        outputs:
          sandbox/
          itemdb/notes/sandbox-plan.md

     9. gate-check phase 1c
        verifies:
          - sandbox status/provenance
          - sandbox validation result
          - final frontmatter/checks
```

## Phase 1a prompt

Create:

```text
prompts/phase-1a-profile.md
```

Responsibilities:

- broad source tree mapping;
- language/framework detection;
- build model detection;
- primary/secondary target identification;
- preliminary attack-surface hints;
- generate `itemdb/notes/codeql-plan.yml`;
- do not create vulnerability findings;
- do not bootstrap sandbox;
- do not run CodeQL manually.

Required outputs:

```text
itemdb/notes/target-profile.md
itemdb/notes/build-model.md
itemdb/notes/codeql-plan.yml
```

## Phase 1b prompt

Create:

```text
prompts/phase-1b-codeql-recon.md
```

Responsibilities:

- read the Phase 1a outputs;
- read CodeQL artifacts if present;
- treat CodeQL results as reconnaissance evidence, not proof of vulnerability;
- complete the Phase 1 reconnaissance notes;
- enrich `file-risk-index.yml` with CodeQL file signals;
- prepare Phase 2 and sweep focus.

Required outputs:

```text
itemdb/notes/attack-surface.md
itemdb/notes/execution-model.md
itemdb/notes/trust-boundaries.md
itemdb/notes/data-flow.md
itemdb/notes/validation-model.md
itemdb/notes/interesting-files.md
itemdb/notes/file-risk-index.yml
itemdb/notes/security-assumptions.md
```

## Phase 1c prompt

Create:

```text
prompts/phase-1c-sandbox.md
```

This should contain the sandbox bootstrap portion currently embedded in `prompts/phase-1-recon.md`.

Responsibilities:

- inspect current sandbox state;
- select/apply/adapt a sandbox template;
- author missing helper scripts;
- run sandbox validation;
- write `itemdb/notes/sandbox-plan.md`;
- leave `sandbox/` ready for Phase 2/4/5 where possible.

## `codeql-plan.yml` template

Add:

```text
templates/codeql-plan.yml
```

Example:

```yaml
schema_version: 1
generated_by: "phase-1a-profile"

source_path: "./src"
recommended: true

languages:
  - id: "python"
    confidence: "HIGH"
    build_mode: "none"
    build_command: null
    packs:
      - "official"
      - "github-security-lab"

  - id: "javascript-typescript"
    confidence: "MEDIUM"
    build_mode: "none"
    build_command: null
    packs:
      - "official"

exclude:
  - "src/**/tests/**"
  - "src/**/fixtures/**"
  - "src/**/vendor/**"
  - "src/**/node_modules/**"

notes:
  - "Primary target appears to be a Python API service."
```

C/C++ example:

```yaml
schema_version: 1
generated_by: "phase-1a-profile"

source_path: "./src"
recommended: true

languages:
  - id: "c-cpp"
    confidence: "HIGH"
    build_mode: "manual"
    build_command: "make -C src"
    packs:
      - "official"
      - "github-security-lab"
      - "trailofbits"
      - "coding-standards"

exclude:
  - "src/**/tests/**"
  - "src/**/vendor/**"
```

Allowed pack profile names:

```text
official
github-security-lab
trailofbits
coding-standards
local
```

The model chooses profiles, not exact package names. The harness resolves profiles via `templates/codeql-packs.yml`.

## `templates/codeql-packs.yml`

Add:

```text
templates/codeql-packs.yml
```

Keep it intentionally simple:

```yaml
schema_version: 1

packs:
  python:
    official:
      - "codeql/python-queries"
    github-security-lab:
      - "githubsecuritylab/codeql-python-queries"
    local:
      - "./queries/codeql/python"

  javascript-typescript:
    official:
      - "codeql/javascript-queries"
    github-security-lab:
      - "githubsecuritylab/codeql-javascript-queries"
    local:
      - "./queries/codeql/javascript"

  c-cpp:
    official:
      - "codeql/cpp-queries"
    github-security-lab:
      - "githubsecuritylab/codeql-cpp-queries"
    trailofbits:
      - "trailofbits/cpp-queries"
    coding-standards:
      - "codeql/coding-standards-cpp"
    local:
      - "./queries/codeql/cpp"

  go:
    official:
      - "codeql/go-queries"
    github-security-lab:
      - "githubsecuritylab/codeql-go-queries"
    trailofbits:
      - "trailofbits/go-queries"
    local:
      - "./queries/codeql/go"

  csharp:
    official:
      - "codeql/csharp-queries"
    github-security-lab:
      - "githubsecuritylab/codeql-csharp-queries"
    local:
      - "./queries/codeql/csharp"

  java-kotlin:
    official:
      - "codeql/java-queries"
    github-security-lab:
      - "githubsecuritylab/codeql-java-queries"
    local:
      - "./queries/codeql/java"

candidate_policy:
  official:
    allow_precreate: true
  github-security-lab:
    allow_precreate: true
  trailofbits:
    allow_precreate: true
  coding-standards:
    allow_precreate: false
  local:
    allow_precreate: true
```

Notes:

- Some package names may require verification during implementation with `codeql pack download` / `codeql resolve packs`.
- Missing/unavailable packs should be recorded as warnings in `run-manifest.yml`, not crash the phase under soft fail policy.
- `coding-standards` packs should enrich risk and sweep context by default, but should not precreate findings unless explicitly allowed later.

## CodeQL installation and `make init`

Rename `make venv` to `make init`, keeping `venv` as an alias.

```makefile
.PHONY: init venv venv-check

init:
	@python3 -m venv .venv
	@$(PYTHON) -m pip install --upgrade pip
	@$(PYTHON) -m pip install --no-input -r requirements.txt
	@if [ "$$CODEQL" != "0" ] && [ "$$CODEQL_SKIP_INSTALL" != "1" ]; then \
		$(PYTHON) tools/codeql.py install; \
	fi

venv: init
```

Install location:

```text
.tools/codeql/<version>/
.tools/codeql/current -> <version>
.cache/codeql/
```

Update `.gitignore`:

```text
.tools/
.cache/
```

Environment controls:

```bash
CODEQL=0 make init
CODEQL_SKIP_INSTALL=1 make init
CODEQL_VERSION=<version> make init
CODEQL_FORCE_INSTALL=1 make init
```

## CodeQL runtime controls

Supported escape hatches:

```bash
CODEQL=0 make phase-1
CODEQL_SKIP=1 make phase-1
CODEQL_FAIL_POLICY=hard make phase-1
CODEQL_PACKS=0 make phase-1
CODEQL_COMMUNITY_PACKS=0 make phase-1
CODEQL_CANDIDATES=off make phase-2
CODEQL_CANDIDATES=briefing make phase-2
CODEQL_CANDIDATES=precreate make phase-2
```

Resolution priority:

```text
environment variables > codecome.yml > defaults
```

Default policy:

```text
CodeQL enabled: yes
Failure policy: soft
Candidate mode: briefing
Community packs: enabled
```

## `codecome.yml` additions

Keep this compact; do not embed the full pack map in `codecome.yml`.

```yaml
static_analysis:
  codeql:
    enabled: true
    fail_policy: "soft"
    pack_catalog: "./templates/codeql-packs.yml"

    install:
      managed: true
      version: "latest"
      path: ".tools/codeql/current/codeql"

    output_dir: "./itemdb/codeql"
    database_dir: "./itemdb/codeql/databases"
    cache_dir: "./.cache/codeql"

    phase_1:
      enabled: true

    phase_2:
      enabled: true
      candidate_mode: "briefing"
      max_candidates: 10

    sweep:
      enabled: true
      inject_context: true
```

## CodeQL artifacts

Use this layout:

```text
itemdb/codeql/
  run-manifest.yml
  selected-query-packs.yml
  codeql-summary.md

  databases/
    python/
    c-cpp/

  sarif/
    python.official.sarif
    python.github-security-lab.sarif
    cpp.trailofbits.sarif
    cpp.coding-standards.sarif

  normalized/
    alerts.yml
    file-signals.yml
    candidate-findings.yml
```

`run-manifest.yml` should always exist after a CodeQL step, even when CodeQL was skipped or soft-failed.

Example:

```yaml
schema_version: 1
phase: "phase-1"
status: "completed" # completed | skipped | soft-failed | failed
codeql_enabled: true
codeql_version: "2.x.y"
started_at: "YYYY-MM-DDTHH:MM:SSZ"
finished_at: "YYYY-MM-DDTHH:MM:SSZ"
plan_file: "itemdb/notes/codeql-plan.yml"
pack_catalog: "templates/codeql-packs.yml"
languages:
  - "python"
warnings: []
failures: []
```

## SARIF normalization

Do not expose raw SARIF directly to model prompts. Normalize it first.

`itemdb/codeql/normalized/alerts.yml`:

```yaml
schema_version: 1
generated_by: "codeql-normalize"
codeql_version: "2.x.y"
target: "codecome-target"

alerts:
  - id: "CQ-0001"
    fingerprint: "..."
    language: "python"
    pack_profile: "github-security-lab"
    pack: "githubsecuritylab/codeql-python-queries"
    rule_id: "py/path-injection"
    rule_name: "Uncontrolled data used in path expression"
    severity: "warning"
    security_severity: "7.5"
    precision: "high"
    kind: "path-problem"
    primary_location:
      path: "src/api/upload.py"
      start_line: 88
      end_line: 88
    flow:
      source:
        path: "src/api/routes.py"
        line: 42
        label: "request file name"
      sink:
        path: "src/api/upload.py"
        line: 88
        label: "filesystem write"
      steps:
        - path: "src/api/routes.py"
          line: 42
          message: "..."
        - path: "src/api/upload.py"
          line: 88
          message: "..."
    mapped:
      category: "Path traversal"
      suggested_validation_methods:
        - "static_proof"
        - "http_exploit"
```

`file-signals.yml`:

```yaml
schema_version: 1
files:
  - path: "src/api/upload.py"
    codeql_score_boost: 2
    suggested_sweep: true
    alerts:
      total: 3
      path_problems: 1
      high_precision: 1
    rules:
      - "py/path-injection"
```

## File risk enrichment

`tools/codeql.py import-risk` should enrich `itemdb/notes/file-risk-index.yml`.

Rules:

- Preserve existing entries and model-authored reasons.
- Do not duplicate file entries.
- Cap scores at 5.
- Explain every score boost in `reasons`.
- Add an optional `external_signals.codeql` block.

Example:

```yaml
- path: "src/api/upload.py"
  score: 5
  confidence: "HIGH"
  target_area: "file upload API"
  reasons:
    - "Handles attacker-controlled multipart upload data."
    - "CodeQL signal: py/path-injection reports user-controlled path reaching filesystem sink."
  sources:
    - "HTTP multipart filename"
  sinks:
    - "filesystem write"
  trust_boundaries:
    - "remote client -> server filesystem"
  suggested_vulnerability_classes:
    - "Path traversal"
    - "File upload vulnerabilities"
  suggested_skills:
    - "web-security"
  suggested_validation_methods:
    - "static_proof"
    - "http_exploit"
  external_signals:
    codeql:
      alerts: 3
      path_problems: 1
      highest_precision: "high"
      rules:
        - "py/path-injection"
```

## Phase 2 candidate handling

Before the Phase 2 model invocation, the harness should call:

```bash
tools/codeql.py create-candidates
```

Inputs:

```text
itemdb/codeql/normalized/alerts.yml
itemdb/codeql/normalized/file-signals.yml
itemdb/notes/file-risk-index.yml
itemdb/findings/**/CC-*.md
```

Outputs:

```text
itemdb/codeql/normalized/candidate-findings.yml
itemdb/notes/codeql-candidate-findings.md
```

Candidate modes:

```text
off       -> do nothing
briefing  -> write candidate briefing only
precreate -> create filtered PENDING findings before model runs
```

Default: `briefing`.

Precreate only when:

- candidate is not under ignored/test/vendor/generated paths;
- a CodeCome category can be inferred;
- affected files are concrete;
- there is a plausible sink or security decision;
- the candidate is from an allowed pack profile;
- max candidate limit is not exceeded.

Phase 2 prompt must require candidate disposition.

Add to `prompts/phase-2-audit.md`:

```md
## CodeQL candidate handling

If `itemdb/notes/codeql-candidate-findings.md` or
`itemdb/codeql/normalized/candidate-findings.yml` exists, you must
account for each candidate.

For each candidate, choose one:

- create or complete a PENDING finding,
- merge it into an existing finding,
- defer it to `make sweep` with a concrete file target,
- reject it as non-security-relevant or out of scope.

Write the decision table to:

    itemdb/notes/codeql-candidate-disposition.md
```

Add a Phase 2 gate:

- if candidate findings exist, `itemdb/notes/codeql-candidate-disposition.md` must exist;
- each candidate id should appear in the disposition table;
- created findings must pass frontmatter validation.

## Sweep context injection

`tools/run-sweep.py` should request per-file CodeQL context before writing the temporary sweep prompt.

Command:

```bash
tools/codeql.py context --file src/path/file.ext
```

If context exists, inject a section like:

```md
## CodeQL context for this file

Relevant alerts:

- `CQ-0001` / `py/path-injection`
  - pack: `githubsecuritylab/codeql-python-queries`
  - source: `src/api/routes.py:42`
  - sink: `src/api/upload.py:88`
  - summary: user-controlled path reaches filesystem write

Treat this as a static-analysis hint, not proof. Verify attacker control,
reachability, sanitizers, authorization, and impact before creating a finding.
```

Add `SWEEP_ARGS` support to the Makefile:

```makefile
sweep: venv-check
	@if [ -n "$(FILE)" ]; then \
		$(PYTHON) tools/run-sweep.py --file "$(FILE)" $(SWEEP_ARGS); \
	else \
		$(PYTHON) tools/run-sweep.py $(SWEEP_ARGS); \
	fi
```

## Makefile changes

### Remove raw wrapper mode

Remove all `CODECOME_USE_WRAPPER` branches from phase targets.

Phase targets become:

```makefile
phase-1: venv-check
	@$(PYTHON) tools/run-agent.py --phase 1

phase-2: venv-check
	@$(PYTHON) tools/run-agent.py --phase 2

phase-3: venv-check
	@$(PYTHON) tools/run-agent.py --phase 3

phase-4: venv-check
	@test -n "$(FINDING)" || (...)
	@$(PYTHON) tools/run-agent.py --phase 4 --finding "$(FINDING)"

phase-5: venv-check
	@test -n "$(FINDING)" || (...)
	@$(PYTHON) tools/run-agent.py --phase 5 --finding "$(FINDING)"

phase-6: venv-check
	@$(PYTHON) tools/run-agent.py --phase 6
```

### Optional raw debug target

```makefile
opencode-raw:
	@test -n "$(AGENT)" || (echo "AGENT is required" && exit 1)
	@test -n "$(PROMPT_FILE)" || (echo "PROMPT_FILE is required" && exit 1)
	@opencode run --agent "$(AGENT)" "$$(cat "$(PROMPT_FILE)")"
```

## Gates

Extend `tools/gate-check.py` with subphase gates.

### `gate-check.py 1a`

Checks:

- `itemdb/notes/target-profile.md` exists;
- `itemdb/notes/build-model.md` exists;
- `itemdb/notes/codeql-plan.yml` exists;
- `codeql-plan.yml` is valid YAML;
- if `recommended: true`, at least one language entry exists;
- each language entry has `id`, `confidence`, `build_mode`, `packs`;
- no new findings were created during 1a.

### `gate-check.py 1b`

Checks:

- all required recon notes exist;
- `itemdb/notes/file-risk-index.yml` exists;
- YAML is valid;
- `schema_version` is present;
- `files` is a list;
- all file paths are workspace-relative;
- all scores are integers 1..5;
- template placeholder entry is gone;
- no new findings were created during 1b.

### `gate-check.py 1c`

Checks:

- `itemdb/notes/sandbox-plan.md` exists;
- sandbox status/provenance exists or clear halt protocol exists;
- sandbox validation was attempted or static-only/nested-virt justification exists;
- frontmatter check passes.

### CodeQL artifact gate

Can live in `tools/codeql.py check-artifacts` rather than `gate-check.py`.

Checks:

- `run-manifest.yml` exists after a CodeQL step;
- manifest status is one of `completed`, `skipped`, `soft-failed`, `failed`;
- if completed, normalized outputs exist;
- if skipped/soft-failed, reason is recorded;
- no raw exception trace is left as the only diagnostic.

## Candidate finding frontmatter

If precreate mode is used, generated findings should include the normal finding frontmatter plus optional origin/static-analysis metadata if the current frontmatter checker allows it.

Preferred fields if allowed:

```yaml
origin:
  - "codeql"

static_analysis:
  codeql:
    alerts:
      - "CQ-0001"
    rules:
      - "py/path-injection"
    packs:
      - "githubsecuritylab/codeql-python-queries"
    sarif:
      - "itemdb/codeql/sarif/python.github-security-lab.sarif"
```

If the frontmatter checker rejects extra fields, place this information in the finding body under:

```md
# Static-analysis evidence
```

Do not weaken the frontmatter gate to accept arbitrary fields without a deliberate schema update.

## Testing plan

Add fixtures:

```text
tests/fixtures/codeql/
  sarif-path-problem.json
  sarif-local-problem.json
  sarif-multiple-packs.json
  file-risk-index.base.yml
  codeql-plan.python.yml
  codeql-plan.cpp.yml
  codeql-packs.yml
```

Add tests:

```text
tests/test_codeql_packs.py
tests/test_codeql_normalize.py
tests/test_codeql_risk.py
tests/test_codeql_candidates.py
tests/test_codeql_context.py
tests/test_phase1_subphase_gates.py
```

Required cases:

- pack catalog resolves requested profiles by language;
- unavailable pack profile is reported clearly;
- SARIF path-problem extracts source/sink/steps;
- local SARIF problem without flow is normalized without crashing;
- file risk enrichment preserves existing entries;
- file risk enrichment caps score at 5;
- ignored paths do not create candidates;
- coding-standards alerts enrich risk but do not precreate candidates by default;
- context lookup returns alerts where file is primary or related location;
- Phase 1a gate rejects missing/invalid `codeql-plan.yml`;
- Phase 1b gate rejects placeholder file-risk-index entries.

## Implementation PR sequence

### PR 1 — Harness simplification and init rename

- Remove `CODECOME_USE_WRAPPER` branches from Makefile.
- Make all `phase-*` targets call `tools/run-agent.py`.
- Add optional `opencode-raw` debug target.
- Rename `make venv` to `make init`.
- Keep `venv: init` alias.
- Update help text.

### PR 2 — Split Phase 1 into 1a/1b/1c

- Add prompts:
  - `prompts/phase-1a-profile.md`
  - `prompts/phase-1b-codeql-recon.md`
  - `prompts/phase-1c-sandbox.md`
- Add `templates/codeql-plan.yml`.
- Extend `run-agent.py` with explicit Phase 1 orchestration.
- Add `gate-check.py 1a`, `1b`, `1c`.

### PR 3 — CodeQL CLI and install/check

- Add `tools/codeql.py`.
- Add `tools/codeql/` modules.
- Implement `install` and `check`.
- Install CodeQL into `.tools/codeql/`.
- Add `.tools/` and `.cache/` to `.gitignore`.
- Respect `CODEQL=0` and `CODEQL_SKIP_INSTALL=1`.

### PR 4 — Pack catalog and resolver

- Add `templates/codeql-packs.yml`.
- Implement pack resolver.
- Support profiles:
  - `official`
  - `github-security-lab`
  - `trailofbits`
  - `coding-standards`
  - `local`
- Write `selected-query-packs.yml`.
- Validate pack catalog schema.

### PR 5 — CodeQL run and SARIF normalization

- Implement `tools/codeql.py run`.
- Read `itemdb/notes/codeql-plan.yml`.
- Create databases per language.
- Analyze with selected packs.
- Normalize SARIF.
- Write:
  - `run-manifest.yml`
  - `alerts.yml`
  - `file-signals.yml`
  - `codeql-summary.md`
- Implement soft/hard fail policy.

### PR 6 — Phase 1 CodeQL integration

- Call CodeQL between Phase 1a and Phase 1b.
- Add CodeQL artifact gate.
- Ensure Phase 1b prompt reads CodeQL artifacts.
- Enrich file-risk-index from CodeQL signals.

### PR 7 — Phase 2 candidates

- Implement `tools/codeql.py create-candidates`.
- Generate `candidate-findings.yml`.
- Generate `codeql-candidate-findings.md`.
- Support `off`, `briefing`, and `precreate` modes.
- Update Phase 2 prompt with candidate disposition requirement.
- Add gate for candidate disposition.

### PR 8 — Sweep context

- Implement `tools/codeql.py context --file`.
- Inject context into `tools/run-sweep.py` prompts.
- Add `SWEEP_ARGS` to Makefile.
- Update sweep prompt with CodeQL context rules.

## Review checklist before implementation

- Confirm `tools/codeql.py` vs `tools/codecome.py codeql` decision.
- Confirm exact CodeQL install source/version policy.
- Verify package names in `templates/codeql-packs.yml`.
- Confirm default `CODEQL_CANDIDATES` mode: `briefing` vs `precreate`.
- Confirm whether finding frontmatter schema should accept `origin` / `static_analysis`.
- Confirm whether `coding-standards` should ever precreate findings by default.
- Confirm whether Phase 1c sandbox prompt should be copied from current `phase-1-recon.md` or rewritten tighter.
