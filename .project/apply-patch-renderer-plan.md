# Apply-patch Renderer Plan

## Goal

Render `apply_patch` tool calls in the wrapper as cleanly as we already
render `edit` and `write`, so users on models that emit `apply_patch`
instead of `edit` / `write` see meaningful per-file diffs rather than
a raw JSON blob.

## Why this matters

`tools/run-agent.py` `_dispatch_tool_renderer` (around line 1399) only
special-cases `todowrite`, `read`, `write`, `edit`, `glob`, `bash`,
`skill`. `apply_patch` falls through to the generic branch in
`render_tool_use` (around line 1467), which dumps `input` / `output`
as `rich.JSON` or `json.dumps`.

For `apply_patch` the input is a long multi-file patch string. JSON
dumping it produces one hard-to-read line full of escaped newlines, and
the panel title shows only `Tool: apply_patch [completed]` with no
per-file information.

Worse, the same agent on a different model (Claude / OpenAI tool-use
mode) would have used `edit` and gotten the nice unified-diff panel.
The wrapper's quality of output therefore varies purely with model
choice. That is what the user reported.

This was already noted as out-of-scope in
`.project/tool-renderers-plan.md:253`. This plan closes that gap.

## What `apply_patch` actually looks like

Two common shapes show up in the wild:

1. The `*** Begin Patch / *** Update File / *** End Patch` envelope
   (used by Claude Code-style tooling, OpenAI Codex agents, etc.). In
   this case the entire patch is a single string in `input.patch` (or
   sometimes `input.input`).
2. Variants where `input` is `{"patch": "..."}` or
   `{"patches": [{"path": "...", "diff": "..."}, ...]}`.

The renderer must be tolerant of both and degrade gracefully when it
cannot parse either. The output side is usually a short status string
(e.g. `Updated the following files: ...`) or an error diagnostic.

## Renderer design

New module-level helpers in `tools/run-agent.py`:

1. `_extract_apply_patch_payload(state) -> tuple[str, list[ParsedFilePatch], str]`

   Returns `(raw_patch_text, parsed_per_file_patches, output_str)`.

   `ParsedFilePatch` carries:

   - `op`: `"add" | "update" | "delete" | "rename" | "unknown"`
   - `path`: target path, relativized to `ROOT` when possible
   - `old_path`: only for renames
   - `hunks`: list of unified-diff-ready strings (already in
     `--- old / +++ new / @@ ... @@` form, or synthesized for adds /
     deletes)
   - `added`, `removed`: line counts

   Recognizes the `*** Begin Patch / *** Update File / *** End Patch`
   envelope and falls back gracefully if the input is just a raw
   unified diff or a `{patches: [...]}` list.

2. `render_apply_patch_rich(console, state) -> bool`

   - Title: `Apply patch`.
   - Header rows:
     - one summary line: `N file(s) changed: +A -B`
     - per-file row: `<op>  <path>  +adds -removes` styled like
       `edit`
   - Body for each file:
     - render the file's hunks via
       `rich.syntax.Syntax(..., "diff", ...)` reusing
       `_truncate_diff` and `_EDIT_DIFF_LINES` (already used for
       `edit`)
     - same `... K more lines` truncation footer
   - Trailing status block:
     - rendered like `edit`: green status text on success, red on
       failure (use `_is_likely_error`)
   - Border color:
     - `green` on success
     - `red` if `output` indicates failure
     - `yellow` if status is not yet `completed`
   - Cache integration:
     - On success, invalidate cached snapshots for every touched path
       with `_cache_reread(path)`, identical to what
       `render_edit_rich` does today, so subsequent `read` / `write`
       after `apply_patch` see fresh content.
   - Returns `True` if it handled the event, `False` if the input
     could not be parsed at all (so the generic JSON renderer can
     still take over instead of crashing).

3. `render_apply_patch_plain(state) -> bool`

   Plain ASCII version mirroring the rich renderer. Reuses
   `_render_truncated_body_plain` patterns and the existing
   `C.header` / `C.info` / `C.fail` / `C.ok` helpers, in the same
   style as `render_edit_plain`.

4. Dispatch wiring in `_dispatch_tool_renderer`:

   - Add
     `elif tool_lower in {"apply_patch", "applypatch", "apply-patch"}: ...`
   - Place it next to the `edit` branch since it shares cache
     semantics.

5. Tunables (env-driven, mirroring existing knobs):

   - `CODECOME_APPLY_PATCH_DIFF_LINES` (default falls back to
     `_EDIT_DIFF_LINES`)
   - `CODECOME_APPLY_PATCH_MAX_FILES` (default 10) — when more, render
     the first `N` and append `... and K more file(s)`.

## Parser scope

We do not want to write a fully general patch parser. The minimum:

- Split the input on
  `^*** (Begin Patch|End Patch|Update File:|Add File:|Delete File:|Rename File:|Move File:) `
  boundaries.
- For each file block:
  - capture `op` and path(s)
  - everything between the file header and the next `*** ` line is
    the body
  - count `+` and `-` lines (excluding `+++` / `---`)
  - synthesize a real `--- old\n+++ new` header for the rich
    `Syntax("diff", ...)` block so colors are consistent with the
    `edit` renderer.

Fallbacks:

- If the input is already a raw unified diff (starts with `--- ` or
  `diff --git`), treat the whole input as one synthetic file with
  `op = "unknown"` and pass through.
- If the input is `{patches: [...]}` style, iterate that list
  directly.
- If parsing fails entirely, fall back to a generic panel that:
  - shows a short header, the byte / line size of the patch
  - dumps the raw patch text in a `Syntax(..., "diff", ...)` block,
    capped by `_WRITE_DIFF_LIMIT`

This is still vastly better than the current JSON dump.

## Output / error handling

- If `output` text starts with something like
  `Updated the following files:`, surface it verbatim as the green
  status line.
- If `_is_likely_error(output)` is true, color red and bypass cache
  invalidation (we don't want to re-read possibly-half-written files).
- If `output` is absent (in-flight tool call), use border `yellow`
  and do not invalidate cache yet.

## Testing approach

Since this is a renderer, testing is fastest via captured-event
fixtures, like the existing renderers were validated. Concrete manual
tests after implementation:

1. Run `make phase-1` (or any phase) on a model that uses
   `apply_patch` and verify:
   - each file change shows op + path + adds / removes summary
   - diffs are colorized via `rich`
   - truncation works with very large patches (more than 50 changed
     lines)
2. Force a deliberate error (malformed patch) and verify the red
   error path.
3. Run again with `CODECOME_USE_WRAPPER=0` to confirm raw mode is
   unaffected.
4. Run with `--color never` and `NO_COLOR=1` to verify the plain
   renderer.

## Documentation updates

- `.project/tool-renderers-plan.md` line 253 — remove `apply_patch
  renderer` from the deferred list, or move it into a new "Done"
  section.
- `README.md` wrapper section — add `apply_patch` to the list of
  pretty-rendered tools (currently only `read`, `write`, `edit`,
  `glob`, `bash`, `todowrite`, `skill` are mentioned implicitly).

## Open questions to confirm before implementing

1. **Patch envelope coverage.** Are we only seeing the
   `*** Begin Patch / *** Update File / *** End Patch` envelope, or
   are some models emitting raw unified diffs? If only the former, we
   keep the parser narrow and treat the rest as fallback only.
2. **Per-file truncation policy.** Two reasonable choices:
   - (a) Show every file fully up to
     `CODECOME_APPLY_PATCH_DIFF_LINES` per file (matches `edit`
     behavior; can produce a long panel)
   - (b) Show first `N` files fully, then
     `... and K more file(s)` (compact)

   Default (a) and add (b) only if a single patch ever exceeds
   `CODECOME_APPLY_PATCH_MAX_FILES`.
3. **Cache invalidation.** Should `apply_patch` trigger the same
   `_cache_reread` for each touched file as `edit` does today?
   Recommended: **yes**. `apply_patch` is functionally an
   `edit` / `write` for cache-tracking purposes.
4. **Plain (non-rich) mode parity.** Worth doing now, or are we only
   worried about the rich path? Recommended: **do both at once**,
   since plain mode is roughly 30 lines of code once the parser
   exists.

## Out-of-scope (deferred)

- A full `task` sub-agent renderer.
- A replay harness for offline testing.
- User-configurable theming.
- Cross-tool deduplication of cache-invalidation logic (currently
  duplicated between `edit` / `write` / future `apply_patch`).

## Implementation checklist

- [ ] Add `_extract_apply_patch_payload` helper.
- [ ] Add `ParsedFilePatch` dataclass / dict shape.
- [ ] Add `render_apply_patch_rich`.
- [ ] Add `render_apply_patch_plain`.
- [ ] Wire dispatch in `_dispatch_tool_renderer`.
- [ ] Add env tunables `CODECOME_APPLY_PATCH_DIFF_LINES` and
      `CODECOME_APPLY_PATCH_MAX_FILES`.
- [ ] Manual end-to-end test on a phase that emits `apply_patch`.
- [ ] Manual error-path test with a malformed patch.
- [ ] Update `.project/tool-renderers-plan.md` to mark the renderer as
      done.
- [ ] Update `README.md` wrapper section to mention pretty
      `apply_patch` rendering.

## License

CodeCome is dual-licensed under your choice of:

- GNU General Public License version 3 or later (`GPL-3.0-or-later`),
  or
- GNU Affero General Public License version 3 or later
  (`AGPL-3.0-or-later`).

SPDX expression: `GPL-3.0-or-later OR AGPL-3.0-or-later`.

Copyright (C) 2025-2026 Pablo Ruiz García &lt;pablo.ruiz@gmail.com&gt;.
