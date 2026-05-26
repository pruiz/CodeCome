# Plan: Epic B — Findings and Itemdb Consolidation

**Status:** Implemented; final documentation and PR cleanup pending
**Date:** 2026-05-27
**Parent:** [tools-refactor-plan.md](tools-refactor-plan.md)
**PR:** #21 (`wip/tools-refactor`)
**Scope:** Consolidate finding/itemdb logic under `tools/findings/` while preserving historical script entrypoints.

---

## 1. Summary

Epic B completes the findings/itemdb side of the `tools/` refactor. The historical root-level scripts remain stable CLI entrypoints, but implementation code now lives in `tools/findings/` and receives filesystem configuration through `FindingsContext` instead of copied wrapper globals.

This keeps user-facing commands compatible while making finding creation, movement, listing, evidence creation, packaging, report rendering, index rendering, and frontmatter checks testable as library code.

Future CLI consolidation of `run-agent.py` and `codecome.py` is intentionally outside Epic B.

---

## 2. Architecture

```text
tools/
├── create-finding.py              # thin wrapper -> findings.create.main()
├── create-evidence.py             # thin wrapper -> findings.evidence.main()
├── move-finding.py                # thin wrapper -> findings.move.main()
├── list-findings.py               # thin wrapper -> findings.listing.main()
├── package-finding.py             # thin wrapper -> findings.package.main()
├── render-index.py                # thin wrapper -> findings.render_index.main()
├── render-report.py               # thin wrapper -> findings.render_report.main()
├── check-frontmatter.py           # thin wrapper -> findings.checks_entry.main()
└── findings/
    ├── __init__.py                # lightweight package marker; exposes FindingsContext only
    ├── constants.py               # itemdb paths, regexes, status/severity/confidence constants
    ├── frontmatter.py             # YAML frontmatter parsing and replacement helpers
    ├── ids.py                     # finding ID generation, lookup, and iteration
    ├── create.py                  # create_finding() implementation
    ├── evidence.py                # create_evidence() implementation
    ├── move.py                    # move_finding() implementation
    ├── listing.py                 # load_findings(), eligibility filters, listing CLI
    ├── package.py                 # bundle discovery and archive creation
    ├── render_index.py            # itemdb/index.md rendering
    ├── render_report.py           # Markdown report rendering
    ├── checks.py                  # frontmatter validation rules
    └── checks_entry.py            # check-frontmatter CLI entrypoint
```

Implementation modules import sibling findings helpers directly. Root-level scripts do not define copied constants or adapter functions.

---

## 3. Constants and Context

`tools/findings/constants.py` owns the shared itemdb model:

```python
ROOT = Path(__file__).resolve().parents[2]
ITEMDB_ROOT = ROOT / "itemdb"
FINDINGS_ROOT = ITEMDB_ROOT / "findings"
EVIDENCE_ROOT = ITEMDB_ROOT / "evidence"
NOTES_ROOT = ITEMDB_ROOT / "notes"
REPORTS_ROOT = ITEMDB_ROOT / "reports"
INDEX_PATH = ITEMDB_ROOT / "index.md"
```

It also owns stable regexes, status lists, severity/confidence constants, template paths, and helper functions such as `evidence_dir_for()`, `exploits_dir_for()`, and `finding_status_dir()`.

`FindingsContext` is the dependency-injection boundary for filesystem paths:

```python
@dataclass(frozen=True)
class FindingsContext:
    root: Path = ROOT
    itemdb_root: Path = ITEMDB_ROOT
    findings_root: Path = FINDINGS_ROOT
    evidence_root: Path = EVIDENCE_ROOT
    notes_root: Path = NOTES_ROOT
    reports_root: Path = REPORTS_ROOT
    template_path: Path = TEMPLATE_PATH
    evidence_template_path: Path = EVIDENCE_TEMPLATE_PATH

    @classmethod
    def default(cls) -> "FindingsContext":
        return cls()
```

Implementation functions accept `ctx: Optional[FindingsContext] = None` when they need workspace paths. Tests pass temporary contexts explicitly instead of monkeypatching wrapper globals.

---

## 4. Wrappers

Historical scripts stay at their current paths because Makefile targets, docs, and user workflows rely on them.

Wrappers follow this shape:

```python
#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from findings.create import main

if __name__ == "__main__":
    raise SystemExit(main())
```

Wrapper rules:

- no copied filesystem constants;
- no implementation helper functions;
- no test-aware monkeypatch adapters;
- no dynamic imports of wrapper modules;
- smoke-test wrapper behavior with `--help`, but test implementation behavior through `findings.*` modules.

---

## 5. Render-Index Regression Fix

`render-index` must preserve the original per-finding index while optionally keeping a summary section.

Required output:

```markdown
## Summary

| Status | Count |
|---|---:|

## Findings

| ID | Status | Severity | Confidence | Target area | Title | Finding | Evidence |
|---|---|---|---|---|---|---|---|
```

Each finding appears as its own row, even when multiple findings share a status. Evidence links use `validation.evidence_dir` when present and otherwise fall back to `itemdb/evidence/{finding_id}`. Links in `itemdb/index.md` are rendered relative to `itemdb/`.

---

## 6. Acceptance Criteria

- `FindingsContext` is defined once and is default-constructible.
- Shared itemdb paths and regexes are centralized in `findings.constants`.
- Historical root-level findings scripts are thin wrappers.
- Implementation modules accept `FindingsContext` where path injection is needed.
- `findings.__init__` remains lightweight and does not introduce broad package reexports.
- No implementation code scans `sys.modules`, imports wrapper modules dynamically, or contains test-specific path discovery.
- `render-index` emits summary counts and per-finding rows with all original columns.
- Wrapper paths and CLI behavior remain stable.
- `tools/AGENTS.md` documents the findings/itemdb architecture rules.

---

## 7. Test Matrix

| Area | Tests / checks |
|---|---|
| Constants/context | `tests/test_findings_constants.py` verifies default construction, centralized paths, helper paths, and single `FindingsContext` definition. |
| Frontmatter checks | `tests/test_check_frontmatter.py` validates frontmatter parsing and required finding fields. |
| Create finding | `tests/test_create_finding.py` imports `findings.create` and uses temporary `FindingsContext` paths. |
| Move/evidence | `tests/test_move_and_evidence.py` covers status movement and evidence directory creation through implementation modules. |
| Listing | `tests/test_list_findings.py` covers loading/filtering findings through `findings.listing`. |
| Package finding | `tests/test_package_finding.py` covers bundle file discovery and package creation through `findings.package`. |
| Render index | `tests/test_render_index.py` covers summary counts, per-finding rows, full columns, target area, and evidence links. |
| Wrappers | Root-level scripts run `--help` and contain only delegation logic. |

Validation commands:

```bash
python -m pytest tests/test_findings_constants.py tests/test_create_finding.py tests/test_move_and_evidence.py tests/test_list_findings.py tests/test_package_finding.py tests/test_render_index.py tests/test_check_frontmatter.py -v --tb=short

python tools/create-finding.py --help
python tools/create-evidence.py --help
python tools/move-finding.py --help
python tools/list-findings.py --help
python tools/package-finding.py --help
python tools/render-index.py --help
python tools/render-report.py --help
python tools/check-frontmatter.py --help
```

---

## 8. References

- [tools-refactor-plan.md](tools-refactor-plan.md) — overall as-built refactor plan.
- [tools-refactor-a8-plan.md](tools-refactor-a8-plan.md) — A8/A8.1 PR review cleanup.
- [../tools/AGENTS.md](../tools/AGENTS.md) — current architecture rules for future tool changes.
