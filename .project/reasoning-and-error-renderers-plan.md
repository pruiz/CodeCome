# Reasoning and Error Event Renderers Plan

## Goal

Make the wrapper produce visible "thinking" and "error" panels for every
model that has reasoning or that emits session errors, so the verbosity
of in-flight commentary is comparable across providers.

Today the wrapper:

- Drops `reasoning` events into `render_unknown` (printed as
  `unknown event type: reasoning`).
- Drops `error` events into `render_unknown` (same flat fallback).
- Passes `--thinking` to the child only when the user opts in via
  `CODECOME_THINKING=1`. Default is OFF.

This makes Claude phases look much chattier than gpt-5 / Copilot
phases, because Claude emits multiple finalized `text` blocks per turn
(interleaved thinking is on by default in OpenCode for Anthropic) while
OpenAI / Copilot / Gemini emit only a single short final `text` block
and stash the rest of the model's working in a separate `reasoning`
block that the wrapper currently has no way to surface.

## Why this matters

Vulnerability research benefits from seeing the model's reasoning
between tool calls. The wrapper exists to make phases legible. Hiding
reasoning for half the providers is the wrong default for this
workflow. Confirmed by transcript inspection:

- A recent `make phase-1` on `github-copilot/gpt-5.4` produced 11
  `step_start`, 53 `tool_use`, 10 `step_finish`, and zero `text`
  events.
- The same phase on Claude produces several finalized `text` events
  per turn, so it shows multiple "Assistant" panels by default.

The asymmetry is purely a side effect of provider conventions, not of
work done.

## What OpenCode actually emits

Confirmed against
`anomalyco/opencode/packages/opencode/src/cli/cmd/run.ts`:

The JSON event stream currently contains:

- `step_start`
- `step_finish`
- `tool_use`
- `text` — assistant message parts, only when `part.time?.end` is
  set (finalized, not streamed in chunks).
- `reasoning` — only when `--thinking` is passed AND
  `part.time?.end` is set.
- `error` — emitted on `session.error` events.

Other internal events (`message.updated`, `message.part.updated`,
`session.status`, `permission.asked`, ...) are not surfaced as
top-level JSON event types in `--format json`; they drive the events
above.

## Provider behavior summary

Confirmed via OpenCode source and provider docs:

- **Anthropic (Claude)**: OpenCode passes
  `anthropic-beta: interleaved-thinking-2025-05-14` by default.
  Thinking is interleaved with text in the assistant message; both
  arrive as multiple finalized `text` blocks (and `reasoning` blocks
  when `--thinking` is on). With `--thinking` off you already see
  multiple `Assistant` panels per phase.
- **OpenAI / xAI / GitHub Copilot (gpt-5+)**: reasoning is in a
  separate block. Without `--thinking` we see one or zero `text`
  events per turn. With `--thinking` we get `reasoning` events
  interleaved with tool calls.
- **Google Gemini (2.5 / 3.x)**: supports `thinkingConfig`. By
  default the API returns only the final text. Thinking summaries are
  opt-in. Same shape as gpt-5 from the wrapper's point of view —
  needs `--thinking` to surface anything during the turn.
- **Other providers**: unknown by default. The safest assumption is
  "may have hidden reasoning" — surface it if the user has not
  pinned the variable.

## Decisions (per user)

1. **Per-provider default for `--thinking`.**
   - `anthropic/*`: default OFF. Claude already shows interleaved
     thinking via `text` blocks, so adding `reasoning` events on top
     would double the panel count for no extra information.
   - `github-copilot/*`, `openai/*`, `xai/*`, `groq/*`,
     `cerebras/*`: default ON. These providers hide reasoning
     unless `--thinking` is passed.
   - `google/*`, `google-vertex/*`: default ON. Gemini follows the
     gpt-5 convention.
   - Anything else (unknown / future provider): default ON. Cheaper
     to over-surface than to under-surface for this workflow.
   - User override: `CODECOME_THINKING={0,1}` always wins over the
     per-provider default. `0` and `false`/`False`/`no` disable;
     `1` and any other non-empty string enable.
   - `--thinking` already present in `OPENCODE_ARGS` is respected
     and not duplicated.
2. **Reasoning panel title**: `Thinking`.
3. **Reasoning border color**: `dim blue` (visually subordinate to
   the regular `Assistant` panel which is `blue`).
4. **Error panel**: render with a clear-alarm color (`yellow` border,
   bold red icon prefix). Keep it distinct from tool failures (which
   already render red) and from `Thinking` (which is dim blue).

## Renderer design

### 1. `render_reasoning(console, event)`

- Title: `Thinking`.
- Border: `blue` (rich uses `dim` styling on the body text via
  `Markdown`/`Text` style; the `border_style` itself stays `"blue"`
  but with `expand=True`).
- Body: `Markdown(text)` for rich, plain text for plain.
- Truncate body content via `_REASONING_MAX_CHARS` env tunable
  (default `4000`). Append `... (N chars truncated)` footer when
  cut.
- Skip empty / whitespace-only reasoning (parity with OpenCode's
  own behavior in `run.ts`).
- Suppress entire panel when `_THINKING_RENDER` is disabled (paired
  with `--thinking` upstream control).

### 2. `render_error(console, event)`

- Title: `Error`.
- Border: `yellow` (alarm-but-not-fatal).
- Body: red error message text in rich; in plain mode use
  `C.fail(...)` for the message and a yellow header.
- Always rendered. Even when `--thinking` is off these are signal,
  not noise.

### 3. Dispatch in `render_event`

Extend the elif chain:

```python
elif event_type == "reasoning":
    render_reasoning(console, event)
elif event_type == "error":
    render_error(console, event)
```

### 4. Per-provider `--thinking` decision

New helper:

```python
def _thinking_default_for_provider(provider_id: str) -> bool:
    """Return True if --thinking should be ON by default for this provider."""
    # Anthropic interleaves thinking into normal text blocks already.
    if provider_id.startswith("anthropic"):
        return False
    # All other known reasoning-capable providers hide it without --thinking.
    # Default ON for everything else; opt-out via CODECOME_THINKING=0.
    return True
```

In `build_child_command()`:

- Read `CODECOME_THINKING`. If explicitly set to one of `0` /
  `false` / `False` / `no` -> disable. If set to anything else
  non-empty -> enable.
- If unset, derive from the resolved `model` provider prefix using
  `_thinking_default_for_provider()`.
- Append `--thinking` to the child command unless it is already
  present in `OPENCODE_ARGS`-derived `extra_args`.
- Track the resolved decision (`on` / `off`) and the source
  (`env` / `provider-default` / `user-args`) for the banner.

### 5. Banner update

Append a small chip after the model line, e.g.:

```
[phase-1] recon · github-copilot/gpt-5.4 · thinking=on (provider-default)
```

When off:

```
[phase-1] recon · anthropic/claude-opus-4-7 · thinking=off (provider-default)
```

When user-controlled:

```
... · thinking=off (env)
```

### 6. Tunables

- `CODECOME_THINKING={1,0}` — explicit override. Default unset
  (per-provider).
- `CODECOME_REASONING_MAX_CHARS` — default `4000`. Truncate
  individual reasoning blocks longer than this.
- `CODECOME_RENDER_REASONING={1,0}` — escape hatch to render or
  suppress reasoning panels even when `--thinking` was passed.
  Default `1`. (Use case: someone wants `--thinking` on for the
  upstream JSON transcript but keep the on-screen output clean.)

## Edge cases

1. **Models that don't support reasoning.** OpenCode silently skips
   emitting `reasoning` events even with `--thinking`. Net change:
   zero.
2. **`--thinking` already in `OPENCODE_ARGS`.** Don't double-add.
   Treat as user-pinned and report `thinking=on (user-args)`.
3. **Provider not detected (probe failed).** Default ON. Aligns with
   "for unknown models, default to ON" guidance.
4. **Very long reasoning blocks.** Truncate per
   `_REASONING_MAX_CHARS` with explicit footer, mirroring the
   read renderer's pattern.
5. **Reasoning + final answer in same turn.** Both events fire as
   normal; both panels appear in stream order. No special handling.
6. **`error` event with no error string.** Render an empty-body
   panel with the title `Error` and a `(no error message)` body so
   the user still sees something happened.
7. **Cost.** Some providers bill reasoning tokens. The opt-out via
   `CODECOME_THINKING=0` is the user's escape hatch; we document
   the cost note in the README.

## Testing

1. `make phase-1` on `claude/...` model. Confirm `Assistant`
   panels still appear and *no* extra `Thinking` panels are added
   (anthropic default off).
2. `make phase-1` on `github-copilot/gpt-5.4`. Confirm
   `Thinking` panels now appear interleaved with tool calls.
3. `make phase-1` on `google/gemini-3-pro-preview`. Confirm
   `Thinking` panels appear (per-provider default on).
4. Set `CODECOME_THINKING=0` against a copilot model. Confirm no
   `Thinking` panels and `--thinking` is *not* passed to child;
   transcript file in `tmp/` should not contain `reasoning`
   events.
5. Set `CODECOME_THINKING=1` against `claude/...`. Confirm
   `Thinking` panels do appear (override wins).
6. Set `CODECOME_REASONING_MAX_CHARS=200`. Confirm truncation
   footer.
7. Synthesize a session error in the transcript and confirm the
   `Error` panel renders yellow with a red message body.
8. `CODECOME_USE_WRAPPER=0` -> raw mode unaffected (only wrapper
   changes).
9. `--color never` and `NO_COLOR=1` -> plain reasoning and error
   panels render with a clear header line.

## Code changes (files affected)

- `tools/run-agent.py`
  - Add `render_reasoning(console, event)` near `render_text`.
  - Add `render_error(console, event)` near `render_step_finish`.
  - Extend `render_event` dispatch with both new event types.
  - Add `_thinking_default_for_provider(provider_id)`.
  - In `build_child_command()`:
    - Replace the existing `if truthy_env("CODECOME_THINKING")`
      block with the per-provider logic above.
    - Add dedup vs `OPENCODE_ARGS`.
    - Track resolution source for the banner.
  - Add `_REASONING_MAX_CHARS` and `_RENDER_REASONING` env
    tunables.
  - Pass thinking decision through to the banner printer.
- `README.md`
  - Document `CODECOME_THINKING` per-provider default and the new
    `CODECOME_REASONING_MAX_CHARS` and `CODECOME_RENDER_REASONING`
    knobs.
  - Note the cost implication for reasoning-billing providers.

## Out of scope

- Streaming partial reasoning/text deltas. OpenCode emits only
  finalized parts in `--format json`.
- Provider-specific reasoning effort (`--variant high` / Gemini
  `thinkingConfig.thinkingBudget` / OpenAI `reasoning.effort`).
  These remain in `codecome.yml` / env / `OPENCODE_ARGS`.
- Cost-per-reasoning-token reporting.
- A dedicated `task` sub-agent renderer (still deferred from the
  earlier tool-renderers plan).

## Implementation checklist

- [ ] Add `render_reasoning(console, event)`.
- [ ] Add `render_error(console, event)`.
- [ ] Wire both into `render_event`.
- [ ] Add `_thinking_default_for_provider(provider_id)`.
- [ ] Update `build_child_command()` to resolve thinking with
      `env > user-args > per-provider default`.
- [ ] Dedup `--thinking` against `OPENCODE_ARGS`.
- [ ] Banner shows `thinking=on/off (source)`.
- [ ] Add `_REASONING_MAX_CHARS` (4000) and `_RENDER_REASONING`
      (1) env tunables.
- [ ] Update README.
- [ ] Verify with synthetic JSONL fixtures (claude / copilot /
      gemini / unknown).

## License

CodeCome is dual-licensed under your choice of:

- GNU General Public License version 3 or later
  (`GPL-3.0-or-later`), or
- GNU Affero General Public License version 3 or later
  (`AGPL-3.0-or-later`).

SPDX expression: `GPL-3.0-or-later OR AGPL-3.0-or-later`.

Copyright (C) 2025-2026 Pablo Ruiz García &lt;pablo.ruiz@gmail.com&gt;.
