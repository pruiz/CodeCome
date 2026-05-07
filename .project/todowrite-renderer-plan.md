# Plan: Pretty `todowrite` Rendering in `tools/run-agent.py`

## Goal

When the OpenCode agent emits a `todowrite` tool call, render it in CodeCome's wrapper as a compact, human-readable checklist instead of dumping the raw JSON input/output.

## Scope (locked)

- v1 scope: `todowrite` only.
- Other tools (`read`, `glob`, `grep`, `bash`, `apply_patch`, `Write`, `Edit`, etc.) keep their current generic JSON rendering.
- Display strategy is option 2: a single consolidated checklist sourced from `state.output`, falling back to `state.input.todos` if `output` is missing or not a list.
- Panel title becomes the tighter `Todos` (replacing `Tool: todowrite [...]`).
- Icon/priority mapping confirmed:
  - `completed` -> green check
  - `in_progress` -> yellow filled circle
  - `pending` -> dim hollow circle
  - `cancelled` -> dim cross with strikethrough (rich only; plain falls back to `[-]`)
  - priority `high` -> red `H`
  - priority `medium` -> yellow `M`
  - priority `low` -> dim `L`
- Plain-mode ASCII fallback confirmed:
  - `[x]` completed
  - `[~]` in_progress
  - `[ ]` pending
  - `[-]` cancelled
  - priority shown as a single uppercase character: `H`, `M`, `L`, or `?`

## Non-goals

- No truncation of long content.
- No collapsing/folding.
- No per-todo diff between input and output.
- No new color constants in `_colors.py`.
- No new dependencies.
- No replay harness or test framework changes.
- No documentation changes.
- No commit policy changes.

## Where the change lives

Single file modified:
- `tools/run-agent.py`

Touched areas inside that file:
1. `render_tool_use` becomes a small dispatcher that routes to a tool-specific renderer when one exists, otherwise falls back to the current generic JSON-based renderer.
2. New helper `render_todowrite` for the rich path.
3. New helper `render_todowrite_plain` for the no-rich path.
4. New helper `extract_todos` that performs defensive validation of the payload shape and returns either a normalized list or `None`.
5. Optional small helpers for status/priority symbol mapping, kept private to the module.

No additional dependencies. No `requirements.txt` change. No Makefile change.

## Detection rules

A payload qualifies for pretty rendering only when ALL of these hold:

- `tool == "todowrite"`
- `state` is a dict
- `state.output` is a list (preferred) OR `state.input.todos` is a list
- the chosen list contains zero or more dicts
- each dict, when present, may have any subset of `content`, `status`, `priority`

If any check fails, the renderer falls back to the existing generic JSON path. Never raise; always degrade gracefully.

## Source-of-truth selection

1. If `state.output` is a list, use it as the consolidated todo state.
2. Else if `state.input` is a dict and `state.input.todos` is a list, use that.
3. Else fall back to the generic JSON renderer.

This matches option 2 with a defensive fallback. Input vs output diffing is intentionally out of scope.

## Rich rendering layout

Single Rich `Panel`:
- Title: `Todos`
- Border color: green if all todos are `completed`, yellow if any are `in_progress`, dim otherwise. Final color choice can be tweaked at implementation time but must use `_colors.py` constants where possible.
- Body composition:
  - line 1: compact summary, e.g. `4 tasks · 2 completed · 1 in progress · 1 pending`
  - blank line
  - a Rich `Table` with no header repetition and tight padding:
    - column 1: status icon
    - column 2: priority tag
    - column 3: content (soft-wrapped)

Edge cases:
- Empty list: panel body is the single line `No todos.`
- Missing `status`: render `?` icon
- Missing `priority`: render `?` priority tag
- Missing `content`: render empty content cell, never crash
- `status` not in known set: render the raw status text in dim
- `priority` not in known set: render `?`

## Plain ASCII rendering layout

Used when `rich` is not available.

```
todos
  4 tasks · 2 completed · 1 in progress · 1 pending
  [x] H Read required guidance and templates for recon phase
  [~] H Inspect src tree to infer target type, build model, and technologies
  [ ] M Write optional run summary under runs/ if practical
```

Plain mode rules:
- header line `todos` printed via `_colors.header`
- summary line indented by two spaces
- each todo on its own line, indented by two spaces
- bullet uses ASCII checkbox, then space, then priority letter, then space, then content
- if `content` contains newlines, replace them with spaces in plain mode (no soft wrap), to keep one row per todo

## Defensive behavior

Mandatory:
- Wrapper must never crash on malformed `todowrite` payloads.
- If `extract_todos` returns `None`, the dispatcher falls through to the generic JSON renderer and the panel title remains `Tool: todowrite [<status>]` as today, so we still show the data, just unstyled.

Mandatory:
- The `--debug` mode must continue to mirror the raw JSON event line to stderr unchanged. The pretty renderer must not interfere with that.

## Footer behavior

No change. The existing dim line `step finished: <reason> (...)` continues to be printed by `render_step_finish`.

## Color and theming

- Reuse `tools/_colors.py` constants:
  - `BOLD_GREEN` for completed
  - `YELLOW` for in_progress
  - `DIM` for pending and cancelled
  - `RED` for `H`
  - `YELLOW` for `M`
  - `DIM` for `L`
- The `rich` path may use Rich style strings that map to these intentions but should not invent unrelated palettes.
- The plain mode also runs through `_colors.py` so `NO_COLOR` and `CLICOLOR_FORCE` continue to behave correctly.

## Tool dispatch contract

Pseudo-shape:

```python
TOOL_RENDERERS = {
    "todowrite": render_todowrite,
}

def render_tool_use(console, event):
    tool = event["part"].get("tool", "unknown")
    state = event["part"].get("state", {})
    renderer = TOOL_RENDERERS.get(tool)
    if renderer is not None:
        rendered = renderer(console, state)
        if rendered:
            return
    # fall through to existing generic rendering
    ...
```

`render_todowrite` returns a truthy value when it successfully rendered, falsy when the dispatcher should fall back. This contract must be preserved so future tool renderers slot in cleanly.

## Symbol choices

Recommended Unicode glyphs (aligned with existing `_colors.py` usage):
- completed: `✔`
- in_progress: `●`
- pending: `○`
- cancelled: `✖` with strike (rich only)

If any of these glyphs render poorly in some terminals, the plain ASCII fallback is already defined.

## Validation plan (manual)

After implementation, validate with:

1. `make phase-1` on `src/sample-c-cli/` and visually confirm:
   - the panel is titled `Todos`
   - status/priority icons are correct
   - summary line counts are accurate
2. `make phase-2` and confirm the rendering remains correct as the agent updates the same todo list multiple times during a longer run.
3. A phase that emits a non-`todowrite` tool call (any of `read`, `glob`, `grep`, `bash`, `apply_patch`) and confirm generic JSON rendering is unchanged.
4. `NO_COLOR=1 make phase-1` and confirm:
   - no ANSI codes
   - plain ASCII layout for todos as specified above
5. `make phase-1` with the wrapper running outside the venv (forcing the no-rich fallback) and confirm the plain mode renders todos correctly.
6. `make phase-1 --debug` (via `OPENCODE_ARGS` if needed, or by passing `--debug` directly to `tools/run-agent.py` in a manual test) and confirm raw JSON still hits stderr unchanged.

If any of those steps fails, fix and re-run that step before claiming done.

## Risks

1. Pretty printing hides information present in the raw JSON.
   - Mitigation: only triggers on the recognized shape; anything unexpected falls through to generic rendering.
2. Schema drift in `todowrite` payloads.
   - Mitigation: every field access is defensive; missing fields render as `?`.
3. Different terminals/locales render Unicode glyphs poorly.
   - Mitigation: plain mode uses ASCII; rich mode follows the existing project convention for glyphs.
4. Risk of regression in the generic tool-call panel.
   - Mitigation: dispatch only intercepts `todowrite`; all other tools take the unchanged path.
5. Border color heuristic may feel inconsistent if mixed states are common.
   - Mitigation: rule is documented above. If it bothers us in practice, it can be revisited without changing the plan structure.

## Acceptance criteria

The implementation is considered done when:

- A `todowrite` tool call from a real `make phase-*` run renders as a `Todos` panel with summary line and table, no raw JSON.
- A `todowrite` payload with missing or unexpected fields renders without crashing.
- A `todowrite` payload with shape not recognized falls back to the existing generic JSON rendering.
- A non-`todowrite` tool call renders exactly as it does today.
- Plain mode prints the ASCII layout above with no ANSI codes when `NO_COLOR=1`.
- `--debug` continues to mirror the raw JSON event to stderr unchanged.
- No new dependency added. No documentation churn.

## Out-of-scope follow-ups (not part of this work)

- Pretty rendering for `read`, `bash`, `apply_patch`, `grep`, `Write`, `Edit`.
- Truncation/folding policies for very long tool outputs.
- A replay harness using `.project/spikes/opencode-json/*.jsonl`.
- Per-tool theming controls or user-configurable mappings.

## Decisions still implicit (no action needed unless you object)

- Plain-mode header uses lowercase `todos` for visual difference vs the rich panel title `Todos`. If you prefer matching capitalization, switch to `Todos` in both.
- Cancelled-with-strike is a rich-only flourish; plain mode shows `[-]` only.
- The dispatcher is internal; no environment variable or flag will toggle it.
- Implementation language remains Python; no rewrite.
