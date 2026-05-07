# Plan: Pretty Renderers for Common Tool Calls in `tools/run-agent.py`

## Goal

Extend the per-tool renderer dispatcher (already in place for `todowrite`) to handle the other tools that show up frequently in real `make phase-*` runs. The current generic JSON dump is noisy and visually overwhelming, especially for `read` (which dominates every phase) and `write` (which floods the screen with full file content).

This plan is grounded in actual observed tool usage from a real Phase 1 run on `src/sample-c-cli/`:

| Tool | Calls observed in one Phase 1 run | Priority for pretty rendering |
|---|---|---|
| `read` | 19 | **Critical** — dominates output volume |
| `write` | 9 | High — large content payloads, will use real diff |
| `todowrite` | 3 | Done in v1 |
| `glob` | 2 | Medium |
| `bash` | 1 | High — security-relevant |
| `skill` | 1 | Low — small payloads |

## Locked decisions

1. **v2 scope**: `read`, `write`, `glob`, `bash`, `skill`. `apply_patch` and `edit` stay on the generic fallback for now.
2. **`write`**: show a real **diff** between the previously-known content (snapshot cache) and the new content. Truncate when over a configurable line limit. Default 50 lines.
3. **Excerpt size for fallback paths**: 5 lines. Tunable.
4. **Small-file full-content threshold for `write` (when no baseline exists)**: ≤ 25 lines AND ≤ 1 KB.
5. **`read` content**: syntax-highlighted via Rich `Syntax` (Pygments).
6. **`bash` exit code**: omitted, OpenCode does not expose it.
7. **Panel titles for v2 tools**: short and clean (`Read`, `Write`, `Glob`, `Bash`, `Skill`). Generic fallback retains `Tool: <name> [<status>]`.
8. **Diff context lines**: 3 lines (`difflib.unified_diff(..., n=3)`).
9. **Snapshot cache size**: 200 paths LRU. Tunable.
10. **Cache invalidation**: mtime-based. See "Snapshot cache and mtime invalidation" below.

## Real payload shapes (observed in spike)

### `read`

Input: `{ "filePath": "<abs path>" }` (optional `offset`, `limit`).

Output (file): wrapped in `<path>...</path><type>file</type><content>...</content>`.

Output (directory): flat list of entries, no framing tags.

Truncation: OpenCode appends `(line truncated to 2000 chars)` at the end of long lines.

### `write`

Input: `{ "filePath": "<abs path>", "content": "<full new body>" }`.

Output: `Wrote file successfully.` on success, otherwise an error string.

### `glob`

Input: `{ "pattern": "**/*", "path": "<abs dir>" }`.

Output: newline-separated absolute paths.

### `bash`

Input: `{ "command": "<shell command>", "description": "<optional>" }`.

Output: combined stdout/stderr.

### `skill`

Input: `{ "name": "<skill-name>" }`.

Output: small or empty.

### `todowrite` (already done)

Skipped here.

## Design principles (carried forward from todowrite plan)

- **Defensive shape detection**: each renderer inspects expected fields; if anything looks off, it returns `False` and the dispatcher falls back to the generic JSON renderer. Never crash.
- **No new dependencies**. Pygments is already a transitive dep via `rich`.
- **Plain-mode parity**: every tool renderer also has a `_plain` path for the no-rich fallback.
- **`--debug` unchanged**: raw JSON still mirrored to stderr.
- **Reuse existing color helpers**: `tools/_colors.py` constants and Rich style strings; no new palette.
- **Single file change**: all logic in `tools/run-agent.py`.

## Snapshot cache and mtime invalidation

The wrapper maintains a process-local cache mapping file path → `(content, mtime)`.

Population:

- On a `read` event for a file (not directory), parse the framed content and cache it with the current `os.stat(path).st_mtime`.
- After rendering a `write` event, update the cache for the written path with the new content and the current mtime (which is now the post-write mtime).

Invalidation:

- Before rendering each **non-write** event (`read`, `bash`, `glob`, `skill`, generic, `todowrite`), iterate cache entries and `os.stat` each path. Drop any entry whose current mtime differs from its recorded mtime, and any entry whose path no longer exists.
- For `read` events, this happens implicitly: if the path was cached and mtime changed since, the entry is dropped, and the new content from the read replaces it.

Diff handling:

- For `write` events, look up the path in the cache **before** updating. The cached entry is the baseline. After the write event has been rendered, replace the cache entry with the new content and the post-write mtime.
- If no cache entry exists, treat as a new file.

Why this works:

- A `read` followed later by a `write` in the same session produces a real diff against the read baseline.
- Two `write` calls in a row produce a diff against the previous write.
- A `bash` (or anything else) that modifies a file between events bumps mtime; the next non-write event drops the stale entry, and the subsequent `write` falls back to "new file" rendering rather than an inaccurate diff.
- A `read` that follows external modification re-caches the fresh content with the new mtime.

Known limitations:

- Same-second rewrites on coarse-mtime filesystems may be missed. macOS APFS uses nanosecond resolution; not a concern in practice.
- Same-content rewrites by `bash` would still bump mtime and invalidate the cache, producing "new file" rendering on the next `write` instead of "no changes". Acceptable cost.
- The cache is process-local; restarting the wrapper resets it. Acceptable.

Kill switch:

- `CODECOME_WRITE_CACHE=0` disables caching entirely. All `write` events render as "new file" with size-based full-content or excerpt path. Useful for debugging.

## Per-tool render specs

### `read`

Rich layout:

- Panel title: `Read`
- Border color: green if `status == completed`, red if output indicates error, yellow otherwise
- Body:
  - bold cyan path (relative to repo root when possible, absolute otherwise)
  - if `offset`/`limit` present: dim line `lines <offset>..<offset+limit-1>`
  - blank line
  - directory listing → list of entries (directories ending in `/` styled bold blue)
  - file content → strip OpenCode framing, pass to Rich `Syntax` with auto-detected lexer
  - truncation marker `(line truncated to 2000 chars)` preserved as dim text at end

Plain layout:

```
read <path>
  lines 1..50
  <stripped content with line numbers preserved>
```

Edge cases:

- file content > `CODECOME_READ_HIGHLIGHT_LIMIT` bytes (default 200 KB): skip Syntax, render plain monospace
- binary content: render `(binary file, content suppressed)` dim
- empty file: render `(empty file)` dim
- error in output: render in red without Syntax

### `write`

Decision tree at render time:

1. If output indicates an error: render error in red, do not render content or diff.
2. Look up `filePath` in the snapshot cache.
3. Cache hit:
   - Compute unified diff between cached content and `state.input.content` (3 context lines).
   - If diff is empty: render dim line `(no changes)`.
   - Else: render diff with truncation at `CODECOME_WRITE_DIFF_LIMIT` (default 50 lines). Append `... diff truncated (<K> more lines)` dim if truncated.
4. Cache miss (new file or invalidated):
   - If new content has ≤ `CODECOME_WRITE_FULL_LINES` lines (default 25) AND ≤ `CODECOME_WRITE_FULL_BYTES` bytes (default 1024): render full content as syntax-highlighted block.
   - Else: render first `CODECOME_EXCERPT_LINES` (default 5) lines as a syntax-highlighted excerpt; append `... <K> more lines` dim.
5. Update the snapshot cache with new content and the current mtime of the file.

Rich layout:

- Panel title: `Write`
- Border color: green on success, red on error
- Body:
  - bold cyan path (relative when possible)
  - dim metadata line: `<N> lines, <M> bytes`
  - dim status line: one of:
    - `diff: -<deleted> +<added>`
    - `(no changes)`
    - `(new file)` when cache miss
    - `(content too large for diff)` if either side exceeds 200 KB
  - blank line
  - the diff block, full-content block, or excerpt block per the decision tree
  - blank line
  - status line: `Wrote file successfully.` in green, or the error in red

Plain layout:

```
write <path>
  <N> lines, <M> bytes
  diff: -<del> +<add>
  --- old
  +++ new
  @@ ... @@
   context
  +added
  -removed
   ...
  ... diff truncated (<K> more lines)
  Wrote file successfully.
```

For new-file path:

```
write <path>
  <N> lines, <M> bytes
  (new file)
  <full content if small, else first N lines>
  ... <K> more lines
  Wrote file successfully.
```

Diff coloring (Rich path):

- additions: green
- deletions: red
- hunk headers (`@@ ... @@`): cyan
- context lines: dim
- file headers (`---`, `+++`): dim

Edge cases:

- binary or non-decodable content: render `(binary, <M> bytes)` dim, no diff
- output indicates failure: skip diff, error prominent in red
- missing `filePath`: render `(missing path)` dim, fall back to generic

### `glob`

Rich layout:

- Panel title: `Glob`
- Border color: green if matches found, dim if zero
- Body:
  - dim metadata line: `pattern=<pattern> path=<path>`
  - blank line
  - bulleted list of matches; paths shown relative to input `path` when possible
  - cap: `CODECOME_GLOB_MATCH_CAP` (default 100); overflow shown as `... and <K> more` dim
  - footer dim line: `<N> match(es)`

Plain layout:

```
glob <pattern> in <path>
  src/main.c
  src/greet.c
  ...
  <N> match(es)
```

Edge cases:

- zero matches: render `(no matches)` dim
- output as a single string: split on newlines

### `bash`

Rich layout:

- Panel title: `Bash`
- Border color: green on `completed`, yellow if running, red if output looks error-shaped (heuristic: contains `Error`, `Traceback`, `command not found`, etc.)
- Body:
  - bold cyan label `$ <command>` (full command, may wrap)
  - if `description` present: dim italic line `<description>`
  - blank line
  - section header `Output` styled bold green
  - command output as plain monospace (no syntax highlighting)

Plain layout:

```
bash $ <command>
  # <description>
  <output>
```

Edge cases:

- empty output: `(no output)` dim
- exit code: omitted

### `skill`

Rich layout:

- Panel title: `Skill`
- Border color: dim
- Body: single line `loaded skill: <name>`

Plain layout:

```
skill <name>
```

Edge cases:

- missing `name`: render `(unknown skill)` dim

## Tunable limits and toggles

| Knob | Default | Env var | CLI flag | Notes |
|---|---|---|---|---|
| Excerpt lines | 5 | `CODECOME_EXCERPT_LINES` | `--excerpt-lines` | Used by `write` excerpt path |
| Write diff line limit | 50 | `CODECOME_WRITE_DIFF_LIMIT` | `--write-diff-limit` | Truncates rendered diff |
| Write full-content line threshold | 25 | `CODECOME_WRITE_FULL_LINES` | `--write-full-lines` | New-file full content cutoff (lines) |
| Write full-content byte threshold | 1024 | `CODECOME_WRITE_FULL_BYTES` | `--write-full-bytes` | New-file full content cutoff (bytes) |
| Read content highlight cap | 200 KB | `CODECOME_READ_HIGHLIGHT_LIMIT` | none | Plain monospace beyond this |
| Glob match cap | 100 | `CODECOME_GLOB_MATCH_CAP` | none | `... and N more` after |
| Snapshot cache cap | 200 | `CODECOME_WRITE_CACHE_CAP` | none | LRU cap on cached paths |
| Write cache disabled | off | `CODECOME_WRITE_CACHE=0` | none | Disables diff rendering, all writes appear as new files |

CLI flags override env vars. Env vars override defaults.

## Title format (locked)

| Tool | Rich panel title | Plain mode label |
|---|---|---|
| `todowrite` | `Todos` | `todos` |
| `read` | `Read` | `read` |
| `write` | `Write` | `write` |
| `glob` | `Glob` | `glob` |
| `bash` | `Bash` | `bash` |
| `skill` | `Skill` | `skill` |
| any other | `Tool: <name> [<status>]` | `tool: <name> [<status>]` |

## Tool dispatch

```python
TOOL_RENDERERS = {
    "todowrite": render_todowrite,
    "read": render_read,
    "write": render_write,
    "glob": render_glob,
    "bash": render_bash,
    "skill": render_skill,
}
```

Each renderer signature stays the same as `todowrite`:

```python
def render_<tool>(console, state) -> bool: ...
def render_<tool>_plain(state) -> bool: ...
```

The dispatcher tries the registered renderer first; if it returns False, falls through to the existing generic JSON renderer.

Tool-name normalization: `tool = part.get("tool", "").strip().lower()`.

## Helper utilities to add (private to `tools/run-agent.py`)

- `_relativize_path(path: str) -> str` — repo-relative path when possible
- `_strip_read_framing(output: str) -> tuple[str | None, dict]` — parse `<path>...<content>...` framing
- `_count_lines_and_bytes(text: str) -> tuple[int, int]`
- `_detect_lexer(path: str) -> str | None` — Pygments lexer from file extension; default `text`
- `_format_output_excerpt(text: str, max_lines: int) -> tuple[str, int]`
- `_is_likely_error_output(text: str) -> bool`
- `_unified_diff(old: str, new: str, context: int = 3) -> list[str]`
- `_truncate_diff(lines: list[str], max_lines: int) -> tuple[list[str], int]`
- snapshot cache: module-level `OrderedDict` with LRU semantics and helpers `_cache_get(path)`, `_cache_set(path, content)`, `_cache_invalidate_stale()`

## Validation plan

After implementation, on `src/sample-c-cli/`:

1. `make phase-1` — exercises `read`, `write`, `glob`, `bash`, `skill`, `todowrite` in one run. Confirm:
   - `Read` panels syntax-highlighted with path header
   - `Write` panels show real diffs for files previously read or written; small-content/excerpt for new files
   - `Glob`, `Bash`, `Skill` per spec
   - `Todos` rendering still works
   - Generic fallback for unrecognized tools still works
2. Run a phase that **rewrites a file** so the diff path is exercised — Phase 4 evidence updates are a good candidate.
3. `NO_COLOR=1 make phase-1` — plain layout, no ANSI for any tool.
4. Run wrapper outside `.venv` — plain mode parity for every renderer.
5. `--debug` — raw JSON still mirrored to stderr.
6. Confirm tunables: set `CODECOME_WRITE_DIFF_LIMIT=10`; verify truncation at 10 lines.
7. Confirm cache: read a file, then mutate it via a separate `bash` command (within a phase or simulated), then write it; confirm "(new file)" rendering instead of an inaccurate diff.
8. Confirm `CODECOME_WRITE_CACHE=0` disables diffing entirely.

## Risks

1. `read`-then-`write` is the common path, but not universal. Mitigation: clean fallback to "new file" rendering with size-based full or excerpt.
2. Snapshot cache memory growth. Mitigation: 200-path LRU cap, tunable.
3. mtime granularity on coarse filesystems. Mitigation: documented; APFS/ext4/Btrfs all give sub-second resolution.
4. Diff cost on large files. Mitigation: skip diff when either side > 200 KB; render `(content too large for diff)` and use excerpt path.
5. Rich `Syntax` cost on large content. Mitigation: 200 KB cap.
6. Lexer mis-detection. Acceptable; Rich falls back to plain text.
7. Heuristic `bash` error detection by string match is imperfect. Border color may be wrong occasionally. Acceptable cosmetic risk.

## Acceptance criteria

Implementation done when:

- All five tools (`read`, `write`, `glob`, `bash`, `skill`) render via dedicated panels in real `make phase-*` runs.
- `write` shows a real diff when a baseline exists (read-then-write or write-after-write in the same session); diff is truncated to `CODECOME_WRITE_DIFF_LIMIT`.
- `write` for new files shows full content when small (≤ 25 lines AND ≤ 1 KB by default), excerpt otherwise.
- mtime-based invalidation correctly drops cache entries when external mutation occurs between events.
- `read` shows syntax-highlighted content with path and optional line range.
- `glob` shows match count and relative paths.
- `bash` shows command and output cleanly; no fake exit code.
- `skill` is one line.
- Any tool not in the dispatcher falls back to the existing generic JSON renderer.
- Plain mode (no rich, `NO_COLOR=1`) works for every renderer.
- `--debug` output unchanged.
- Tunables work via env vars; the four flagged tunables (`--excerpt-lines`, `--write-diff-limit`, `--write-full-lines`, `--write-full-bytes`) work via CLI as well.
- `CODECOME_WRITE_CACHE=0` disables diffing entirely.
- No new package added to `requirements.txt`.

## Out-of-scope follow-ups (not part of this work)

- `apply_patch`, `edit` rendering with diff-style coloring
- `task` rendering with nested sub-agent panels
- A unified replay harness reading `.project/spikes/opencode-json/*.jsonl` and rendering offline
- User-configurable theming via env vars or a config file
- Cross-process cache (Redis or filesystem-backed); current design is process-local on purpose
