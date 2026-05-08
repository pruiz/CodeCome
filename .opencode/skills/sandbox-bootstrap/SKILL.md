# Sandbox Bootstrap Skill

Use this skill during CodeCome **Phase 1b: Sandbox bootstrap**.

Phase 1b runs immediately after Phase 1a (source reconnaissance) in
the same `make phase-1` invocation. The goal is to ensure that
`sandbox/` contains a working validation environment for the target
under `src/`, so Phase 2 can rely on it.

## Templates are seeds, not finished sandboxes

Every directory under `templates/sandboxes/<id>/` is a **seed**.
Each seed ships only `Dockerfile`, `docker-compose.yml`, a starter
`scripts/build-target.sh`, and a starter `scripts/test-target.sh`.

That is on purpose. The agent is expected to extend the seed into a
fully functional sandbox tailored to the specific target. Treating
a seed as a finished sandbox is a workflow violation.

You **must**:

- implement the required sandbox capabilities (see "Sandbox
  capability contract" below), preferably via helpers under
  `sandbox/scripts/`,
- adapt the starter `build-target.sh` and `test-target.sh` to the
  real project layout (some targets nest their build under a
  subdirectory of `src/`, not `src/` directly; many real targets do similar),
- add target-specific scripts when they help (sanitizer builds,
  fuzzing harnesses, debugger attach helpers, etc.),
- make every script executable,
- document every authored or adapted script in
  `itemdb/notes/sandbox-plan.md`.

You **must not**:

- record a validation tier as `skipped` because its script is
  absent,
- replace authoring a script with an in-chat manual spot-check
  (manual checks are not durable and do not survive the next
  `make phase-1` run),
- assume that "the template ships only X" means "only X is
  expected to exist".

## Sandbox capability contract

Phase 1b does not require one universal fixed script set. Different
targets need different mechanics. What matters is that the resulting
`sandbox/` exposes a coherent set of capabilities.

Required capabilities for a Phase 2-ready sandbox:

| Capability | Preferred helper | Purpose |
|---|---|---|
| build sandbox | `sandbox/scripts/build-sandbox.sh` | Build the sandbox artifact in a repeatable way. This may be a container image, VM image, firmware bundle, or other runnable sandbox artifact. |
| start sandbox | `sandbox/scripts/up.sh` | Bring the sandbox environment up when runtime startup is distinct from build. |
| sandbox sanity check | `sandbox/scripts/check.sh` | Verify mounts, toolchain/runtime availability, and basic health. |
| build target | `sandbox/scripts/build-target.sh` | Build the target inside the sandbox when applicable. |
| test target | `sandbox/scripts/test-target.sh` | Run the target tests inside the sandbox when applicable. |
| stop sandbox | `sandbox/scripts/down.sh` | Tear the sandbox environment down cleanly. |

Recommended helper capabilities when the target/runtime model makes
them useful:

| Capability | Preferred helper | Purpose |
|---|---|---|
| stop environment | `sandbox/scripts/down.sh` | Tear the environment down cleanly. |
| shell entry | `sandbox/scripts/shell.sh` | Open a shell in the sandbox. |
| logs access | `sandbox/scripts/logs.sh` | Inspect runtime logs. |
| clean runtime artifacts | `sandbox/scripts/clean.sh` | Remove containers, volumes, and tmp produced by validation. |
| reset to known state | `sandbox/scripts/reset.sh` | Recreate the environment from a clean state. |

If a recommended helper does not apply, say so explicitly in
`sandbox-plan.md`. Do not silently omit it.

Add additional scripts whenever the target benefits, for example:

- `run-target.sh` — drive the target with a sample input.
- `asan-build.sh` — build with AddressSanitizer + UBSan.
- `fuzz-corpus.sh` — seed a fuzzing corpus.
- `attach-debugger.sh` — attach gdb / lldb to a running container.
- `reset-target.sh` — reset target-specific state inside the
  container without tearing down the whole stack.

Document any extras in `itemdb/notes/sandbox-plan.md` under "Extra
scripts authored", with one line per script explaining what it does
and how to run it.

## Authoring conventions for helper scripts

- All helper scripts are bash with `set -euo pipefail` at the top.
- Path discipline: paths inside the container start with
  `/workspace/...`; paths on the host start with `sandbox/...`.
- Idempotency: `down.sh`, `clean.sh`, and `reset.sh` should be safe
  to run repeatedly even when the stack is already down.
- `check.sh` runs **inside the sandbox container**, exercising the
  toolchain (compiler versions, package manager versions, language
  runtime versions) and verifying the expected workspace mounts
  exist (`/workspace/src`, `/workspace/itemdb`, `/workspace/sandbox`,
  `/workspace/AGENTS.md`, `/workspace/codecome.yml`).
- `build-sandbox.sh` should build the sandbox artifact without implying
  the environment must be started. When Docker Compose is used, it
  should typically run `docker compose -f sandbox/docker-compose.yml
  build`.
- `up.sh` runs `docker compose -f sandbox/docker-compose.yml up -d
  --build` (or the multi-service variant) when the sandbox needs a
  long-lived environment. If the target does not need a persistent
  started stack, explain that in `sandbox-plan.md`.
- `shell.sh` runs `docker compose -f sandbox/docker-compose.yml
  exec <service> bash` or `docker compose run --rm <service>
  bash`.
- `logs.sh` runs `docker compose -f sandbox/docker-compose.yml
  logs -f`.
- `clean.sh` runs `docker compose -f sandbox/docker-compose.yml
  down -v` and removes any `tmp/` artifacts produced by the
  sandbox.
- `reset.sh` is `clean.sh` followed by `up.sh`, or a tighter
  per-target reset when faster.

## T1/T2/T3/T4/T5/T6 reporting rules

- T1 must never be recorded as `skipped` because the sandbox build
  mechanism is missing. Prefer `build-sandbox.sh`; `docker compose
  -f sandbox/docker-compose.yml build` is an acceptable fallback.
- T2 must never be recorded as `skipped` because the sandbox start
  mechanism is missing when the sandbox requires startup. Prefer
  `up.sh`.
- T3 must never be recorded as `skipped` because the sandbox sanity
  mechanism is missing. Prefer `check.sh`.
- T4/T5 may legitimately be `skipped` only when the target
  genuinely has no build or test step. The reason must be in
  `sandbox-plan.md` (`static-only`, pre-built firmware, header-only
  library, etc.).
- T6 must never be recorded as `skipped` because the sandbox stop /
  teardown mechanism is missing. Prefer `down.sh`.
- A manual in-chat toolchain check is not a substitute for
  `check.sh`.

`tools/sandbox-bootstrap.py validate` enforces these rules for the
required Phase 2 capabilities: a missing build, start, check,
target-build, test, or stop mechanism is reported as **failed** (not
skipped). The Phase 2 gate blocks on `failed`.

## Purpose

Phase 1b answers:

- Does `sandbox/` already work for this target?
- If not, which curated example under `templates/sandboxes/<id>/` is
  the best starting point?
- Does the target ship its own `Dockerfile`, `docker-compose.yml`,
  or runbooks under `src/` that should be honored?
- What marker values are correct for this target (versions, ports,
  target name)?
- Did the validation tiers actually pass?
- If not, what does the user need to do to unblock Phase 2?

## Required output

Write or update:

    itemdb/notes/sandbox-plan.md

This is the durable artifact. Do not leave Phase 1b decisions only
in chat history.

Mandatory sections in `sandbox-plan.md`:

1. **Detected stack** — languages, manifests, and runtime services
   inferred from Phase 1a notes.
2. **Honoring decision** — what `src/` artifacts were honored,
   wrapped, or ignored, and why. Mandatory even when nothing is
   honored ("nothing to honor").
3. **Chosen example(s)** — id from `templates/sandboxes/`.
4. **Marker values applied** — table of `__VARNAME__` → value.
5. **Validation matrix** — for each tier (T1 build, T2 start, T3
   check, T4 build-target, T5 test-target, T6 stop): pass/fail/skipped, last command,
   exit code, last 50 lines of stderr.
6. **`validation_model`** — one of: `docker`, `static-only`,
   `nested-virt`. Justification mandatory for the last two.
7. **Remediation log** — each automatic remediation attempt with its
   rationale and outcome.
8. **Open questions for the user** — optional, only if input is
   needed.
9. **Halt notice** — only when bootstrap could not finish.

## Tooling

The bootstrap CLI lives at `tools/sandbox-bootstrap.py` and is also
exposed via Make targets:

| CLI subcommand | Make target | Status |
|---|---|---|
| `list` | `make sandbox-list` | available |
| `inspect <id>` | `make sandbox-inspect ID=<id>` | available |
| `detect` | `make sandbox-detect` | available |
| `status [--gate]` | `make sandbox-status` | available |
| `apply <id>` | `make sandbox-bootstrap ID=<id>` | available |
| `regenerate` | `make sandbox-regenerate` | available |
| `validate` | `make sandbox-validate` | available |

When a subcommand is "not yet implemented" the CLI exits with code
`64`. All Phase 1b subcommands are now implemented; if you ever
hit code 64, refer to `.project/auto-sandbox-bootstrap-plan.md`.

Always invoke the CLI through the project's virtualenv:

    .venv/bin/python3 tools/sandbox-bootstrap.py <subcommand>

Or via the Make targets when running from the project root.

## Decision flow

```
Phase 1a complete
        |
        v
read itemdb/notes/* for stack hints
        |
        v
inspect sandbox/ state
   |        |        |
empty   tracked   user-managed
   |        |        |
   |        v        v
   |   try-validate-existing
   |        |        |
   |     passes   fails
   |        |        |
   v        v        v
choose example -> apply -> validate -> done
                              |
                          on failure
                              |
                          remediate
                              |
                       within retry budget?
                              |
                            yes/no
                              |
                              v
                         halt + sandbox-plan.md
```

## Inputs to consult before choosing

Always read these files before deciding:

- `itemdb/notes/target-profile.md`
- `itemdb/notes/build-model.md`
- `itemdb/notes/execution-model.md`
- `itemdb/notes/interesting-files.md`
- `itemdb/notes/validation-model.md`
- `src/Dockerfile`
- `src/docker-compose.yml` and `src/docker-compose.yaml`
- `src/compose.yml` and `src/compose.yaml`
- `src/Makefile`
- `src/scripts/`
- `src/README*`
- `src/CONTRIBUTING*`
- `src/INSTALL*`
- `src/RUN*`
- `src/docs/`

## Honoring `src/` artifacts

If `src/` contains usable runtime definitions, honor them. The
`multi-service-compose` example is built around this case: its build
and test scripts pass `src/docker-compose.yml` as a second `-f`
argument so the user's compose remains authoritative.

Honoring rules:

1. If `src/Dockerfile` defines the runtime, use it via the
   `multi-service-compose` example or by referencing it from a
   thin sandbox wrapper. Do not duplicate it.
2. If `src/docker-compose.yml` is present and runnable, prefer
   layering on top of it via `multi-service-compose`.
3. If `src/Makefile` describes the build, the language-specific
   example's `scripts/build-target.sh` should call it instead of
   re-implementing build logic.
4. If `src/README*` or `src/docs/` describe ports, environment
   variables, or run commands, capture those values into marker
   substitutions or directly into the generated `sandbox/` files.
5. If `src/` artifacts exist but are clearly inappropriate
   (production secrets, cloud-only behavior, build-time-only
   helpers), document the reason in `sandbox-plan.md` under
   "Honoring decision" and proceed with the curated example.

## Build-time vs runtime stacks

A repository can contain build-time helpers (e.g. a Node.js layer
that produces static assets consumed by a Python runtime). Those
helpers should not be expressed as runtime services in the sandbox.
Treat them as multi-stage build steps inside the runtime example's
`Dockerfile`, or as one-off `docker compose run` invocations rather
than always-on services.

## Marker substitution

Examples use `__VARNAME__` markers. The agent fills the values from:

1. recon notes (e.g. exact Python version from `build-model.md`),
2. target documentation in `src/`,
3. sensible defaults if nothing else is known.

Two ways to substitute markers:

- Pass `--var KEY=VAL` to `tools/sandbox-bootstrap.py apply` once
  it is implemented.
- Edit the copied files in `sandbox/` directly. This is the
  manual fallback below.

Do not invent variables that are not defined in `manifest.yml`.

## Preferred flow (using the CLI)

1. Run `make sandbox-detect` to see ranked candidates.
2. Run `make sandbox-inspect ID=<chosen-example>` to see the
   manifest, file list, and markers.
3. Run `make sandbox-status` to see if `sandbox/` is empty,
   user-managed, or generated.
4. If `sandbox/` is user-managed (no `CODECOME-GENERATED.md`) and
   Phase 2 will run, attempt validation against the existing
   scripts first. If it passes, capture the result in
   `sandbox-plan.md` and move on. If it fails, halt with the halt
   protocol and request user guidance — do not silently overwrite
   user-managed content.
5. To bootstrap a fresh sandbox, prefer:

       BOOTSTRAP_ARGS='--var KEY1=VAL1 --var KEY2=VAL2' \
         make sandbox-bootstrap ID=<chosen-example>

   Or, if invoking the CLI directly:

       .venv/bin/python3 tools/sandbox-bootstrap.py apply <id> \
         --var KEY1=VAL1 --var KEY2=VAL2

   Use `--dry-run` first to preview which files would be written
   and which markers are still unfilled. Use `--force` only when
   `sandbox/` has user-managed content that the user has accepted
   to lose (the prior content will be moved to
   `sandbox/.backup-<timestamp>/`).

6. To re-apply after a manifest update or a marker change:

       make sandbox-regenerate
       # or with overrides:
       BOOTSTRAP_ARGS='--var PYTHON_VERSION=3.13' make sandbox-regenerate

   Regenerate reads `sandbox/CODECOME-GENERATED.md` for the source
   example id and the previous markers. CLI overrides win. The
   prior sandbox content is always moved to a fresh
   `sandbox/.backup-<timestamp>/`.

7. Run validation tiers:

       make sandbox-validate

   Or with options:

       BOOTSTRAP_ARGS='--keep-going' make sandbox-validate
       BOOTSTRAP_ARGS='--scripts-only' make sandbox-validate
       BOOTSTRAP_ARGS='--docker-only' make sandbox-validate

   `validate` writes a "Validation run <ISO>" Markdown table at the
   end of `sandbox/CODECOME-GENERATED.md` so each run is auditable.
   Use the JSON output (`--format json`) when scripting the agent
   loop:

       .venv/bin/python3 tools/sandbox-bootstrap.py --format json \
         validate --keep-going

## Validation tiers

| Tier | Purpose | Preferred helper | Fallback |
|---|---|---|---|
| T1 | Sandbox build | `sandbox/scripts/build-sandbox.sh` | `docker compose -f sandbox/docker-compose.yml build` |
| T2 | Sandbox start | `sandbox/scripts/up.sh` | none — implement it when startup is distinct from build |
| T3 | Sanity | `sandbox/scripts/check.sh` | none — implement it |
| T4 | Target build | `sandbox/scripts/build-target.sh` (template ships starter; adapt it) | none — implement it |
| T5 | Target test | `sandbox/scripts/test-target.sh` (template ships starter; adapt it) | none — implement it |
| T6 | Sandbox stop | `sandbox/scripts/down.sh` | none — implement it |

For each tier capture: start time, exit code, last 50 lines of
combined stdout+stderr, duration, outcome
(`passed | failed | skipped`).

A missing required capability causes the tier to record `failed`,
**not** `skipped`. The Phase 2 gate blocks on `failed`.

`skipped` is reserved for tiers that genuinely do not apply to the
target (e.g. `static-only` builds with no executable). Such cases
require a positive justification in `sandbox-plan.md`.

Per-tier failures must be triaged. Do not move to the next tier on
T1/T2/T3 failure unless the user explicitly asks for `--keep-going`.

## Auto-remediation

The agent may attempt automatic remediations when validation fails.
Default budget is 3 attempts; honor the `CODECOME_BOOTSTRAP_MAX_RETRIES`
environment variable when present.

Each attempt must:

1. State the failure cause hypothesis.
2. State what is being changed (file, line range, intent).
3. Re-run validation tiers from where the failure occurred.
4. Record the attempt in the remediation log of `sandbox-plan.md`.

Common remediations:

- Adjust the Debian or language base tag.
- Add a missing native dev package to the Dockerfile.
- Adjust an exposed port marker.
- Replace a hard-coded build command with the one from
  `src/Makefile` or `build-model.md`.
- Drop a useless `EXPOSE` directive when the target has no app
  port.

Stop conditions:

- Retry budget exhausted.
- Failure requires user input that the agent does not have (secret,
  external service, hardware device).
- Failure is outside the sandbox (Docker not installed on host,
  insufficient disk space, etc.).

When stopping, write the halt notice to `sandbox-plan.md`.

## Halt protocol

When bootstrap cannot finish, `sandbox-plan.md` must include:

1. **Attempts** — every remediation step with command and exit
   code.
2. **Root cause hypothesis** — concise diagnosis.
3. **What is needed from the user** — the exact missing input.
4. **Suggested next action** — copy-pasteable.
5. **Halt notice** — explicit "Phase 2 blocked until this is
   resolved" statement.
6. **Override hint** — mention `CODECOME_ALLOW_NO_SANDBOX=1` for
   users who want to proceed despite the missing sandbox.

## Special validation models

Some targets cannot be exercised by Docker alone.

### `static-only`

Use when the target cannot be executed in the local sandbox. Possible
reasons: corpus too large to build, no executable artifacts, license
restriction, cross-compiled firmware that the host cannot run, or a
binary-only edge case where review is purely static.

Required justification section in `sandbox-plan.md`:

    ## Justification: static-only

    - <reason>
    - <evidence from recon notes>

Phase 2 gate honors `static-only` only when the justification is
present.

### `nested-virt`

Use when the target genuinely requires nested virtualization. Apply
the `templates/sandboxes/nested-virt/` example. Document in
`sandbox-plan.md`:

    ## Justification: nested-virt

    - <reason>
    - <required QEMU arch>
    - <KVM availability statement>

## Idempotency rules

1. Never overwrite a non-generated `sandbox/` silently. Detect by
   the absence of `sandbox/CODECOME-GENERATED.md` plus tracked
   user content.
2. Always back up displaced files into
   `sandbox/.backup-<timestamp>/` before modifying.
3. The provenance file must reflect the latest applied example and
   its markers.

## When to ask the user

Ask only when blocked. Do not ask for things that can be inferred
from notes or `src/` artifacts. Examples of legitimate asks:

- "Which Python version should I pin? `pyproject.toml` does not
  specify and `build-model.md` is silent."
- "The repo references a private gem server. Should I skip those
  dependencies for review purposes, or do you have a `bundler`
  config to mount?"
- "The target uses `qemu-system-arm`. Is KVM available on the host?
  If not, runtime validation will be slow."

Ask in `sandbox-plan.md`, not by halting. The user reads the plan
and replies in the next iteration.
