# Plan: Suppress / Summarize Read Output for Internal Workspace Files

## Status

v3.0 — extends the v2.1 read renderer. Builds on
`.project/tool-renderers-plan.md` v2.1.

## Goal

Reduce visual noise from the most common but least-informative reads in
real `make phase-*` runs: when an agent loads its own skill, agent
definition, workspace config, finding, note, evidence, run summary,
report, or template. Replace the body display with a single descriptive
line that tells the user **what** is being read without dumping its
content.

## Scope

Affects only `render_read_rich` and `render_read_plain`. No changes to
write, edit, glob, bash, skill, or todowrite renderers. No changes to
the snapshot cache mechanics. No new dependencies.

## Detection rules

Use `_relativize_path` to compute the path relative to the repo root.
If the result is still absolute (path is outside the repo), use the
normal v2.1 renderer. Otherwise, classify by prefix.

| Prefix / pattern | Bucket | Full-read description | Partial suffix |
|---|---|---|---|
| `.opencode/agents/<name>.md` | agent | `loading agent: <name>` | ` (partial)` |
| `.opencode/skills/<name>/SKILL.md` | skill | `loading skill: <name>` | ` (partial)` |
| `.opencode/skills/<name>/<rest>` | skill resource | `loading skill resource: <name>/<rest>` | ` (partial)` |
| `.opencode/<other>` | opencode config | `loading opencode config: <relpath>` | ` (partial)` |
| `itemdb/findings/<status>/CC-NNNN-<slug>.md` | finding | `reading finding: CC-NNNN [<status>] - <slug>` | ` (partial)` |
| `itemdb/notes/<name>.md` | note | `reading note: <name>.md` | ` (partial)` |
| `itemdb/evidence/<finding-id>/<rest>` | evidence | `reading evidence: <finding-id>/<rest>` | ` (partial)` |
| `itemdb/reports/<name>.md` | report | `reading report: <name>.md` | ` (partial)` |
| `itemdb/index.md` | index | `reading items index` | ` (partial)` |
| `itemdb/<other>` | itemdb file | `reading itemdb file: <relpath>` | ` (partial)` |
| `runs/<name>.md` | run summary | `reading run summary: <name>.md` | ` (partial)` |
| `templates/<name>` | template | `reading template: <name>` | ` (partial)` |
| `AGENTS.md` (root) | workspace doc | `reading workspace doc: AGENTS.md` | ` (partial)` |
| `codecome.yml` (root) | workspace config | `reading workspace config: codecome.yml` | ` (partial)` |
| `README.md` (root) | workspace doc | `reading workspace doc: README.md` | ` (partial)` |
| anything else | — | normal v2.1 renderer | n/a |

A read is "partial" when `state.input.offset` or `state.input.limit` is
set. Otherwise full.

The slug for a finding is extracted from the filename: the part after
`CC-NNNN-` and before `.md`. Status comes from the parent directory name.

## Display format

Single Rich panel. Title `Read`. Border green on completed, red on error.

Body has exactly two visible lines:

1. Bold cyan relative path (same as v2.1).
2. Dim italic description, with optional ` (partial)` suffix.

No body content. No syntax-highlighted block. No truncation marker.
No `(End of file)` summary line.

The `lines <offset>..<offset+limit-1>` line from v2.1 is **not** shown
for suppressed reads; the `(partial)` suffix already conveys that.

## Plain mode

Header line uses bracketed description format:

```
read [skill: source-recon]
read [finding: CC-0001 NEEDS_VALIDATION - off-by-one-stack-write-in-greet-user]
read [workspace doc: AGENTS.md] (partial)
```

One line per suppressed read.

## Edge cases

1. **Errors**: If `_is_likely_error(output)` is true, fall back to the
   normal red error rendering. Suppression never hides errors.
2. **Unrecognized framing**: Fall back to the normal renderer.
3. **Directory reads**: Always go through normal directory rendering,
   never suppressed.
4. **Findings with malformed names** (not matching `CC-NNNN-<slug>.md`):
   fall back to `reading itemdb file: <relpath>`.
5. **Files outside the repo**: stay on normal renderer.
6. **Status not in canonical set**: status taken verbatim from parent
   directory name; no validation needed.

## Snapshot cache behavior

Cache the full body whenever framing parses cleanly, regardless of
display mode. The classification is purely a display concern. If the
agent later writes back to a suppressed-display file (e.g., a finding,
note, evidence README), the diff path uses the cached body.

This is unchanged from v2.1; the only change is that the cache update
runs *before* the display-suppression decision.

## Tunability

| Knob | Default | Env var | CLI flag |
|---|---|---|---|
| Suppress internal reads | on | `CODECOME_INTERNAL_READ_SUPPRESS` | none |

`=0` disables v3 suppression; reads of internal paths fall through to
v2.1 behavior. No CLI flag — niche debugging knob.

## Implementation outline

1. Add a private helper:

   ```python
   def _classify_internal_read(rel_path: str) -> str | None:
       """Return a description string for suppressible internal reads,
       or None when the path should use the normal renderer."""
   ```

   Pure function, prefix matching on `Path.parts`.

2. In `render_read_rich`:
   - After parsing framing, when `kind == "file"`:
     - Cache the body first (unchanged).
     - If kill switch is on AND `_classify_internal_read(rel_path)`
       returns a label, render the suppressed panel:
       1. Bold cyan relative path
       2. Dim italic description (+ ` (partial)` if offset/limit set)
     - Skip Syntax block, skip footer.
   - Else: continue with normal v2.1 path.

3. In `render_read_plain`:
   - Same logic, single bracketed line.

4. Directory reads: unchanged.
5. Errors: unchanged.

Estimated change: ~80 lines added in `tools/run-agent.py`.

## Validation plan

After implementation:

1. `make phase-1` on `src/sample-c-cli/`:
   - Reads of `AGENTS.md`, `codecome.yml`, `README.md` are one-line
   - Reads of `.opencode/skills/...` are one-line
   - Reads of `.opencode/agents/...` are one-line
   - Reads of `templates/...` are one-line
   - Reads of `src/sample-c-cli/...` use the normal v2.1 panel
   - Directory reads still render entries
2. `make phase-3` (reads findings/notes):
   - Findings: `reading finding: CC-NNNN [STATUS] - <slug>`
   - Notes: `reading note: <name>.md`
3. Trigger a partial read: confirm ` (partial)` suffix.
4. `CODECOME_INTERNAL_READ_SUPPRESS=0 make phase-1`: full v2.1 panels return.
5. `NO_COLOR=1 make phase-1`: plain-mode parity, no ANSI.
6. Trigger error (read non-existent path): red error panel, not a
   suppressed line.
7. Subsequent write to a previously-read finding shows a diff (cache
   populated).

## Risks

1. **Misclassification of unusual paths**: nested skill directories
   handled via `Path.relative_to` so resources render correctly.
2. **Malformed finding filenames**: fall back to generic itemdb form. Safe.
3. **Status from parent dir** taken verbatim. Acceptable.
4. **Cache misses**: cache update runs before suppression decision. Not a risk.
5. **Description length**: rich wraps automatically. Acceptable.

## Acceptance criteria

- All listed prefix patterns produce one-line summaries instead of body.
- Partial reads include ` (partial)` suffix.
- Findings show status and slug.
- Skills distinguish SKILL.md from other resources.
- Errors still render as red panels.
- Directory reads unaffected.
- Snapshot cache continues to populate from full body.
- Kill switch returns full v2.1 behavior.
- No regressions in other renderers.
