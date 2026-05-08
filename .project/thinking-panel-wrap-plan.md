## Goal

Fix Rich `Thinking` panel clipping in `tools/run-agent.py` so long reasoning
text wraps inside the panel instead of being visually cut at the right border.

## Constraints

- Preserve markdown rendering in reasoning when feasible.
- Use a regression test first so the failure is reproducible.
- Try markdown-preserving fixes before falling back to plain text.

## Suspected root cause

- `render_reasoning()` renders `Panel(Markdown(text), ...)`.
- `build_console()` constructs the global Rich console with
  `soft_wrap=True`.
- That combination likely causes some markdown-rendered lines to clip at panel
  width instead of folding.

## Plan

1. Add a Rich-mode regression test in `tests/test_run_agent.py` using a narrow
   `Console(record=True, width=60, force_terminal=True)`.
2. Feed `render_reasoning()` a long markdown-ish reasoning string.
3. Assert the rendered output includes continuation text that would otherwise
   be lost to clipping.
4. First implementation attempt: remove global `soft_wrap=True` from
   `build_console()` and keep `Markdown(text)` in `render_reasoning()`.
5. If needed, second implementation attempt: keep markdown but wrap it in a
   container that behaves better inside `Panel`, e.g. `Group(Markdown(text))`.
6. Run `make tests` after implementation.

## Non-goals

- Do not convert reasoning to plain text unless markdown-preserving attempts
  fail.
- Do not broadly restyle other panels unless required by the fix.
