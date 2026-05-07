# Plan: Restore the Model-In-Use Banner in `make phase-*`

## Status

v1.0. New feature. No upstream OpenCode change required.

## Goal

Make `make phase-*` print which model the agent will use, in the
header banner. Optionally let the user pin a model per phase or
project-wide via env vars or `codecome.yml`. When a pin is provided,
also pass it to `opencode run` so the banner is the truth.

## Why this is needed

`opencode run --format json` does not emit `model` / `provider` /
`variant` in `step_start` or any other event. Our wrapper, which we
introduced to take over rendering, therefore lost the model badge
that the default `opencode run` renderer used to print.

## Decisions (locked)

| # | Decision |
|---|---|
| 1 | Option A: best-effort resolution before launch. |
| 2 | When the resolved model comes from YAML or env, pass it to `opencode run` via `--model`. |
| 3 | Same for variant: `--variant`. |
| 4 | Visibility is scoped to `make phase-*`. Bare `tools/run-agent.py` invocations also benefit because they go through the wrapper. |
| 5 | Env var names: `CODECOME_MODEL` and `CODECOME_MODEL_VARIANT`. |

## Resolution order

Highest priority wins:

1. **OPENCODE_ARGS** containing `--model …` and/or `--variant …`. The
   user already passes `OPENCODE_ARGS` to inject extra flags. We
   parse it, do not modify it, and just display whatever model /
   variant it contains.
2. **Env vars** `CODECOME_MODEL` and `CODECOME_MODEL_VARIANT`. If
   set and `OPENCODE_ARGS` does not already pass `--model` /
   `--variant`, the wrapper appends them.
3. **`codecome.yml`** at `agents.<agent>.model` and
   `agents.<agent>.variant`. If set and not already overridden by
   sources 1 or 2, the wrapper appends them.
4. **Unknown**. Display `model=(unknown)` so the banner makes the
   gap visible. The wrapper does not invent a model.

The banner shows the **source** of the resolved value:

    agent=recon  model=anthropic/claude-opus-4-7  variant=high  prompt=…  (model source: codecome.yml)

Sources are reported with these labels:

- `OPENCODE_ARGS`
- `env CODECOME_MODEL`
- `codecome.yml`
- `(unknown)`

## File-level changes

### `tools/run-agent.py`

- New helper:

      def resolve_model_and_variant(
          agent_name: str,
          opencode_args_tokens: list[str],
      ) -> tuple[Optional[str], Optional[str], str, str]:
          # returns (model, variant, model_source, variant_source)

  Reads `OPENCODE_ARGS` tokens, env, then `codecome.yml`. Each
  resolution returns the source label.
- `build_child_command(args)` is updated to:
  - keep parsing `OPENCODE_ARGS` as today,
  - if `--model` is not already in those tokens and we resolved a
    model from env or yaml, append `--model <value>`,
  - same for `--variant`.
- Banner block (rich and plain) prints the new line:

      agent=recon  model=…  variant=…  prompt=…  (model source: …)

### `codecome.yml`

Optional, additive. New top-level structure:

    agents:
      recon:
        model: "anthropic/claude-opus-4-7"
        variant: "high"
      auditor:
        model: "anthropic/claude-opus-4-7"
      reviewer:
        model: "anthropic/claude-opus-4-7"
      validator:
        model: "anthropic/claude-opus-4-7"
      exploiter:
        model: "anthropic/claude-opus-4-7"
      reporter:
        model: "anthropic/claude-opus-4-7"

Wrapper reads only `agents.<name>.model` and `agents.<name>.variant`.
Anything else under `agents:` is left for future use.

We will ship `codecome.yml` with **the section commented out** by
default so we don't accidentally pin a model nobody asked for. Users
who want pinning uncomment.

### `Makefile`

Help blurb gains `CODECOME_MODEL=…` and `CODECOME_MODEL_VARIANT=…`
under the wrapper controls.

### `README.md`, `docs/workflow.md`

Mention the new env vars and the optional YAML per-agent pinning.

## Implementation notes

- Token parsing: existing code already does
  `shlex.split(os.environ.get("OPENCODE_ARGS", ""))`. We re-use the
  resulting list; we do not re-implement.
- We must look for `--model` and `-m` (short form) in OPENCODE_ARGS.
  Same for `--variant`.
- When OPENCODE_ARGS already pins, we **do not** append from env or
  yaml, even if env/yaml differ. The user's most explicit knob wins.
- When the YAML has neither key, behavior is identical to today.
- Banner says `model=(unknown)` when nothing is resolved. We do not
  probe `opencode` to discover the user's global default because
  that probe is unreliable and slow.

## Tests / verification

After implementation, verify five paths:

1. No env, no yaml, no OPENCODE_ARGS → banner says
   `model=(unknown)  (model source: (unknown))`. Wrapper does not
   pass `--model`.
2. `OPENCODE_ARGS='--model anthropic/claude-sonnet-4-5'` → banner
   says model=…  (model source: OPENCODE_ARGS). Wrapper does not
   re-add the flag.
3. `CODECOME_MODEL=anthropic/claude-sonnet-4-5` → banner says model
   from `env CODECOME_MODEL`. Wrapper command line shows `--model`
   appended.
4. `codecome.yml` with `agents.recon.model: …` → banner shows yaml
   source for `make phase-1`, unknown for other phases unless
   filled. Wrapper command line shows `--model` appended.
5. Mix: env set + yaml set + OPENCODE_ARGS set → OPENCODE_ARGS
   wins. Lower-priority values are ignored.

For cases 3, 4, 5, we'll inspect the constructed child command
without actually calling `opencode` to keep tests fast.

## Out of scope for v1

- Probing OpenCode to learn the global default model.
- Per-phase model overrides via Make variables (e.g.
  `MODEL=anthropic/claude-sonnet-4-5 make phase-1`). Skippable
  because `OPENCODE_ARGS='--model …' make phase-1` already works.

## Done criteria

- `make phase-*` prints `model=…` and `variant=…` (when applicable)
  in the header.
- All five test paths behave as specified.
- Docs mention the env vars and the optional YAML field.
- Single commit on master.
