# Plan: Discover OpenCode's Default Model + Single-Line Banner

## Status

v1.0. One commit.

## Problem 1: `model=(unknown)` when nothing is pinned

When the user doesn't set `OPENCODE_ARGS=--model …`, `CODECOME_MODEL`,
or `codecome.yml agents.<name>.model`, the wrapper banner says
`model=(unknown)` even though `opencode run` happily uses *its own*
default. The banner is honest but unhelpful.

`opencode models` (with or without `--verbose`) only lists available
models, not the active default. There is no `--default` flag.

The runtime model picked by `opencode run --agent <name>` is stored
in `~/.local/share/opencode/opencode.db` on the `session` table:

    CREATE TABLE session (
      ...
      agent text,
      model text  -- JSON like {"id":"gpt-5.4","providerID":"github-copilot"}
    )

The CodeCome agents (recon, auditor, validator, …) are not stored
on the `session.agent` column — they are prompt+skill bundles that
run under one of OpenCode's top-level agents (`plan` / `build`).
The model picked for those top-level agents is what we want.

So the practical recipe is:

1. Look at the latest session row in `opencode.db` (project-scoped if
   possible) and read its `model` JSON.
2. If found and parseable, use it as the discovered default; banner
   source label = `opencode session history`.

## Problem 2: model line lives on its own line

User asked to fold `model=…` and (when present) `variant=…` onto the
same line as `agent=…  prompt=…`.

## Decisions (locked)

| # | Decision |
|---|---|
| D1 | Best-effort discovery via `opencode db` querying the latest session for this project. |
| D2 | Do not pass discovered defaults back to `opencode run`. Display only. |
| D3 | No caching across phase invocations. Re-query each run. |
| D4 | Discovery has a 1-second timeout and degrades silently to `(unknown)`. |
| D5 | Add `make show-model` (alias `make sandbox-debug-model`) that prints the resolution table from all four sources without launching a phase. |
| D6 | Watch the JSON event stream during the phase run. If a model name appears (e.g. on `step_finish`), print a one-line "model resolved: …" update. |
| D7 | Banner: single line `agent=…  model=…  variant=…?  prompt=…  (model source: …)`. Sources go in trailing parenthetical, only when the source is interesting (i.e. not `OPENCODE_ARGS` for the canonical case where they came from CLI explicitly — actually, always show the source). |
| D8 | Wrap source labels onto a second line only if the terminal is too narrow. Rich already soft-wraps; on plain mode we just print one long line. |
| D9 | `finding=` (Phase 4/5) stays on its own line. |
| D10 | Phase 1 sub-stage hint stays on its own line. |
| D11 | Stay silent about the unknown case (no extra hint about how to fix it). |

## Resolution order (updated)

Highest priority wins:

1. `OPENCODE_ARGS` containing `--model …` / `--variant …`
2. Env vars `CODECOME_MODEL` / `CODECOME_MODEL_VARIANT`
3. `codecome.yml` `agents.<agent>.model` / `agents.<agent>.variant`
4. **NEW:** `opencode db` latest session model (best-effort,
   read-only, 1-second timeout, project-scoped)
5. `(unknown)`

Source labels:

- `OPENCODE_ARGS`
- `env CODECOME_MODEL`, `env CODECOME_MODEL_VARIANT`
- `codecome.yml`
- `opencode session history`
- `(unknown)`

## File-level changes

### `tools/run-agent.py`

#### New helper: `_discover_opencode_default_model()`

```python
def _discover_opencode_default_model() -> Optional[str]:
    """Best-effort: return the model used in the most recent opencode
    session for this project's worktree, or None.

    Honors a 1-second timeout. Errors are silently ignored.
    """
```

Implementation outline:

- Run `opencode db "SELECT s.model FROM session s JOIN project p ON
  s.project_id = p.id WHERE p.worktree = ? AND s.model IS NOT NULL
  ORDER BY s.time_updated DESC LIMIT 1" --format tsv` with the
  current `ROOT` as the parameter — but `opencode db` doesn't
  parameterize, so we shell-quote.
- If that fails or returns nothing, broaden: latest session globally
  with `model IS NOT NULL`.
- Parse the JSON column to extract `{"id": …, "providerID": …}` and
  format as `<providerID>/<id>`.
- Fail silently on any error or after 1s.

#### Update `resolve_model_and_variant`

Add the new fourth source. Variant is not in the DB schema (no
`variant` column), so variant from this source is always None.

Returns model and source labels exactly like before.

#### Update `build_child_command`

Today, env / yaml results cause us to append `--model` / `--variant`
to the child. We must **not** do that for the new "opencode session
history" source because:

- it's display-only,
- forcing it would surprise the user the first time they globally
  switch model.

So append only when source is `env CODECOME_MODEL` or
`codecome.yml`.

#### Single-line banner

Replace the current two-line banner with one line:

    f"agent={args.agent}  model={model_label}  "
    + (f"variant={variant_label}  " if variant else "")
    + f"prompt={args.prompt_file}  "
    + (f"(model source: {model_source}"
       + (f", variant source: {variant_source})" if variant else ")"))

Same for plain mode.

#### Stream-based late discovery (D6)

Add a tiny helper that watches `tool_use` / `step_finish` events for
any field that mentions a model. From the spike captures we don't
see one today, but this is forward-compatible:

- When parsing each event, recursively walk the `part` looking for
  any dict key matching `^model$|providerID|modelID` whose value is
  a string. If we find one and it differs from what we displayed in
  the banner, print one extra line:

      [model resolved] anthropic/claude-opus-4-7  (from step_finish)

- Only print once per run.
- Silent if never found (today's behavior).

### `Makefile`

Add `show-model` target that calls a new
`tools/sandbox-bootstrap.py show-model` (or just runs the resolver
inline in a small Python invocation). Print a small table:

    Model resolution for agent recon:
      OPENCODE_ARGS               -> (not set)
      env CODECOME_MODEL          -> (not set)
      codecome.yml                -> (not set)
      opencode session history    -> github-copilot/gpt-5.4
      effective                   -> github-copilot/gpt-5.4 (source: opencode session history)

Allow choosing the agent: `make show-model AGENT=auditor`. Default
agent is `recon` (i.e., what Phase 1 uses).

The cleanest implementation is to delegate to a new
`tools/run-agent.py --resolve-model AGENT` mode rather than putting
this in `tools/sandbox-bootstrap.py`. Less coupling.

### `README.md` and `docs/workflow.md`

Add the new env-var precedence, the discovery source, and `make
show-model`.

### `.project/restore-model-banner-plan.md`

Append a "v1.1 follow-up" note pointing at this plan and noting that
the resolution order grew to 5 sources.

## Verification

1. Without any pin, banner shows
   `agent=recon  model=<discovered>  prompt=…  (model source: opencode session history)`.
2. With `OPENCODE_ARGS='--model X'`, source is `OPENCODE_ARGS`,
   wrapper passes `--model X`.
3. With `CODECOME_MODEL=X`, source is `env CODECOME_MODEL`, wrapper
   passes `--model X`.
4. With `agents.recon.model: X` in `codecome.yml`, source is
   `codecome.yml`, wrapper passes `--model X`.
5. With nothing set and an empty opencode.db, banner shows
   `(unknown)`.
6. `make show-model` prints the resolution table without launching a
   phase.

## Out of scope

- Hooking into `opencode db` for variant discovery (DB has no variant
  column).
- Per-agent persistence of pinned models inside `codecome.yml`
  beyond what we already have.
- Caching the discovery result across phase runs.

## Done criteria

- One commit on master.
- All four source paths display cleanly on a single banner line.
- `make show-model` works from any agent name.
- Discovery has 1s timeout and silent failure.
- Stream-based late discovery prints "model resolved" if and only if
  the JSON stream actually carries the field.
