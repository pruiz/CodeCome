# CodeCome Sandbox

The CodeCome sandbox is the local execution environment used to
validate findings.

It lives under:

    sandbox/

The sandbox is intentionally separate from the target source code
under:

    src/

## Phase 1b auto-bootstrap

`sandbox/` is **semi-ephemeral**. CodeCome regenerates its contents
during Phase 1b based on what the recon agent learned about `src/`.
Curated baselines live under:

    templates/sandboxes/<id>/

For each baseline the agent picks (e.g. `python`, `c-cpp`,
`multi-service-compose`), `tools/sandbox-bootstrap.py apply <id>`
copies the files into `sandbox/`, substitutes `__VARNAME__`
markers, and writes provenance into `sandbox/CODECOME-GENERATED.md`.

After bootstrap, `sandbox/` typically contains:

    sandbox/Dockerfile
    sandbox/docker-compose.yml
    sandbox/scripts/build-target.sh
    sandbox/scripts/check.sh
    sandbox/scripts/clean.sh
    sandbox/scripts/down.sh
    sandbox/scripts/logs.sh
    sandbox/scripts/reset.sh
    sandbox/scripts/shell.sh
    sandbox/scripts/test-target.sh
    sandbox/scripts/up.sh
    sandbox/CODECOME-GENERATED.md
    sandbox/.backup-<UTC-timestamp>/  (if a previous content was replaced)

`sandbox/CODECOME-GENERATED.md` and `sandbox/.backup-*/` are git-ignored.
Everything else in `sandbox/` is also ignored, except `sandbox/.gitkeep`.

## Bootstrap CLI

| Command | Make target |
|---|---|
| List examples | `make sandbox-list` |
| Inspect one example | `make sandbox-inspect ID=python` |
| Detect candidates from src/ | `make sandbox-detect` |
| Apply an example | `make sandbox-bootstrap ID=python` |
| Re-apply with backup | `make sandbox-regenerate` |
| Run validation tiers | `make sandbox-validate` |
| Show provenance and gate | `make sandbox-status` |

Pass extra args via `BOOTSTRAP_ARGS`:

    BOOTSTRAP_ARGS='--var TARGET_NAME=demo --var PYTHON_VERSION=3.12 --dry-run' \
      make sandbox-bootstrap ID=python

Environment variables:

| Var | Default | Purpose |
|---|---|---|
| `CODECOME_ALLOW_NO_SANDBOX` | unset | Soft override of the Phase 2 sandbox gate. |
| `CODECOME_BOOTSTRAP_MAX_RETRIES` | 3 | Agent remediation budget. |
| `CODECOME_BOOTSTRAP_DRY_RUN` | unset | Force `--dry-run` on `apply`/`regenerate`. |
| `CODECOME_VALIDATE_TAIL_LINES` | 50 | Lines of stderr/stdout captured per tier. |

## Validation tiers

`make sandbox-validate` runs four tiers in order:

| Tier | Purpose | Default command |
|---|---|---|
| T1 | Image build | `sandbox/scripts/up.sh` (or `docker compose -f sandbox/docker-compose.yml build`) |
| T2 | Sandbox sanity | `sandbox/scripts/check.sh` |
| T3 | Target build | `sandbox/scripts/build-target.sh` |
| T4 | Target test | `sandbox/scripts/test-target.sh` |

By default, validate stops at the first failed tier. Pass
`BOOTSTRAP_ARGS='--keep-going'` to run all tiers regardless.

The validation matrix is appended to
`sandbox/CODECOME-GENERATED.md` so each run is auditable.

## Phase 2 sandbox gate

Before running `make phase-2`, the gate inspects the most recent
validation outcome:

| State | Outcome |
|---|---|
| sandbox missing | block |
| validation failed | block |
| validation passed | pass |
| validation mixed (passed+skipped) | pass with warning |
| no validation run yet | pass with warning |
| user-managed sandbox | pass (user owns it) |

Override the gate with `CODECOME_ALLOW_NO_SANDBOX=1`. Always
documents the override in the sandbox-plan halt section.

## Sandbox boundaries

Validators may freely experiment inside the sandbox.

Allowed:

- install packages,
- compile code,
- run local services,
- run local tests,
- run debuggers,
- run sanitizers,
- create payloads,
- create temporary files,
- reset local test data,
- inspect local logs.

Not allowed:

- attack third-party systems,
- use production credentials,
- exfiltrate secrets,
- modify production systems,
- perform destructive actions outside the workspace,
- modify `src/` unless explicitly instructed.

## Write locations

Validation evidence belongs under:

    itemdb/evidence/<finding-id>/

Temporary files belong under:

    tmp/

Run summaries may be stored under:

    runs/

Important evidence should not exist only in terminal output.

## Evidence examples

Useful evidence files:

    itemdb/evidence/CC-0001/README.md
    itemdb/evidence/CC-0001/commands.txt
    itemdb/evidence/CC-0001/output.txt
    itemdb/evidence/CC-0001/logs.txt
    itemdb/evidence/CC-0001/sanitizer.log
    itemdb/evidence/CC-0001/crash.txt
    itemdb/evidence/CC-0001/request.http
    itemdb/evidence/CC-0001/response.txt
    itemdb/evidence/CC-0001/exploit.py
    itemdb/evidence/CC-0001/payload.bin
    itemdb/evidence/CC-0001/test-output.txt
    itemdb/evidence/CC-0001/debugger-notes.md
    itemdb/evidence/CC-0001/static-proof.md
    itemdb/evidence/CC-0001/limitations.md

## Special validation models

Two escape hatches exist when Docker is not enough or not needed:

- `static-only`: target cannot be executed locally (firmware,
  binary-only, license-restricted, corpus-too-large). Requires
  explicit justification in `itemdb/notes/sandbox-plan.md`.
- `nested-virt`: target requires QEMU-in-Docker. Apply the
  `nested-virt` example from `templates/sandboxes/`. KVM
  acceleration is enabled by default; comment out the `/dev/kvm`
  device on hosts without it.

## Future isolation model

The initial PoC uses one validation worker at a time.

Future versions may isolate validation workers using:

- one Docker Compose project per finding,
- one container per finding,
- one disposable VM per finding,
- one remote sandbox per finding.

Each worker should write only to:

    itemdb/evidence/<finding-id>/
    runs/

and should not share mutable runtime state with other validation
workers.

## License

CodeCome is dual-licensed under your choice of:

- GNU General Public License version 3 or later (`GPL-3.0-or-later`), or
- GNU Affero General Public License version 3 or later (`AGPL-3.0-or-later`).

SPDX expression: `GPL-3.0-or-later OR AGPL-3.0-or-later`.

The files under `templates/sandboxes/` are an exception: they are
licensed under the **MIT License** so they can be copied into user
workspaces without imposing copyleft obligations on those user
projects.

See `LICENSE`, `AGPL-LICENSE`, `templates/sandboxes/LICENSE`, and
`NOTICE`. Contributions are accepted under the terms described in
`CONTRIBUTING.md`.

Copyright (C) 2025-2026 Pablo Ruiz García &lt;pablo.ruiz@gmail.com&gt;.
