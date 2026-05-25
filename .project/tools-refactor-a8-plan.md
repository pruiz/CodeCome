# Plan: Phase A8 — PR Review Fixes and Architectural Cleanup

**Status:** Active
**Date:** 2026-05-25
**Parent:** [tools-refactor-plan.md](tools-refactor-plan.md)
**PR:** #21 (`wip/tools-refactor`)
**Scope:** Address all unresolved PR review comments from the A1–A5 implementation

---

## 1. Summary

PR #21 accumulated 20 unresolved review threads during the A1–A5 implementation.
This plan addresses all of them in a single phase (A8), grouped into an ordered
execution sequence that respects dependency chains.

Two items are deferred:
- **Unify run-agent.py + codecome.py** → deferred to Phase 2 (Epic B).
- **Legacy globals in cli.py** → already resolved in the last commit.

---

## 2. Execution Order

Tasks are ordered to minimise rework: foundational changes (ROOT, colors, naming)
come first, then structural moves, then the larger splits/extractions.

### Batch 1 — Foundational fixes (no structural moves)

| ID | Thread | File | Action |
|----|--------|------|--------|
| T3 | plan:266 | `tools/mock_llm_scripts/` | `git mv` to `mock-llm-scripts`, update all 16 path-based references across 6 files. |
| T4 | harness:50 | `chat/harness.py` | Remove redundant `check_opencode_version()` call and its import; `cli.py:76` already covers both modes. |
| T5 | harness:56 | multiple | Define `ROOT` once in `codecome/config.py` (already has it at line 24). Remove duplicate `ROOT =` definitions from `cli_render.py`, `transcript.py`, `graceful.py`, and `chat/harness.py`; import from `codecome.config` instead. |
| T12 | config:36 | `codecome/config.py` | Replace inline `_COLOR_ENABLED`/`_RESET`/`_BOLD`/`_DIM` with `import _colors as C` and use `C.RESET`, `C.BOLD`, `C.DIM`. |
| T15 | events/__init__:10 | `events/__init__.py` | Add `ChatEventLoop` to exports. |
| T2 | plan:260 | `.project/tools-refactor-plan.md` | Add note that run-agent.py + codecome.py unification is deferred to Phase 2. |

### Batch 2 — Naming and small structural changes

| ID | Thread | File | Action |
|----|--------|------|--------|
| T7 | harness:83 | multiple | Make `log_level` configurable: read from `--log-level` CLI arg or `OPENCODE_LOG_LEVEL` env var (default `"WARN"`). Both phase and chat paths use the same source. |
| T6 | harness:66 | `codecome/config.py` | Extract `resolve_runtime_config(agent, extra_args) -> RuntimeConfig` that bundles model, variant, thinking resolution into a single call. Both `cli.py` and `chat/harness.py` call this instead of duplicating three separate calls. |
| T13 | graceful:1 | `codecome/graceful.py` | Create `tools/phases/` package. Move `graceful.py` to `phases/completion.py`. Update all imports (`codecome.graceful` → `phases.completion`). |

### Batch 3 — Transcript class

| ID | Thread | File | Action |
|----|--------|------|--------|
| T8 | transcript:1, app:107, harness:109 | `codecome/transcript.py` | Convert to `Transcript` class with `for_phase()` / `for_chat()` class methods, `write_event()`, and `close()`. Remove old free functions entirely (no backward-compat wrappers). Update `runner.py` and `chat/app.py` to use `transcript.write_event(event)`. |

### Batch 4 — Rendering architecture

| ID | Thread | File | Action |
|----|--------|------|--------|
| T16 | events.py:42 | `rendering/events.py` | Split into `rendering/events/` package: `base.py` (EventRenderer + constants + subagent state), then one file per renderer class. `rendering/events/__init__.py` re-exports everything so existing imports continue to work. |
| T11 | cli_render:1 | `codecome/cli_render.py` | Move rendering-related parts (`HAVE_RICH`, Rich stubs, `_get_rendering_ctx`, `render_event`) into `rendering/dispatch.py`. Keep CLI-only parts (`build_console`, `_emit_fatal_error`) in `codecome/cli_render.py`. Update imports. |
| T1 | plan:207 | `rendering/tools/` | Restructure: move `command.py` → `command/__init__.py`, move `interceptors/` → `command/interceptors/`. Update all import paths from `rendering.tools.interceptors.*` to `rendering.tools.command.interceptors.*`. Update plan document. |

### Batch 5 — Phase harness extraction

| ID | Thread | File | Action |
|----|--------|------|--------|
| T10 | cli:198 | `codecome/cli.py` | Extract the phase retry/resume loop (lines ~160–395) into `codecome/harness.py` as `run_phase_mode(args, console, ...)`. `cli.py` becomes: parse args → check version → dispatch to `run_phase_mode()` or `_run_chat_mode()`. |

### Batch 6 — Testing and PR hygiene

| ID | Thread | File | Action |
|----|--------|------|--------|
| T17 | run-agent.py | `tests/` | Add regression test verifying `--read-display-lines`, `--write-content-lines`, `--write-diff-limit`, `--edit-diff-lines` flags propagate into `RenderSettings`. |
| — | PR body | GitHub | Update PR #21 description to reflect A1–A8 implementation status. |
| — | Verify | — | Run `make tests` to confirm all changes pass. |

---

## 3. New Directory Structure (after A8)

Changes from the current structure are marked with `← NEW` or `← MOVED`.

```
tools/
├── run-agent.py                  # Thin wrapper → codecome.cli.main()
├── codecome.py                   # Workspace validation CLI (unchanged)
│
├── codecome/                     # Core runner and configuration
│   ├── cli.py                    #   main() → parse args → dispatch to harness
│   ├── cli_render.py             #   build_console, _emit_fatal_error (CLI-only)  ← SLIMMED
│   ├── config.py                 #   ROOT, env, codecome.yml, prompt, model, thinking
│   ├── session.py                #   OpenCode HTTP: create session, send prompt
│   ├── runner.py                 #   _consume_events, _run_single_attempt
│   ├── harness.py                #   run_phase_mode() — retry/resume loop  ← NEW (from cli.py)
│   ├── transcript.py             #   Transcript class  ← REWRITTEN
│   └── version.py                #   OpenCode version checks
│
├── phases/                       # Phase-specific logic  ← NEW PACKAGE
│   ├── __init__.py
│   └── completion.py             #   ← MOVED from codecome/graceful.py
│
├── rendering/                    # Rendering infrastructure
│   ├── __init__.py
│   ├── base.py
│   ├── cache.py
│   ├── context.py
│   ├── dispatch.py               #   HAVE_RICH, _get_rendering_ctx, render_event  ← NEW (from cli_render.py)
│   ├── registry.py
│   ├── settings.py
│   ├── sink.py
│   ├── utils.py
│   ├── events/                   #   ← NEW PACKAGE (split from events.py)
│   │   ├── __init__.py           #     Re-exports all renderer classes + constants
│   │   ├── base.py               #     EventRenderer, finish constants, subagent state
│   │   ├── step_start.py
│   │   ├── step_finish.py
│   │   ├── text.py
│   │   ├── reasoning.py
│   │   ├── tool_use.py
│   │   ├── error.py
│   │   ├── session_status.py
│   │   ├── session_diff.py
│   │   ├── server.py             #     ServerConnectedRenderer + ServerHeartbeatRenderer
│   │   ├── message.py            #     MessageUpdatedRenderer
│   │   ├── subagent.py
│   │   └── unknown.py
│   └── tools/
│       ├── __init__.py
│       ├── base.py
│       ├── todo.py
│       ├── read.py / write.py / edit.py / glob.py / grep.py
│       ├── apply_patch.py
│       ├── skill.py / task.py / permissions.py
│       └── command/              #   ← RESTRUCTURED
│           ├── __init__.py       #     CommandRenderer (was command.py)
│           └── interceptors/     #     ← MOVED from rendering/tools/interceptors/
│               ├── __init__.py
│               ├── base.py
│               ├── sandbox_bootstrap.py
│               ├── rtk_read.py
│               ├── rtk_grep.py
│               └── shell_listing.py
│
├── mock-llm-scripts/             #   ← RENAMED from mock_llm_scripts
│   ├── basic.json
│   ├── comprehensive.json
│   └── ...
│
├── chat/                         # Chat TUI package (unchanged)
├── events/                       # Event consumption (ChatEventLoop now exported)
├── opencode/                     # opencode serve lifecycle
├── _colors.py                    # Shared ANSI utilities
└── ...                           # Other scripts unchanged
```

---

## 4. Dependency Direction (updated)

```
run-agent.py → codecome/          → (none)
chat/        → codecome/, events/, rendering/
codecome/    → events/, rendering/ (lazy), phases/
phases/      → (stdlib only, reads workspace files)
events/      → (stdlib only, except sse_client)
rendering/   → _colors, (no codecome/ dependency)
```

Key change: `rendering/dispatch.py` replaces the dependency that `codecome/cli_render.py`
had on `rendering/`. Now `codecome/` imports `rendering.dispatch` instead of the reverse.

---

## 5. Acceptance Criteria

```
- All 20 unresolved PR threads addressed (18 fixed, 2 deferred with notes).
- `make tests` passes.
- `py_compile` passes for all moved/new files.
- No duplicate ROOT definitions across modules.
- No duplicate color escape definitions in config.py.
- Transcript logic is a class, not scattered free functions.
- Phase retry/resume loop lives in codecome/harness.py, not cli.py.
- Event renderers are individual files under rendering/events/.
- Interceptors live under rendering/tools/command/interceptors/.
- mock-llm-scripts directory uses hyphenated name.
- PR body is updated.
```

---

## 6. Risks

| Risk | Probability | Impact | Mitigation |
|------|:-----------:|:------:|------------|
| Import cycles from ROOT centralisation | Low | Medium | ROOT stays in config.py which has no execution deps |
| Renderer split breaks existing imports | Medium | High | `rendering/events/__init__.py` re-exports all symbols |
| Command interceptor move breaks imports | Medium | Medium | `rendering/tools/command/interceptors/__init__.py` re-exports |
| Phase harness extraction breaks retry logic | Medium | High | Extract verbatim first, refactor later; run tests after |
| Transcript class change breaks chat/phase flow | Medium | Medium | Keep same write semantics; test both paths |
