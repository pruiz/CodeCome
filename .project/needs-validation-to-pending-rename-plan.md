# Plan: Rename `NEEDS_VALIDATION` → `PENDING`

## Status

v1.0 — workspace-wide rename. Atomic, single-commit change.

## Goal

Replace the verbose `NEEDS_VALIDATION` finding status everywhere it appears
with the cleaner, shorter `PENDING`. This includes Python constants, YAML
config, frontmatter defaults, documentation, agent instructions, skills,
prompts, templates, Makefile targets, and `.gitignore` patterns.

## Locked decisions

1. Makefile target `validate-all` keeps its name. Only help text and the
   internal status filter string change.
2. Python local variable `needs_validation` (e.g. in `tools/render-report.py`)
   is renamed to `pending`.
3. `tools/_colors.py` keeps yellow for PENDING; only the dict key changes.
4. `codecome.yml` `default_status` and `statuses[]` get the literal swap.
5. All prompts under `prompts/` are updated.
6. `.gitignore` directory patterns are updated.
7. `.project/*` files other than this one are **not** modified.
8. On-disk findings under `itemdb/findings/NEEDS_VALIDATION/` are managed
   manually by the user after the commit.
9. Single commit, atomic change.

## Out of scope

- `.project/spikes/opencode-json/*.jsonl` — historical event captures.
- Existing `.project/*.md` plan files — historical docs, not updated.
- `itemdb/findings/NEEDS_VALIDATION/` directory and contents — user-managed.
- `itemdb/index.md` — generated; regenerated automatically on next `make index`.
- Git history — no rewrite.

## Affected files (31 modified)

### Python source (9 files)
- `tools/codecome.py`
- `tools/check-frontmatter.py`
- `tools/gate-check.py`
- `tools/list-findings.py`
- `tools/render-index.py`
- `tools/render-report.py` (variable rename: `needs_validation` → `pending`)
- `tools/move-finding.py`
- `tools/create-finding.py`
- `tools/_colors.py`

### Configuration and templates (3 files)
- `codecome.yml`
- `templates/finding.md`
- `templates/report.md`

### Agent definitions (4 files)
- `.opencode/agents/auditor.md`
- `.opencode/agents/reviewer.md`
- `.opencode/agents/validator.md`
- `.opencode/agents/reporter.md`

### Skills (5 files)
- `.opencode/skills/finding-format/SKILL.md`
- `.opencode/skills/counter-analysis/SKILL.md`
- `.opencode/skills/sandbox-validation/SKILL.md`
- `.opencode/skills/exploit-validation/SKILL.md`
- `.opencode/skills/report-writing/SKILL.md`

### Prompts (3 files)
- `prompts/phase-2-audit.md`
- `prompts/phase-3-review.md`
- `prompts/phase-4-validate.md`

### Documentation (5 files)
- `README.md`
- `AGENTS.md`
- `docs/workflow.md`
- `prompts/README.md`
- `itemdb/README.md`

### Build and ignore (2 files)
- `Makefile`
- `.gitignore`

## Prose clarification

The lowercase English phrase "needs validation" is kept as-is in prose where
it describes an action rather than referencing the status value. For example:
- `tools/render-report.py`: the f-string `"finding(s) needing validation"` is
  kept as prose; only the variable and the status comparison string change.
- `.opencode/agents/reviewer.md`: "remains plausible and needs validation" is
  prose; left unchanged.

## User manual steps after commit

After I commit, the user manually performs the on-disk migration:

1. `git mv itemdb/findings/NEEDS_VALIDATION itemdb/findings/PENDING`
2. Update YAML frontmatter `status: "NEEDS_VALIDATION"` → `status: "PENDING"`
   in any finding files inside the renamed directory.
3. Optionally update body prose in those findings.
4. `make frontmatter` — confirm validation passes.
5. `make index` — refresh generated index.
6. Commit those changes separately.

## Validation after rename

1. `grep -r "NEEDS_VALIDATION" .` returns only `.project/*.md` files and any
   remaining user-managed finding files in the old directory.
2. `.venv/bin/python3 -m py_compile tools/*.py` succeeds.
3. `make venv-check && make check` succeed.
4. `tools/list-findings.py --status PENDING` is a valid argument.
5. `make help` shows updated PENDING terminology.

## Acceptance criteria

- All 31 files updated, none missed.
- Single git commit.
- `make help`, `make check`, and `make venv-check` all succeed.
- `tools/list-findings.py --status PENDING` accepted.
- Post-rename grep clean.
