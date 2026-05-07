# Plan: Auto-generated Sandbox Bootstrap (Phase 1b)

## Status

v1.0 — new feature. Introduces a Phase 1b sub-stage in the recon
workflow and a curated set of sandbox baselines under
`templates/sandboxes/`.

## Goal

Make CodeCome auto-create a usable validation sandbox under `sandbox/`
based on the target placed under `src/`. The agent picks one of the
curated examples in `templates/sandboxes/<id>/`, adapts it to the
specific target, validates it, and either hands off to Phase 2 or halts
with a clear, user-actionable explanation.

## Non-goals

- Creating sandboxes outside `sandbox/`.
- Replacing the user's already-working `sandbox/` content silently.
- Building a full template engine. Markers are plain `__VARNAME__`
  strings; the agent does the creative substitution work.
- Provisioning real cloud infrastructure.
- Running validation outside the local host.

## Decisions (locked)

| # | Decision |
|---|---|
| 1 | Examples live under `templates/sandboxes/<id>/`. |
| 2 | If `sandbox/` already has content, validate it. If validation passes, move on. If not, halt with a clear message. Never overwrite silently. |
| 3 | Multi-stack handling honors existing `src/` artifacts (Dockerfile, compose, READMEs, runbooks, docs) when usable. Build-time-only stacks are excluded from the runtime sandbox. |
| 4 | Bootstrap runs as Phase 1b, immediately after the recon notes are written, in the same phase invocation. Single phase, two sub-stages. |
| 5 | Soft gate before Phase 2. Override via `CODECOME_ALLOW_NO_SANDBOX=1`. |
| 6 | `static-only` and `nested-virt` are allowed escape hatches. Both require justification in `sandbox-plan.md`. |
| 7 | All proposed examples ship in v1. |
| 8 | A CLI exists at `tools/sandbox-bootstrap.py`. Agent uses it; user can also invoke it directly. |
| 9 | `sandbox/.backup-*/` kept permanently. User prunes manually. Gitignored. |
| 10 | No template engine. Marker convention is `__VARNAME__`. |
| 11 | `apply` and `regenerate` support `--dry-run`. |
| 12 | Validation prefers `sandbox/scripts/*` when present, otherwise falls back to direct `docker` / `docker compose`. |
| 13 | Agent may attempt automatic remediations. Default retry budget is 3. Configurable via `CODECOME_BOOTSTRAP_MAX_RETRIES` env var and `--max-retries` flag. When exhausted, halt with full explanation. |
| 14 | Marker substitution: CLI accepts `--var KEY=VAL`, agent retains creative control to post-edit. |
| 15 | `detect` reads `itemdb/notes/*.md` if present. Falls back to scanning the top two levels of `src/`. |
| 16 | Everything under `templates/sandboxes/**` tracked in git. |

## Naming convention rename

`static_only` → `static-only` so it matches `nested-virt`. Mirrors the
earlier `NEEDS_VALIDATION` → `PENDING` migration. No active code uses
`static_only` yet, so this is a forward-only convention.

## Top-level deliverables

1. New tree: `templates/sandboxes/<id>/` with v1 set of baselines.
2. New tool: `tools/sandbox-bootstrap.py`.
3. New skill: `.opencode/skills/sandbox-bootstrap/SKILL.md`.
4. New required Phase 1 output: `itemdb/notes/sandbox-plan.md`.
5. New provenance file: `sandbox/CODECOME-GENERATED.md` (only when
   bootstrap actually generated content).
6. New Make targets: `sandbox-detect`, `sandbox-bootstrap`,
   `sandbox-validate`, `sandbox-regenerate`, `sandbox-status`.
7. Phase 2 gate update: soft block on missing/failed sandbox.
8. Doc updates: `sandbox/README.md`, `README.md`, `docs/workflow.md`.

## Workflow integration

Phase 1 becomes:

- **1a** — Source recon. Existing flow. Produces `itemdb/notes/*.md`.
- **1b** — Sandbox planning, bootstrap, validation. Produces
  `itemdb/notes/sandbox-plan.md` and either generates or validates
  `sandbox/`.

Phase 2 gate:

- Reads `sandbox/CODECOME-GENERATED.md` (if any) and the latest
  validation status.
- Hard rules:
  - If sandbox is missing entirely → block (override available).
  - If sandbox exists but last validation failed → block (override
    available).
  - If `validation_model: static-only` is declared with justification →
    pass.
  - If `validation_model: nested-virt` is declared and validation
    passed → pass.
- Override env var: `CODECOME_ALLOW_NO_SANDBOX=1`. Logs a warning even
  on override.

## File-level changes

### New: `templates/sandboxes/`

Initial example set (v1):

- `c-cpp/` — current default reused as an example. Includes gdb,
  valgrind, ASan tooling.
- `python/` — multi-version-friendly Python image.
- `node/` — Node + npm/yarn/pnpm awareness.
- `dotnet/` — .NET SDK image.
- `go/` — Go toolchain.
- `java-maven/` — JDK + Maven.
- `rust/` — rustup + cargo.
- `php/` — PHP CLI + composer.
- `ruby/` — Ruby + bundler.
- `web-static/` — minimal Nginx-based serving for static analysis.
- `iac-terraform/` — Terraform CLI for IaC review (no provider auth).
- `multi-service-compose/` — base for combining services. Documents
  the merge protocol for honoring `src/` compose files.
- `nested-virt/` — Docker host running QEMU for firmware/binary-only
  edge cases. Justification mandatory.
- `generic/` — minimal Debian. Last-resort fallback.

Each example contains:

```
templates/sandboxes/<id>/
├── manifest.yml
├── Dockerfile          (when applicable)
├── docker-compose.yml  (when applicable)
├── scripts/
│   ├── build-target.sh
│   └── test-target.sh
├── README.md
└── notes.md
```

Manifest schema:

```yaml
id: "python"
display_name: "Python project"
applies_when:
  languages: ["python"]
  manifests: ["pyproject.toml", "requirements.txt", "setup.py"]
required_tools: ["python3", "pip"]
default_ports: []
build_command: "pip install -r requirements.txt"
test_command: "pytest"
notes_md: "notes.md"
caveats:
  - "Does not include database services."
  - "Add Postgres/Redis via multi-service-compose if needed."
template_vars:
  - PYTHON_VERSION
  - APP_PORT
```

`applies_when` is **not** authoritative. The agent makes the final
decision. The CLI uses it for ranking only.

### New: `tools/sandbox-bootstrap.py`

Subcommands:

- `list` — list available examples + `applies_when` summary.
- `inspect <id>` — print manifest + previews of `Dockerfile`,
  `docker-compose.yml`, scripts.
- `detect` — scan, return ranked candidates as JSON. Default behavior:
  read `itemdb/notes/*.md` if present, else walk `src/` to depth 2.
- `apply <id> [--var KEY=VAL ...] [--dry-run]` — copy example into
  `sandbox/`, do marker substitution for any `--var` provided, write
  `sandbox/CODECOME-GENERATED.md`, back up displaced files into
  `sandbox/.backup-<ts>/`. Idempotent: refuses to overwrite a
  user-customized `sandbox/` unless `--force` is set.
- `validate [--scripts-only|--docker-only]` — run validation tiers.
  Script-first by default (per decision 12). Outputs JSON result with
  per-tier exit codes and last-50-lines stderr.
- `regenerate [--dry-run]` — re-apply current example, backing up
  previous content. Reads provenance from
  `sandbox/CODECOME-GENERATED.md`.
- `status [--gate]` — read provenance and validation status. With
  `--gate`, exits non-zero if Phase 2 should be blocked. Honors
  `CODECOME_ALLOW_NO_SANDBOX=1`.

Global flags:
- `--format text|json` (default text for humans, json when stdout is
  not a TTY).
- `--max-retries N` and env `CODECOME_BOOTSTRAP_MAX_RETRIES` (default
  3) — only consumed by remediation loops driven by the agent. The CLI
  itself does not retry; it surfaces failure data.

### New: `.opencode/skills/sandbox-bootstrap/SKILL.md`

Concrete decision rules for the agent:

- How to read recon notes and infer the runtime stack.
- Build-time vs runtime stack disambiguation.
- When to choose `multi-service-compose`.
- When to honor and wrap `src/Dockerfile`, `src/docker-compose.yml`,
  `src/Makefile`, `src/scripts/`, and developer documentation under
  `src/README*`, `src/docs/`, `src/INSTALL*`, `src/CONTRIBUTING*`,
  `src/RUN*`.
- When to declare `static-only` (justification template).
- When to declare `nested-virt` (justification template).
- Auto-remediation loop. Pseudocode:

  ```
  attempts = 0
  budget = max(1, max_retries)
  while attempts < budget:
      apply or regenerate
      result = validate
      if result.passed:
          done
      attempts += 1
      analyze tier failures
      if not actionable:
          break
      adjust manifest, Dockerfile, scripts, or env
  if not done:
      write halt explanation to sandbox-plan.md
      exit
  ```

- Halt criteria and `sandbox-plan.md` halt section template.
- User-question protocol when missing input is required (env var,
  secret, port, service, manual edit, etc.).

### New: `itemdb/notes/sandbox-plan.md`

Mandatory output of Phase 1b. Sections:

1. Detected stack
2. Honoring decision (what `src/` artifacts were honored, wrapped, or
   ignored, and why)
3. Chosen example(s)
4. Marker values applied
5. Validation matrix (T1 build, T2 check, T3 build-target, T4
   test-target — each: pass/fail/n-a, last command, exit code, stderr
   excerpt)
6. Open questions for the user (optional)
7. Halt notice (optional, only when bootstrap could not finish)
8. `validation_model` declaration (`docker`, `static-only`,
   `nested-virt`)
9. Remediation log (each automatic attempt with rationale)

### New: `sandbox/CODECOME-GENERATED.md`

Provenance file. Existence indicates the sandbox is bootstrap-managed
and may be regenerated. Absence indicates user-managed; bootstrap will
refuse to overwrite without `--force`.

Sections:

- Generated at: ISO timestamp
- Source example: id + path
- Marker values
- Validation history (append-only, last N entries)
- Manual-edit indicator (computed at validate time by hashing tracked
  files vs recorded baseline; "yes" lowers regenerate confidence)

### New: `sandbox/.backup-<timestamp>/`

Created automatically before any destructive operation. Permanent.
User prunes. Added to `.gitignore`.

### Updated: `.opencode/agents/recon.md`

Add `## Phase 1b: Sandbox bootstrap` section after current Phase 1a
content. Make `itemdb/notes/sandbox-plan.md` a required output. Direct
the agent to `tools/sandbox-bootstrap.py` and the new skill.

### Updated: `prompts/phase-1-recon.md`

Append the bootstrap stage instructions and the user-question
protocol.

### Updated: `Makefile`

New targets:

- `sandbox-detect` → `tools/sandbox-bootstrap.py detect`.
- `sandbox-bootstrap` → `tools/sandbox-bootstrap.py apply`.
  Requires `EXAMPLE=<id>` or driven via the agent. Standalone usage:
  `make sandbox-bootstrap EXAMPLE=python`.
- `sandbox-validate` → `tools/sandbox-bootstrap.py validate`.
- `sandbox-regenerate` → `tools/sandbox-bootstrap.py regenerate`.
- `sandbox-status` → `tools/sandbox-bootstrap.py status`.

`phase-2` gate updated:

```
phase-2: venv-check
    @$(PYTHON) tools/gate-check.py 2
    @$(PYTHON) tools/sandbox-bootstrap.py status --gate
    ...
```

Gate failure prints how to override.

### Updated: `tools/gate-check.py`

Add a sandbox readiness check helper invoked by Phase 2. Honor
`CODECOME_ALLOW_NO_SANDBOX=1`.

### Updated: `.gitignore`

Append:

```
sandbox/.backup-*
sandbox/CODECOME-GENERATED.md
```

`CODECOME-GENERATED.md` is gitignored because it contains per-run
state, not source.

The current `sandbox/Dockerfile` and `sandbox/docker-compose.yml` are
already tracked. They remain so for now — they act as a sane default
for users who do not run Phase 1b. Bootstrap will detect that case via
the missing `CODECOME-GENERATED.md` and refuse to overwrite.

### Updated: `sandbox/README.md`

Document:

- the new bootstrap workflow,
- how to run bootstrap manually,
- how to opt out (`CODECOME_ALLOW_NO_SANDBOX=1`),
- the relationship between the tracked default sandbox and bootstrap.

### Updated: `README.md` and `docs/workflow.md`

Document Phase 1b and the new make targets at the same fidelity as
existing phases.

## Validation tiers

Each tier executed in order. First failing tier causes the validation
to stop early (unless `--keep-going` is set). Result captured per tier.

| Tier | Purpose | Command |
|---|---|---|
| T1 | Image build | `sandbox/scripts/up.sh` if it builds, else `docker compose -f sandbox/docker-compose.yml build` |
| T2 | Sanity | `sandbox/scripts/check.sh` |
| T3 | Target build | `sandbox/scripts/build-target.sh` (skip if not applicable per manifest) |
| T4 | Target test | `sandbox/scripts/test-target.sh` (skip if not applicable per manifest) |

Per-tier capture:

- start time
- stop time
- exit code
- last 50 lines of combined stdout+stderr
- duration

Outcome: `passed | failed | skipped`.

Validation appends to `sandbox/CODECOME-GENERATED.md` validation
history and writes the matrix into `sandbox-plan.md`.

## Honoring existing `src/` artifacts (decision #3)

Before choosing an example, the agent and CLI inspect:

- `src/Dockerfile`
- `src/docker-compose*.yml`
- `src/Makefile`
- `src/scripts/`
- `src/README*`
- `src/CONTRIBUTING*`
- `src/INSTALL*`
- `src/RUN*`
- `src/docs/`

Honoring rules:

1. If a usable runtime definition exists in `src/`, the bootstrap
   generates a thin `sandbox/` wrapper that delegates to those files
   rather than replacing them.
2. If `src/` artifacts are partial, the agent merges them with the
   chosen example.
3. If `src/` artifacts are present but unsuitable (e.g., production
   compose with secrets), document this in `sandbox-plan.md` under
   "Honoring decision" and explain why a fresh sandbox was chosen.
4. The honoring decision is mandatory in `sandbox-plan.md` even when
   no honoring takes place ("nothing to honor").

## Failure / halt protocol (decision #6)

When the agent gives up, `sandbox-plan.md` must include:

1. **Attempts** — each remediation step with the exact commands and
   exit codes.
2. **Root cause hypothesis** — what the agent thinks is wrong.
3. **What is needed from the user** — env var, secret, port, service,
   missing dependency, source change, manual edit.
4. **Suggested next action** — concrete, copy-pasteable.
5. **Halt notice** — explicit "Phase 2 blocked until this is
   resolved" statement.
6. **Override hint** — note about `CODECOME_ALLOW_NO_SANDBOX=1` if the
   user wants to proceed anyway.

## Idempotency rules

1. `apply` refuses to write into a non-empty `sandbox/` lacking
   `CODECOME-GENERATED.md` unless `--force` is set.
2. `regenerate` requires `CODECOME-GENERATED.md` to exist and to
   reference an example. Always backs up before writing.
3. `validate` is read-only against the live sandbox; only writes
   provenance and plan updates.
4. Marker substitution is applied during `apply` and `regenerate`. The
   agent may post-edit afterward, but post-edits cause manual-edit
   indicators to flip to "yes" on the next validation.

## Edge cases

- `sandbox/` does not exist → bootstrap creates it.
- `sandbox/` exists but only `.gitkeep` → treat as empty, bootstrap
  fully.
- `sandbox/` has the current tracked default → bootstrap may apply
  with `--force`, backing up the default to `sandbox/.backup-<ts>/`.
- `sandbox/` has user-customized content without
  `CODECOME-GENERATED.md` → halt with halt protocol if validation
  fails. If validation passes, move on.
- `src/` is empty → bootstrap fails Phase 1a anyway; no behavior
  change.
- Multi-language repo → multi-service-compose example with
  build-time/runtime disambiguation per decision #3.
- Target requires hardware (GPU, USB) → `nested-virt` is not
  sufficient; agent must declare halt with user-action.
- Docker not installed → `validate` and `apply` fail with a clear
  upfront check; halt protocol triggers.

## Configuration / environment

| Var | Default | Purpose |
|---|---|---|
| `CODECOME_ALLOW_NO_SANDBOX` | unset | Soft override of the Phase 2 sandbox gate. |
| `CODECOME_BOOTSTRAP_MAX_RETRIES` | 3 | Agent remediation budget. |
| `CODECOME_BOOTSTRAP_DRY_RUN` | unset | Force `--dry-run` on `apply`/`regenerate`. |

CLI flags mirror env vars where applicable.

## Rollout (commit boundaries)

To keep diffs reviewable, ship in this order. Each step is its own
commit.

1. Skeleton: `tools/sandbox-bootstrap.py` with `list`, `inspect`,
   `status`, `detect`. `.gitignore` updates. New Make targets
   (functional for `list`/`status`/`detect` only).
2. v1 examples — group A: `generic`, `c-cpp`, `python`, `node`.
3. v1 examples — group B: `dotnet`, `go`, `java-maven`, `rust`.
4. v1 examples — group C: `php`, `ruby`, `web-static`,
   `iac-terraform`.
5. v1 examples — group D: `multi-service-compose`, `nested-virt`.
6. `apply` + `regenerate` (with `--dry-run`) + provenance writer.
7. `validate` (script-first, docker fallback) + tier capture.
8. Skill: `.opencode/skills/sandbox-bootstrap/SKILL.md`.
9. Agent + prompt updates: `.opencode/agents/recon.md`,
   `prompts/phase-1-recon.md`.
10. Phase 2 gate update + override env var.
11. Docs: `sandbox/README.md`, `README.md`, `docs/workflow.md`.
12. Convention rename: `static_only` → `static-only`.

## Verification

After each commit boundary:

- `make venv-check`
- `make check`
- `.venv/bin/python3 -m py_compile tools/sandbox-bootstrap.py`
- `make help` shows new targets.

After step 6:

- `make sandbox-bootstrap EXAMPLE=generic` against the current sample
  target produces a generated `sandbox/` with `CODECOME-GENERATED.md`.

After step 7:

- `make sandbox-validate` produces a JSON validation matrix.

After step 9:

- `make phase-1` (with the test sample) writes
  `itemdb/notes/sandbox-plan.md`.

After step 10:

- `make phase-2` blocks when sandbox is broken.
- `CODECOME_ALLOW_NO_SANDBOX=1 make phase-2` proceeds with a warning.

## Risks

- **Agent over-engineering.** Mitigation: the skill prescribes
  honoring `src/` artifacts and prefers minimal sandboxes.
- **Docker unavailable on host.** Mitigation: pre-flight check in
  `validate`; halt protocol explains the requirement.
- **Long retry loops.** Mitigation: bounded `--max-retries` with
  default 3 and explicit override.
- **Drift between agent post-edits and provenance.** Mitigation:
  manual-edit indicator; `regenerate` always backs up.
- **Phase 2 false negatives.** Mitigation: soft gate with override.

## Out of scope (future work)

- Parallel sandboxes per finding.
- Remote sandboxes.
- Live OS imaging beyond `nested-virt`.
- Cloud-provider integration.
- Provider authentication for `iac-terraform`.

## Done criteria

- All 12 commit boundaries shipped on `master`.
- `make phase-1` on the existing sample target produces a working
  sandbox without manual intervention.
- `make phase-2` blocks correctly on broken sandboxes and respects the
  override.
- `tools/sandbox-bootstrap.py` round-trip (`apply` →
  `validate` → `regenerate`) is idempotent.
- `sandbox-plan.md` halt protocol triggers on a deliberate failure
  scenario.
