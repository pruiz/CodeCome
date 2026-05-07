# Plan: Sandbox Templates Are Seeds, Not Finished Sandboxes

## Status

v1.0. Doctrine + tooling fix. One commit.

## Problem

A real Phase 1b run on the existing target (`src/sample-c-cli`)
recorded T2 (sandbox sanity) as `skipped` with the explanation:

> the c-cpp template doesn't ship `scripts/check.sh`. Compensated
> by a manual toolchain spot-check recorded in sandbox-plan.md.

This is wrong. The intent is that **the agent extends the template
into a fully working sandbox**, including authoring missing
lifecycle scripts. Treating absence of `check.sh` in the template
as a hard fact and replacing it with an in-chat manual spot-check
violates the workflow.

The cause spans three places:

1. The skill never explicitly tells the agent that templates are
   starting points to extend.
2. The Phase 1b prompt does not mention the script-completion
   step.
3. `tools/sandbox-bootstrap.py validate` reports T2 as `skipped`
   when `check.sh` is missing, which the agent reads as
   acceptable.

## Decisions (locked)

| # | Decision |
|---|---|
| 1 | Missing-script outcome in `validate`: `failed` + explicit reason. The Phase 2 gate already blocks `failed`, forcing the agent to write the script. |
| 2 | The skill names a canonical script list for Phase 1b output, plus a clear rule that the agent is free to add more scripts when the target needs them, and must document those in `itemdb/notes/sandbox-plan.md`. |
| 3 | Doctrine wording is forceful, not explanatory. |
| 4 | Each `templates/sandboxes/<id>/notes.md` gets a one-line "seed reminder" so the doctrine is visible from inside the template too. |
| 5 | One commit covering skill + prompt + tool + per-template notes. |

## Canonical Phase 1b sandbox script set

These are the scripts the agent must produce in `sandbox/scripts/`
unless a target-specific reason makes one inapplicable. Inapplicability
must be documented in `sandbox-plan.md`.

| Script | Purpose |
|---|---|
| `build-target.sh` | Build the target inside the sandbox. (Templates ship a starter; adapt it.) |
| `test-target.sh` | Run the target's tests inside the sandbox. (Templates ship a starter; adapt it.) |
| `check.sh` | Smoke-check toolchain and workspace mounts inside the container. |
| `up.sh` | Build images and bring the stack up. |
| `down.sh` | Tear the stack down. |
| `shell.sh` | Open an interactive shell in the sandbox. |
| `logs.sh` | Tail logs from the running stack. |
| `clean.sh` | Remove stack containers, volumes, and local tmp produced by validation. |
| `reset.sh` | Reset the sandbox to a known-good state. |

Additional scripts (e.g. `run-target.sh`, `asan-build.sh`,
`fuzz-corpus.sh`, `attach-debugger.sh`) are encouraged when the
target benefits. The agent must list any extras in `sandbox-plan.md`.

## Rules for the agent

1. Templates under `templates/sandboxes/<id>/` are seeds. The agent
   must produce a fully functional `sandbox/` from the chosen seed.
2. If a canonical script does not exist after `apply`, the agent
   writes it, places it under `sandbox/scripts/`, makes it
   executable, and records it in the manual-edit indicator section
   of `sandbox/CODECOME-GENERATED.md`.
3. Manual in-chat spot-checks are not validation. Tool checks
   performed during reasoning must be encoded in `check.sh` so
   future runs reproduce them.
4. T2 must never be recorded as `skipped` because `check.sh` is
   absent. Either the agent authored it (T2 runs) or the validation
   tool reports `failed` (script missing).
5. T1 must never be recorded as `skipped` because `up.sh` is absent.
   Same rule.
6. T3/T4 may legitimately be `skipped` only when the target
   genuinely has no build or test step (e.g. a pre-built firmware
   blob with `static-only` justification). The reason must be in
   `sandbox-plan.md`.
7. Extra scripts the agent invents are documented in
   `sandbox-plan.md` under "Extra scripts authored".

## File-level changes

### `.opencode/skills/sandbox-bootstrap/SKILL.md`

Replace the existing "Validation tiers" section preamble and add a
new top section:

- **"Templates are seeds, not finished sandboxes"** — forceful
  doctrine, two paragraphs.
- **"Canonical Phase 1b script set"** — table copied from this plan.
- **"Authoring missing scripts"** — concrete rules for each
  canonical script (one-liner each), plus the "you may add more"
  permission, plus the documentation requirement.
- **"T1/T2 reporting rule"** — never record `skipped` for missing
  scripts.

### `prompts/phase-1-recon.md`

Insert a new step 5b between the current step 5 (apply) and step 6
(validate):

    5b. Author missing sandbox scripts.

        Templates are seeds. After `apply`, ensure `sandbox/`
        contains the canonical script set:
        check.sh, up.sh, down.sh, shell.sh, logs.sh, clean.sh,
        reset.sh (in addition to the build-target.sh and
        test-target.sh provided by the template).
        Adapt the template's build-target.sh and test-target.sh
        to the actual project layout. Add target-specific
        scripts when they help. Make every script executable and
        document any extras in sandbox-plan.md.

### `tools/sandbox-bootstrap.py`

Adjust the four tier resolvers and the `cmd_validate` flow:

- T1 / T2 / T3 / T4: when the expected script is absent, return a
  failed `TierResult` with `command="(missing: <relative path>)"`
  and `stderr_tail="script not found; the agent must author this
  script during Phase 1b"` instead of recording `skipped`.
- The fall-through "no resolver" branch (used for T1 when no
  compose file exists either) becomes `failed` for T1 and `failed`
  for T2; T3 and T4 retain `skipped` when explicitly inapplicable.
  However, T3 and T4 inapplicability must be a positive statement,
  not the default; until we model that, we mark T3/T4 as `failed`
  too when their scripts are absent. The agent's halt protocol
  covers explicit-inapplicability cases.
- Decision: for v1, treat **all four** missing scripts as `failed`.
  This matches the gate semantics and the doctrine.
- The Phase 2 gate already blocks `failed`, so this propagates
  correctly without further changes.

### `templates/sandboxes/<id>/notes.md`

Append a single block at the very top of each template's
`notes.md`:

    ## Seed reminder

    This template is a starting point, not a finished sandbox.
    During Phase 1b the agent must extend it into a fully
    functional sandbox/, including authoring missing scripts
    such as check.sh, up.sh, down.sh, shell.sh, logs.sh,
    clean.sh, and reset.sh. Document any extra scripts in
    itemdb/notes/sandbox-plan.md.

Same text in every template; cheap to maintain.

## Verification

After the change, on the existing sample target:

1. `make phase-1` — agent writes the missing scripts and the
   recorded T2 outcome is `passed`, not `skipped`.
2. If we manually delete `sandbox/scripts/check.sh` and run
   `make sandbox-validate`, T2 is reported as `failed` with
   "script not found" reason.
3. `make sandbox-status --gate` exits non-zero in that scenario,
   blocking Phase 2.

## Out of scope

- Shipping starter `check.sh` per template. Doctrine prefers the
  agent author it tailored to the example, not copy a one-size
  template.
- Distinguishing "T3/T4 not applicable" from "script missing".
  Targets that genuinely don't build or don't test will be flagged
  as failed in v1 and require the agent to add the explicit
  static-only / no-tests justification. Future work can add a
  `manifest.yml` field like `runtime: build-only` or
  `runtime: test-only` to soften this.

## Done criteria

- Single commit on master.
- `make phase-1` on the existing sample target produces a
  fully-populated `sandbox/scripts/` and validates with all four
  tiers `passed`.
- Removing any canonical script and re-running `make
  sandbox-validate` flips the gate to blocked.
