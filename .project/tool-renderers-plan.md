# Plan: Pretty Renderers for Common Tool Calls in `tools/run-agent.py`

## Status

v2.1 — final locked spec. Supersedes v2.0 draft.

## Goal

Extend the per-tool renderer dispatcher (already in place for `todowrite`) to handle
the other tools that show up frequently in real `make phase-*` runs with readable,
truncation-aware, syntax-highlighted output.

Tool usage observed in a real Phase 1 run on `src/sample-c-cli/`:

| Tool | Calls | Priority |
|---|---|---|
| `read` | 19 | Critical — dominates output volume |
| `write` | 9 | High |
| `todowrite` | 3 | Done in v1 |
| `glob` | 2 | Medium |
| `bash` | 1 | High |
| `skill` | 1 | Low |
| `edit` | common in phase 3/4 | High — now included |

## Unified display model (v2.1)

**One display cap per tool, measured in lines. Source-file size is irrelevant.**
Caps are pure display limits; the decision to truncate is based solely on how
many rendered lines the output would produce, not on the file's actual size.

**Truncation order is mandatory across all tools that support it:**

1. Render up to N highlighted body lines.
2. Dim `... <K> more lines` if truncated.
3. Dim trailing summary line if present (e.g. `(End of file - total 48 lines)`,
   `(Showing lines 1-50 of 146. Use offset=51 to continue.)`,
   `Wrote file successfully.`).

The "more lines" marker always sits between the truncated body and the summary.

Highlighting always applies to the visible portion only, so Pygments cost is bounded.

## Tunables (final)

| Knob | Default | Env var | CLI flag | Notes |
|---|---|---|---|---|
| Read display cap | 10 | `CODECOME_READ_DISPLAY_LINES` | `--read-display-lines` | Pure display cap |
| Write content cap (no baseline) | 25 | `CODECOME_WRITE_CONTENT_LINES` | `--write-content-lines` | Pure display cap |
| Write diff cap (with baseline) | 50 | `CODECOME_WRITE_DIFF_LIMIT` | `--write-diff-limit` | Pure display cap; name kept for compat |
| Edit diff cap | 25 | `CODECOME_EDIT_DIFF_LINES` | `--edit-diff-lines` | Pure display cap |
| Read highlight size cap | 200 KB | `CODECOME_READ_HIGHLIGHT_LIMIT` | none | Plain monospace beyond |
| Glob match cap | 10 | `CODECOME_GLOB_MATCH_CAP` | none | `... and N more` after |
| Snapshot cache size | 200 | `CODECOME_WRITE_CACHE_CAP` | none | LRU path count |
| Snapshot cache enabled | on | `CODECOME_WRITE_CACHE` | none | `=0` to disable |

Removed from earlier drafts (no longer exist):

- `_WRITE_FULL_LINES` — replaced by `_WRITE_CONTENT_LINES`
- `_WRITE_FULL_BYTES` — no byte threshold; lines are the sole measure
- `_EXCERPT_LINES` — its per-tool replacements are the four caps above

CLI flags override env vars. Env vars override defaults.

## Per-tool render specs

### `read`

Detection: `tool == "read"`, `state.input.filePath` and `state.output` present.

Framing parser `_strip_read_framing(output)` returns a 3-tuple:
- `("file", body: str, summary: str | None)` where body has line-number prefixes
  stripped and summary is the trailing `(End of file...)` or `(Showing lines...)`
  line if present
- `("directory", entries: list[str], footer: str)` where entries is the cleaned
  list of entry names and footer is the original `(N entries)` or `(N entries)`
  count text
- `(None, None, None)` when framing is unrecognised → fall through to generic

Rich layout (file):
- title `Read`, border green on completed / red on error
- bold cyan relative path
- if `offset`/`limit` present: dim `lines <offset>..<offset+limit-1>`
- blank line
- syntax-highlighted body, capped at `_READ_DISPLAY_LINES` (default 10)
- if truncated: dim `... <K> more lines`
- if summary present: dim summary line

Rich layout (directory):
- title `Read`, border green
- bold cyan relative path
- blank line
- entry list, directories (ending in `/`) styled bold blue, files plain
- dim `<N> entries` footer

Plain layout: parallel structure, no Syntax block.

Snapshot cache: the full unparsed body (not the truncated display) is cached for
later diff baselines.

Edge cases:
- empty file: `(empty file)` dim, no cap applied
- file > `_READ_HIGHLIGHT_LIMIT` (200 KB): plain monospace, cap still applies
- error in output: red text, no Syntax block

### `write`

Decision tree:

1. Error in output → render error in red, skip body, update cache.
2. `_cache_get(path)` returns content → diff path.
3. Otherwise → content path.

Diff path:
- compute unified diff with 3 context lines
- if zero diff lines: dim `(no changes)`, then status line
- else: dim `diff: -<del> +<add>`, blank, Syntax diff block capped at
  `_WRITE_DIFF_LINES` (50), `... <K> more lines` if truncated, status line

Content path (no baseline):
- dim `(new file)`, blank
- syntax-highlighted body of `state.input.content`, capped at `_WRITE_CONTENT_LINES` (25)
- `... <K> more lines` if truncated
- status line

Cache update: always update snapshot cache with new content + post-write mtime
after rendering, regardless of path taken.

### `glob`

Unchanged from v2.0.

### `bash`

Unchanged from v2.0.

### `skill`

Unchanged from v2.0.

### `edit` (new in v2.1)

Detection: `tool == "edit"`, `state.input.filePath`, `state.input.oldString`,
`state.input.newString`.

Rich layout:
- title `Edit`, border green on completed / red on error
- bold cyan relative path
- dim metadata: `replace 1 occurrence` or `replace all` based on `state.input.replaceAll`
- blank line
- unified diff from `oldString` to `newString` with 3 context lines
- syntax-highlighted with `diff` lexer, capped at `_EDIT_DIFF_LINES` (25)
- if truncated: dim `... <K> more lines`
- success/error status line

Plain layout: parallel.

Snapshot cache behavior after an `edit`:
- if baseline exists for `filePath`: drop the cache entry, then re-read the file
  from disk (`Path(filePath).read_text`) and store the fresh content + current
  mtime via `_cache_set`. This is the only way to get a correct baseline for any
  subsequent `write` diff.
- if no baseline existed: skip.
- if re-read fails (file deleted, permission denied, etc.): drop the cache entry
  silently.

Edge cases:
- missing `oldString` or `newString`: fall through to generic renderer
- error output: render red status line, still show the attempted diff
- `replaceAll` absent or not bool: treat as False

## Shared truncation helper

A single `_render_truncated_body` helper enforces the mandatory order:

```python
def _render_truncated_body(
    body: str,
    cap: int,
    lexer: str,
    summary: str | None,
    *,
    console: Console | None,  # None = plain mode
) -> ...:
    # 1. Render lines[:cap] through Syntax (or plain print)
    # 2. If truncated: "... K more lines" dim
    # 3. If summary: dim summary line
```

This guarantees ordering is correct everywhere. All four rendering tools
(`read`, `write`, `edit`) call this helper rather than inline their own
truncation.

## Tool dispatch table

```python
TOOL_RENDERERS = {
    "todowrite": render_todowrite,
    "read":      render_read,
    "write":     render_write,
    "edit":      render_edit,
    "glob":      render_glob,
    "bash":      render_bash,
    "skill":     render_skill,
}
```

Tool-name normalization at dispatch: `tool = part.get("tool", "").strip().lower()`.
Cache invalidation (`_cache_invalidate_stale`) is called for all non-write
non-edit events so that external mutations are detected before any diff.

## Validation plan

After implementation:

1. `make phase-1` — confirm:
   - `read` panels show ≤ 10 content lines + `... K more` + summary
   - directory reads render entry list with `<N> entries` footer, no XML tags
   - `write` new-file panels show ≤ 25 lines + `... K more` + `Wrote file successfully.`
   - `write` diff panels show ≤ 50 diff lines
   - `glob`, `bash`, `skill` unchanged
   - `todowrite` unchanged
2. `make phase-3` or `make phase-4` to exercise `edit` tool in real conditions.
3. `NO_COLOR=1 make phase-1` — plain mode, no ANSI for any renderer.
4. `--debug` — raw JSON still mirrored to stderr.
5. Confirm truncation order: body → `... K more lines` → summary line.
6. Confirm directory reads no longer emit raw `<entries>` XML.
7. Confirm `CODECOME_READ_DISPLAY_LINES=3` shortens read display to 3 lines.

## Risks

1. `_strip_read_framing` directory regex must not match the entries summary line
   as a regular entry. Mitigation: strip it separately and return it as the
   footer argument.
2. Re-reading the file post-edit adds an extra filesystem call per edit event.
   Mitigation: only triggered when a baseline existed; rare in practice.
3. Rich `Syntax` with `diff` lexer works best on unified-diff format. Malformed
   diff output (e.g. from empty oldString) renders as plain text gracefully.

## Acceptance criteria

- All five tools render via dedicated panels in real `make phase-*` runs.
- `read` truncates to 10 lines, shows summary, handles directories cleanly.
- `write` truncates content/diff to caps, shows status, produces real diffs.
- `edit` renders a unified diff, truncated, with accurate cache invalidation.
- Truncation order is always: body → `... K more` → summary.
- No raw XML framing visible in directory reads.
- Plain mode and NO_COLOR work for every renderer.
- `--debug` unaffected.
- No new package dependency.

## Out-of-scope (deferred)

- `task` sub-agent renderer
- Replay harness for offline testing
- User-configurable theming

## Done (previously deferred)

- `apply_patch` renderer — implemented in `.project/apply-patch-renderer-plan.md`
- `grep` renderer — file-list and line-level modes with per-file grouping and truncation
