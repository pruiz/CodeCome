# CodeCome Tools Refactor Final Fix Plan

**Status:** Implemented and verified locally  
**Date:** 2026-05-27  
**Target repository:** `pruiz/CodeCome`  
**Target branch:** `wip/tools-refactor`  
**Target PR:** #21

## Summary

The final Epic A and Epic B cleanup plan has been completed. The original working notes were used to close the remaining PR-review and CI items, then collapsed into this implemented summary so `.project/` reflects the final state instead of stale instructions.

The only intentionally deferred item remains future CLI consolidation of `run-agent.py` and `codecome.py` into a single command surface. That consolidation is outside this PR.

## Completed Scope

- Mock LLM parity passes for the basic and comprehensive scripts without normalizing away real output differences.
- `run-agent.py` remains a thin wrapper over `codecome.cli.main()`.
- Chat mode uses the public `chat.harness.run_harness()` entrypoint.
- Console-only helpers live in `codecome.console`; rendering dispatch lives under `rendering`.
- Raw event recording is handled by `codecome.recording.EventRecorder` and is separate from rendering.
- Reasoning display controls live in `RenderSettings` and the rendering layer.
- Rendering dependency direction is documented in `tools/AGENTS.md` and keeps rendering independent of `codecome`.
- `FindingsContext` is defined once in `findings.constants` and provides default itemdb paths.
- Finding/itemdb implementation lives under `tools/findings/`; historical root scripts are thin CLI wrappers.
- Finding implementation modules do not manipulate import paths or dynamically import wrapper modules.
- Finding implementation tests import implementation modules and pass temporary `FindingsContext` values where path injection is needed.
- `render-index` preserves per-finding rows with full columns.
- Library validation errors use exceptions rather than process exits.
- `tools/AGENTS.md`, `tools-refactor-plan.md`, `tools-refactor-a8-plan.md`, and `tools-refactor-epic-b-plan.md` describe or point to the final architecture.

## Final Local Validation

Run from the repository root with the project virtualenv:

```bash
make tests
.venv/bin/python3 tools/check-frontmatter.py
.venv/bin/python3 - <<'PY'
import py_compile
from pathlib import Path

for path in Path("tools").rglob("*.py"):
    py_compile.compile(str(path), doraise=True)
print("py_compile ok")
PY
.venv/bin/python3 tools/run-agent.py --help
.venv/bin/python3 tools/create-finding.py --help
.venv/bin/python3 tools/create-evidence.py --help
.venv/bin/python3 tools/move-finding.py --help
.venv/bin/python3 tools/list-findings.py --help
.venv/bin/python3 tools/package-finding.py --help
.venv/bin/python3 tools/render-report.py --help
.venv/bin/python3 tools/render-index.py --help
.venv/bin/python3 tools/check-frontmatter.py --help
.venv/bin/python3 tools/mock-llm-parity.py --script tools/mock-llm-scripts/basic.json --timeout 45
.venv/bin/python3 tools/mock-llm-parity.py --script tools/mock-llm-scripts/comprehensive.json --timeout 45
```

Expected status:

- Test suite passes.
- Frontmatter check passes.
- Python compile check passes.
- Wrapper help smoke checks pass.
- Mock parity checks pass.
- Stale-pattern searches across `tools`, `tests`, and `.project` have no actionable hits.

## PR Notes

The PR body should summarize the implemented architecture, the Epic B findings/itemdb consolidation, the final validation status, and the single deferred future CLI consolidation item.
