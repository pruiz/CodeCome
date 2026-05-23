# Plan: Refactor `tools/` Directory Structure

**Status:** Draft
**Date:** 2026-05-23
**Target:** `tools/run-agent.py`, `tools/events/`, all `tools/*.py` standalone scripts
**Risk Level:** Medium (large structural refactor, all phase targets affected)

---

## 1. Executive Summary

`tools/run-agent.py` has grown to **5,876 lines** with 10+ distinct concerns in a single file. The `events/` sub-package is cleanly separated but tightly coupled back to `run-agent.py` via a runtime callable-injection pattern. Six standalone finding-management scripts each duplicate frontmatter parsing, path resolution, and finding-id regex.

This plan proposes a five-phase refactor that splits the monolith into focused packages (`codecome/`, `rendering/`, `chat/`, `findings/`), extracts shared infrastructure (`events/base.py`), and consolidates the standalone scripts into a `findings/` package — all while keeping the entry-point behavior and Makefile targets unchanged until the final phase.

**Lines of code affected:** ~8,600 (all of `run-agent.py` + the events package + 6 finding scripts). No changes to `opencode/serve.py`, `sandbox-bootstrap.py`, `gate-check.py`, `run-sweep.py`, `check-frontmatter.py`, `_colors.py`, mock tools, or recording tools.

---

## 2. Current Architecture — Full Inventory

### 2.1 File size breakdown

```
tools/
├── run-agent.py               5,876  ← MONOLITH (58% of total)
├── events/
│   ├── __init__.py              393  ← EventLoop orchestrator
│   ├── chat_loop.py             392  ← ChatEventLoop (multi-turn)
│   ├── state_tracker.py         203  ← Delta → finalized parts
│   ├── sse_client.py            200  ← SSE stream + reconnect
│   └── emitters.py               32  ← Callable bridge (2-line function)
├── opencode/
│   ├── serve.py                 333  ← ServerRunner lifecycle
│   └── __init__.py               23
├── _colors.py                   163  ← ANSI codes (shared)
├── codecome.py                  469  ← Workspace validation CLI
├── gate-check.py                339  ← Phase readiness gates
├── run-sweep.py                 214  ← Batch file sweeps
├── sandbox-bootstrap.py         389  ← Sandbox setup/validation
├── create-finding.py            201  ← Finding from template
├── move-finding.py              186  ← Status directory mover
├── create-evidence.py            99  ← Evidence README bootstrap
├── package-finding.py           153  ← Zip bundle
├── list-findings.py             198  ← Listing with filters
├── render-report.py             494  ← Markdown report
├── render-index.py              157  ← itemdb/index.md
├── check-frontmatter.py         138  ← Frontmatter validation
├── list-risk-files.py            75  ← Risk file listing
├── script-to-asciinema.py        76  ← Cast → GIF
├── mock-llm-server.py           180  ← Mock LLM for tests
├── mock-llm-parity.py           162  ← Mock parity checker
└── mock_llm_scripts/             6 JSON files
```

### 2.2 `run-agent.py` internal structure

The 5,876-line file contains these concerns, in file order:

| Lines | Concern | Functions/Classes |
|---|---|---|
| 1–103 | Imports, debug logging, version check | `check_opencode_version`, `_chat_debug`, `_setup_chat_debug` |
| 104–438 | Model resolution | `_scan_event_for_model`, `_discover_opencode_default_model`, `_probe_effective_model`, `_read_codecome_yml_agent`, `resolve_model_and_variant` |
| 440–520 | Prompt loading | `resolve_color_mode`, `build_console`, `load_prompt` |
| 523–675 | Todo rendering | `extract_todos`, `_todo_summary`, `render_todowrite_rich/plain` |
| 678–732 | Permission errors + tunables | `render_permission_error_rich/plain`, ~30 env var config knobs |
| 733–1031 | File cache + utilities | `_SNAPSHOT_CACHE`, `_relativize_path`, `_detect_lexer`, `_compute_diff`, `_cache_set/get/reread`, `_strip_read_framing`, `_classify_internal_read` |
| 1035–1156 | Read tool renderer | `render_read_rich`, `render_read_plain` |
| 1161–1270 | Write tool renderer | `render_write_rich`, `render_write_plain` |
| 1288–1381 | Edit tool renderer | `render_edit_rich`, `render_edit_plain` |
| 1386–1650 | Apply-patch renderer | `_ParsedFilePatch`, `_parse_apply_patch_envelope`, `_extract_apply_patch_payload`, `render_apply_patch_rich/plain` |
| 1655–1750 | Glob renderer | `_parse_glob_output`, `render_glob_rich/plain` |
| 1755–2059 | Grep renderer | `_grep_compile_pattern`, `_grep_format_line_rich/plain`, `_parse_grep_output`, `render_grep_rich/plain` |
| 2064–2120 | Bash renderer | `render_bash_rich/plain` |
| 2123–2923 | Sandbox-bootstrap sub-renderer | `_is_sandbox_bootstrap_json_call`, `_sandbox_payload_matches`, `_maybe_render_sandbox_bootstrap`, 12 `_render_sandbox_*` functions |
| 2925–3518 | Bash-shim sub-renderer | `_BashShim`, `_is_bash_shim_call`, parsers for `cat`/`head`/`tail`/`rg`/`grep`/`ls`/`find`/`tree`/`rtk`, normalizers, `_maybe_render_bash_shim` |
| 3521–3610 | Task + Skill renderers | `render_task_rich/plain`, `render_skill_rich/plain` |
| 3612–3720 | Tool dispatch | `_dispatch_tool_renderer` (10-tool if/elif chain) |
| 3723–4105 | Event renderers | `render_step_start`, `render_text`, `render_reasoning`, `render_tool_use`, `render_step_finish`, `render_error`, `render_session_status`, `render_subagent_status`, `render_message_updated`, `render_event` dispatcher |
| 4107–4213 | CLI parser | `build_parser` |
| 4234–4450 | Thinking + resume logic | `_resolve_thinking_decision`, `_build_phase_resume_prompt`, `_build_frontmatter_resume_prompt`, `_build_resume_command` |
| 4453–4556 | Graceful completion | `check_phase_graceful_completion`, `_exploitation_status_looks_real` |
| 4557–4783 | Session lifecycle + run | `_create_session`, `_create_chat_session`, `_send_prompt_to_session`, `_consume_events`, `_run_single_attempt` |
| 4786–4822 | Model table display | `show_model_table` |
| 4833–5511 | Chat TUI | `TextualConsoleProxy`, `_ChatApp`, `_QuitScreen`, `_run_chat_mode` |
| 5514–5876 | `main()` entry point | Orchestration: server start, attempt loop, retry/resume logic, frontmatter repair, exit handling |

### 2.3 `events/` package structure

```
events/
├── __init__.py          EventLoop — Phase runner orchestrator
│   Uses: SseClient, StateTracker, emit_event
│   Called from: run-agent.py._consume_events()
│   Callback to: run-agent.py.render_event() via render_fn parameter
│
├── chat_loop.py         ChatEventLoop — Multi-turn chat consumer
│   Uses: SseClient, StateTracker, emit_event
│   Called from: run-agent.py._ChatApp (Textual TUI)
│   Duplicates: permission handling, session sync, idle detection, dedup
│
├── sse_client.py        SseClient — Raw SSE stream with reconnection
│   Dependency-free (only stdlib)
│
├── state_tracker.py     StateTracker — Delta → finalized part translation
│   Dependency-free (only stdlib)
│
└── emitters.py          emit_event() — 2-line callable bridge
    Purpose: avoid circular import (events/ → run-agent.py)
```

**Key coupling:** `EventLoop.run(render_fn)` and `ChatEventLoop.start_consumer(render_fn)` both accept `run-agent.py.render_event` as a parameter. The `emitters.py` module simply calls `render_fn(console, phase, label, event)`. This is a runtime dependency inversion to break the compile-time cycle.

### 2.4 Finding management scripts — duplication catalog

All six scripts duplicate these patterns:

```python
# Duplicated in 6 files:
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _colors as C
ROOT = Path(__file__).resolve().parents[1]
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FINDING_ID_RE = re.compile(r"\bCC-(\d{4,})\b")
FINDINGS_ROOT = ROOT / "itemdb" / "findings"

# Duplicated in 4 files:
def load_frontmatter(path: Path) -> dict:
    # 15 lines of identical YAML frontmatter extraction
```

---

## 3. Problems Catalog

### P1: Monolith — 10+ concerns in one file
`run-agent.py` is 5,876 lines. Rendering, orchestration, model resolution, chat TUI, and CLI parsing have no module boundaries. Any change to a renderer risks merge conflicts with TUI changes.

### P2: Circular dependency via callable injection
`run-agent.py` imports `events/EventLoop`, which calls back into `run-agent.py.render_event()` via a `render_fn: Callable` parameter. This means neither module can be understood in isolation, and both must be loaded for any test or analysis.

### P3: `_rich` / `_plain` boilerplate
Every one of the 10 tool renderers has two near-identical functions (~1,300 lines total). The dispatch site repeats `if HAVE_RICH: render_X_rich(...) else: render_X_plain(...)` 10 times in `_dispatch_tool_renderer`.

### P4: EventLoop / ChatEventLoop duplication
Both classes independently implement:
- Permission auto-reject via `POST /permission/{id}/reply`
- Session message sync via `GET /session/{id}/message`
- `_belongs_to_session(event)` filtering
- `_is_session_idle(event)` detection
- Message deduplication via `_seen_message_ids` + `_emitted_signatures`

This is ~250 lines of duplicated logic.

### P5: Implicit bash-renderer dispatch chain
The `bash` tool case in `_dispatch_tool_renderer` has a hardcoded cascade:

```python
elif tool_lower == "bash":
    _cache_invalidate_stale()
    if _maybe_render_sandbox_bootstrap(console, state): return True
    if _maybe_render_bash_shim(console, state): return True
    if HAVE_RICH: return render_bash_rich(console, state)
    else: return render_bash_plain(state)
```

Adding a new interceptor requires editing `_dispatch_tool_renderer` — the chain is implicit.

### P6: Isolated finding scripts with duplicated infrastructure
Six separate `tools/*.py` files each re-implement `load_frontmatter`, path normalization, `FINDING_ID_RE`, and `sys.path` manipulation. They share no module.

### P7: Model resolution is a cross-cutting tangle
`resolve_model_and_variant()` touches CLI args (`_extract_flag_value`), env vars (`CODECOME_MODEL`), YAML config (`codecome.yml`), the opencode SQLite DB, and runtime probe sessions. It has 4 different source-of-truth formats and lives in the same file as the Textual TUI.

---

## 4. Target Architecture

```
tools/
├── _colors.py                          # unchanged
│
├── codecome/                           # NEW: Core runner package
│   ├── __init__.py
│   ├── cli.py                          # main(), build_parser(), show_model_table()
│   ├── config.py                       # resolve_model_and_variant(), load_prompt(),
│   │                                   #   resolve_color_mode(), build_console(),
│   │                                   #   _resolve_thinking_decision(), truthy_env()
│   ├── runner.py                       # _run_single_attempt(), _consume_events(),
│   │                                   #   retry loop, resume prompt builders
│   ├── session.py                      # _create_session(), _create_chat_session(),
│   │                                   #   _send_prompt_to_session(), _get_headers()
│   ├── graceful.py                     # check_phase_graceful_completion(),
│   │                                   #   _phase_checklist_lines(), _phase1_required_artifacts()
│   └── version.py                      # check_opencode_version()
│
├── rendering/                          # NEW: Tool rendering package
│   ├── __init__.py                     # Public API surface
│   ├── registry.py                     # _dispatch_tool_renderer() → chain-of-responsibility
│   ├── cache.py                        # _SNAPSHOT_CACHE, _cache_set/get/reread/invalidate_stale
│   ├── utils.py                        # _relativize_path(), _detect_lexer(),
│   │                                   #   _count_lines_and_bytes(), _compute_diff(),
│   │                                   #   _truncate_diff(), _strip_line_numbers(),
│   │                                   #   _format_excerpt(), _is_likely_error(),
│   │                                   #   _strip_read_framing(), _classify_internal_read(),
│   │                                   #   _current_mtime()
│   ├── read.py                         # render_read_rich(), render_read_plain()
│   ├── write.py                        # render_write_rich(), render_write_plain()
│   ├── edit.py                         # render_edit_rich(), render_edit_plain()
│   ├── apply_patch.py                  # _ParsedFilePatch, _extract_apply_patch_payload(),
│   │                                   #   render_apply_patch_rich/plain()
│   ├── glob.py                         # render_glob_rich(), render_glob_plain()
│   ├── grep.py                         # render_grep_rich(), render_grep_plain()
│   ├── bash.py                         # render_bash_rich(), render_bash_plain()
│   ├── sandbox.py                      # _maybe_render_sandbox_bootstrap() + 12 _render_sandbox_*()
│   ├── bash_shim.py                    # _maybe_render_bash_shim(), _BashShim,
│   │                                   #   parsers (cat/head/tail/rg/grep/ls/find/tree/rtk),
│   │                                   #   normalizers, shim renderers
│   ├── todo.py                         # render_todowrite_rich/plain(), extract_todos()
│   ├── task_skill.py                   # render_task_rich/plain(), render_skill_rich/plain()
│   ├── permissions.py                  # render_permission_error_rich/plain()
│   └── events.py                       # render_step_start(), render_text(), render_reasoning(),
│                                       #   render_tool_use(), render_step_finish(),
│                                       #   render_error(), render_session_status(),
│                                       #   render_subagent_status(), render_message_updated(),
│                                       #   render_server_connected(), render_session_diff(),
│                                       #   render_unknown(), render_event() dispatcher
│
├── chat/                               # NEW: Chat TUI package
│   ├── __init__.py
│   ├── app.py                          # _ChatApp, _QuitScreen, TextualConsoleProxy
│   └── harness.py                      # _run_chat_mode()
│
├── events/                             # REFACTORED: Add base class, reduce duplication
│   ├── __init__.py                     # EventLoop (extends BaseEventConsumer)
│   ├── base.py                         # NEW: BaseEventConsumer
│   │                                   #   Shared: permission handling, session sync,
│   │                                   #   session filtering, idle detection, dedup
│   ├── sse_client.py                   # unchanged
│   ├── state_tracker.py                # unchanged
│   ├── chat_loop.py                    # ChatEventLoop (extends BaseEventConsumer)
│   └── emitters.py                     # unchanged
│
├── opencode/                           # unchanged
│   ├── __init__.py
│   └── serve.py
│
├── findings/                           # NEW: Consolidated finding management
│   ├── __init__.py
│   ├── frontmatter.py                  # Shared: load_frontmatter(), replace_scalar_value(),
│   │                                   #   replace_nested_value(), find_finding(), slugify(),
│   │                                   #   next_finding_id(), iter_finding_files()
│   ├── create.py                       # from create-finding.py
│   ├── move.py                         # from move-finding.py
│   ├── listing.py                      # from list-findings.py
│   ├── evidence.py                     # from create-evidence.py
│   ├── package.py                      # from package-finding.py
│   ├── render_report.py                # from render-report.py
│   └── render_index.py                 # from render-index.py
│
├── gate-check.py                       # unchanged
├── sandbox-bootstrap.py                # unchanged
├── run-sweep.py                        # unchanged
├── codecome.py                         # unchanged
├── check-frontmatter.py                # unchanged
├── list-risk-files.py                  # unchanged
├── script-to-asciinema.py              # unchanged
├── mock-llm-server.py                  # unchanged
├── mock-llm-parity.py                  # unchanged
└── mock_llm_scripts/                   # unchanged
```

### 4.1 New dependency graph

```
codecome/cli.py
  ├── codecome/config.py     (model, prompt, color)
  ├── codecome/runner.py     (orchestration)
  │     ├── codecome/session.py
  │     ├── codecome/graceful.py
  │     ├── events/           (EventLoop)
  │     └── rendering/        (render_event dispatcher)
  ├── chat/harness.py        (--chat mode)
  │     └── chat/app.py
  └── _colors.py

rendering/registry.py
  ├── rendering/read.py write.py edit.py ... bash.py sandbox.py bash_shim.py
  ├── rendering/todo.py task_skill.py permissions.py events.py
  └── rendering/utils.py cache.py

events/base.py
  └── events/sse_client.py
  └── events/state_tracker.py

findings/frontmatter.py
  └── findings/create.py move.py listing.py evidence.py package.py
```

---

## 5. Phased Implementation Plan

### Phase A — Extract Renderers (Lowest Risk)

**Goal:** Move all rendering code out of `run-agent.py` into a new `tools/rendering/` package.

**Why first:** Renderers are pure functions with clear inputs (`Console`, `dict`) and outputs (`bool`). They have no side effects except writing to console. They are the easiest to extract and test in isolation.

**Steps:**

1. **Create `tools/rendering/__init__.py`** — empty, acts as package marker.

2. **Create `tools/rendering/utils.py`** — move these shared utilities:
   - `_relativize_path()`, `_detect_lexer()`, `_count_lines_and_bytes()`
   - `_compute_diff()`, `_truncate_diff()`, `_strip_line_numbers()`
   - `_format_excerpt()`, `_is_likely_error()`
   - `_strip_read_framing()`, `_classify_internal_read()`, `_current_mtime()`
   - All parser regexes: `_READ_FILE_FRAMING_RE`, `_READ_DIR_FRAMING_RE`, `_READ_SUMMARY_RE`, `_LEXER_MAP`, etc.
   - Add `ROOT` constant: `Path(__file__).resolve().parents[2]`

3. **Create `tools/rendering/cache.py`** — move:
   - `_SNAPSHOT_CACHE`, `_WRITE_CACHE_ENABLED`, `_SNAPSHOT_CACHE_CAP`
   - `_cache_set()`, `_cache_get()`, `_cache_invalidate_stale()`, `_cache_reread()`
   - Tunables that affect cache only: `CODECOME_WRITE_CACHE`, `CODECOME_WRITE_CACHE_CAP`

4. **Extract renderers — one module at a time:**
   - `tools/rendering/todo.py` — `render_todowrite_rich/plain`, `extract_todos`, `_todo_summary`
   - `tools/rendering/permissions.py` — `render_permission_error_rich/plain`
   - `tools/rendering/read.py` — `render_read_rich/plain` + helpers
   - `tools/rendering/write.py` — `render_write_rich/plain` + helpers
   - `tools/rendering/edit.py` — `render_edit_rich/plain` + helpers
   - `tools/rendering/apply_patch.py` — `_ParsedFilePatch`, `_parse_apply_patch_envelope`, etc.
   - `tools/rendering/glob.py` — `render_glob_rich/plain`, `_parse_glob_output`
   - `tools/rendering/grep.py` — `render_grep_rich/plain`, `_grep_compile_pattern`, `_parse_grep_output`
   - `tools/rendering/bash.py` — `render_bash_rich/plain`
   - `tools/rendering/sandbox.py` — ALL sandbox-bootstrap code (~700 lines)
   - `tools/rendering/bash_shim.py` — ALL bash-shim code (~500 lines), `_BashShim`, parsers
   - `tools/rendering/task_skill.py` — `render_task_rich/plain`, `render_skill_rich/plain`
   - `tools/rendering/events.py` — `render_step_start`, `render_text`, `render_reasoning`, `render_tool_use`, `render_step_finish`, `render_error`, `render_session_status`, `render_subagent_status`, `render_message_updated`, `render_server_connected`, `render_session_diff`, `render_unknown`, `render_event()` dispatcher, finish-reason constants, permission-error extractor

5. **Create `tools/rendering/registry.py`** — move:
   - `_dispatch_tool_renderer()` — becomes the tool dispatch registry
   - All tunable env vars that affect rendering: `_READ_DISPLAY_LINES`, `_WRITE_CONTENT_LINES`, `_WRITE_DIFF_LIMIT`, `_EDIT_DIFF_LINES`, `_READ_HIGHLIGHT_LIMIT`, `_GLOB_MATCH_CAP`, `_APPLY_PATCH_DIFF_LINES`, `_APPLY_PATCH_MAX_FILES`, `_GREP_FILE_CAP`, `_GREP_LINE_CAP_PER_FILE`, `_GREP_TOTAL_LINE_CAP`, `_GREP_HIGHLIGHT`, `_REASONING_MAX_CHARS`, `_RENDER_REASONING`, `_DEBUG_UNKNOWN_EVENTS`, `_SANDBOX_RENDER`, `_SANDBOX_VALIDATE_STDERR_LINES`, `_SANDBOX_FILES_CAP`, `_BASH_SHIM_RENDER`, `_BASH_SHIM_LS_STRIP_LONG_FORMAT`, `_INTERNAL_READ_SUPPRESS`, `_SUBAGENT_HEARTBEAT_INTERVAL_S`, `_SUBAGENT_UPDATE_THROTTLE_S`, `_TASK_PROMPT_PREVIEW_LINES`, `_RENDER_SUBAGENT_UPDATES`, `_SUBAGENT_LAST_STATE`

6. **Update imports in `run-agent.py`** — replace all moved function definitions with imports from `rendering.*`.

7. **Verify:** Run `make tests` (no rendering changes expected, no breakage of event pipeline).

**Estimated lines moved:** ~2,800 lines out of `run-agent.py`.

**Rollback:** Revert `run-agent.py` and delete `tools/rendering/`. One `git checkout` per step.

---

### Phase B — Extract Chat TUI (Low Risk)

**Goal:** Move all chat-mode code out of `run-agent.py` into a new `tools/chat/` package.

**Steps:**

1. **Create `tools/chat/__init__.py`**

2. **Create `tools/chat/app.py`** — move:
   - `TextualConsoleProxy` class
   - `_ChatApp` class (the Textual `App` subclass)
   - `_QuitScreen` class (the `ModalScreen`)
   - All `HAVE_RICH` guard at the module level, or keep inside the try/except ImportError block
   - `ChatApp` and `QuitScreen` module-level aliases

3. **Create `tools/chat/harness.py`** — move:
   - `_run_chat_mode()` function
   - Chat debug logging: `_CHAT_DEBUG_FP`, `_chat_debug()`, `_setup_chat_debug()`, `_close_chat_debug()`

4. **Update `run-agent.py`:**
   - Replace all moved code with `from chat.harness import _run_chat_mode`
   - Replace all moved code with `from chat.app import ChatApp, QuitScreen`
   - Keep `_setup_chat_debug()` and `_close_chat_debug()` calls in `main()` but import them from `chat.harness`

5. **Verify:** Run `make chat` (if Textual is installed) to confirm TUI still works.

**Estimated lines moved:** ~500 lines out of `run-agent.py`.

---

### Phase C — Extract Shared Event Consumer Base (Medium Risk)

**Goal:** Eliminate the ~250 lines of duplicated logic between `EventLoop` and `ChatEventLoop` by introducing a shared `BaseEventConsumer` class.

**Steps:**

1. **Create `tools/events/base.py`** with:
   ```python
   class BaseEventConsumer:
       """Shared SSE consumption logic for EventLoop and ChatEventLoop."""

       def __init__(self, base_url, session_id, console, *,
                    auth_token=None, workspace_dir=None):
           self.base_url = base_url.rstrip("/")
           self.session_id = session_id
           self.console = console
           self.auth_token = auth_token
           self.workspace_dir = workspace_dir
           self._tracker = StateTracker()
           self._seen_message_ids: set[str] = set()
           self._emitted_signatures: set[tuple[str, str]] = set()

       # --- Shared (currently duplicated in both classes) ---

       def _get_headers(self) -> dict[str, str]: ...

       @staticmethod
       def _is_session_idle(event: dict[str, Any]) -> bool: ...

       def _belongs_to_session(self, event: dict[str, Any]) -> bool: ...

       def _handle_permission(self, event: dict[str, Any]) -> None: ...

       def _sync_session_messages(self) -> list[dict[str, Any]]: ...

       def _dedup_and_emit(self, render_fn, finalized_events) -> None: ...
   ```

2. **Refactor `EventLoop` to extend `BaseEventConsumer`:**
   - Remove duplicated methods
   - Keep: `run()`, `stop()`, `trigger_recovery_sync()`, `_update_result()`, `_build_result()`
   - Call `self._handle_permission(event)` instead of local implementation
   - Call `self._sync_session_messages()` instead of local implementation

3. **Refactor `ChatEventLoop` to extend `BaseEventConsumer`:**
   - Remove duplicated methods
   - Keep: `start_consumer()`, `send_prompt()`, `get_state()`, `stop()`, `_consumer_worker()`
   - Replace `_emit_event()` call with `_dedup_and_emit()`

4. **Update `events/__init__.py`** — export `BaseEventConsumer` optionally for tests.

5. **Verify:** Run all phase targets (`make phase-1`, etc.) and `make chat` to confirm no regression.

**Estimated lines added:** ~80 in new `base.py`; ~120 lines removed from `EventLoop` and `ChatEventLoop` (net reduction ~40 lines, but code quality improvement).

---

### Phase D — Restructure Core Runner (Medium Risk)

**Goal:** Split `run-agent.py` into the `codecome/` package. This is the phase where `run-agent.py` is finally deleted.

**Steps:**

1. **Create `tools/codecome/__init__.py`** — empty package marker.

2. **Create `tools/codecome/version.py`** — move:
   - `check_opencode_version()`, `MINIMUM_OPENCODE_VERSION`, `parse_ver()` (inline helper)

3. **Create `tools/codecome/config.py`** — move:
   - `resolve_model_and_variant()`, `_extract_flag_value()`, `_read_codecome_yml_agent()`
   - `_discover_opencode_default_model()`, `_probe_effective_model()`, `_scan_event_for_model()`
   - `_extract_model_from_export()`, `_strip_probe_unsafe_flags()`
   - `load_prompt()`, `_PHASE_NAMES`, `resolve_color_mode()`, `build_console()`, `truthy_env()`
   - `_resolve_thinking_decision()`, `_thinking_default_for_provider()`
   - `resolve_runtime_model_for_banner()`
   - `_MODEL_FLAG_NAMES`, `_VARIANT_FLAG_NAMES`
   - All model-related constants: `_DISCOVERY_TIMEOUT_S`, `_MODEL_PROBE_TIMEOUT_S`

4. **Create `tools/codecome/session.py`** — move:
   - `_create_session()`, `_create_chat_session()`, `_send_prompt_to_session()`
   - `_get_headers()` (or import from `events.base` if extracted there)

5. **Create `tools/codecome/runner.py`** — move:
   - `_run_single_attempt()`, `_consume_events()`
   - `_build_phase_resume_prompt()`, `_build_frontmatter_resume_prompt()`
   - `_build_resume_command()`, `_emit_fatal_error()`
   - `show_model_table()`

6. **Create `tools/codecome/graceful.py`** — move:
   - `check_phase_graceful_completion()`
   - `_phase_checklist_lines()`, `_phase1_required_artifacts()`
   - `_exploitation_status_looks_real()`, `_phase1_required_artifacts()`, `_path_is_fresh()`, `_iter_files()`
   - `_PHASE1_REQUIRED_ARTIFACT_NAMES`

7. **Create `tools/codecome/cli.py`** — move:
   - `build_parser()`, `main()`, the `if __name__ == "__main__"` block
   - `RUN_START_TIME`, `iteration_retry_count`, `frontmatter_retry_count`
   - Signal handling code (`_forward_signal`, signal setup/teardown)
   - Banner display code
   - Exit status display code

8. **Delete `tools/run-agent.py`** — all code has been moved.

9. **Create `tools/run-agent.py` as a thin wrapper** for backward compatibility during the transition:
   ```python
   #!/usr/bin/env python3
   """Thin wrapper — delegates to codecome.cli."""
   import sys
   from pathlib import Path
   sys.path.insert(0, str(Path(__file__).resolve().parent))
   from codecome.cli import main
   if __name__ == "__main__":
       raise SystemExit(main())
   ```

10. **Update all references:**
    - `Makefile`: Change `python tools/run-agent.py` → `python tools/run-agent.py` (still works via wrapper), OR change to `python -m codecome.cli`. Recommended: keep the wrapper for backward compatibility, add a `make` note about the new canonical path.
    - `tools/run-sweep.py`: Already references `tools/run-agent.py` by path, no change needed.
    - Tests: Update any test that imports from `run-agent` directly (check `tests/`).

11. **Verify:** Run `make tests`, then `make phase-1` through `make phase-6` to confirm all phase targets work.

**Estimated lines moved:** ~1,300 lines into 6 new modules. `run-agent.py` becomes a 15-line wrapper (or deleted entirely once all callers are updated).

---

### Phase E — Consolidate Finding Tools (Low Risk)

**Goal:** Merge 6 standalone scripts into a `findings/` package with shared frontmatter utilities, eliminating duplicated parsing code.

**Steps:**

1. **Create `tools/findings/__init__.py`** — empty package marker.

2. **Create `tools/findings/frontmatter.py`** — shared utilities extracted from the 6 scripts:
   ```python
   ROOT = Path(__file__).resolve().parents[2]
   FINDINGS_ROOT = ROOT / "itemdb" / "findings"
   FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
   FINDING_ID_RE = re.compile(r"\bCC-(\d{4,})\b")
   STATUSES = ["PENDING", "CONFIRMED", "EXPLOITED", "REJECTED", "DUPLICATE"]

   def load_frontmatter(path: Path) -> dict: ...
   def find_finding(identifier: str) -> Path: ...
   def iter_finding_files(status: Optional[str] = None) -> Iterable[Path]: ...
   def collect_finding_ids(paths: Iterable[Path]) -> list[int]: ...
   def next_finding_id() -> str: ...
   def slugify(value: str) -> str: ...
   def replace_scalar_frontmatter(content: str, key: str, value: str) -> str: ...
   def replace_nested_value(content: str, key: str, value: str) -> str: ...
   ```

3. **Refactor each script to use `findings/frontmatter.py`:**
   - `tools/create-finding.py` → `tools/findings/create.py`
   - `tools/move-finding.py` → `tools/findings/move.py`
   - `tools/list-findings.py` → `tools/findings/listing.py`
   - `tools/create-evidence.py` → `tools/findings/evidence.py`
   - `tools/package-finding.py` → `tools/findings/package.py`
   - `tools/render-report.py` → `tools/findings/render_report.py`
   - `tools/render-index.py` → `tools/findings/render_index.py`

4. **Keep thin wrappers** at the original paths for backward compatibility:
   ```python
   # tools/create-finding.py (thin wrapper)
   import sys
   from pathlib import Path
   sys.path.insert(0, str(Path(__file__).resolve().parent))
   from findings.create import main
   if __name__ == "__main__":
       raise SystemExit(main())
   ```

5. **Update `Makefile` and `AGENTS.md`** references if they use absolute paths.

6. **Verify:** Run all finding-management Makefile targets (if any) and manual invocations.

---

## 6. Dependency Resolution During Migration

### Phase A → Phase D ordering rationale

```
Phase A (renderers)      — No imports from codecome/ or chat/. Pure extraction.
    ↓
Phase B (chat TUI)       — Imports from rendering/ (set up in Phase A) + events/.
    ↓
Phase C (events base)    — Independent of codecome/chat/. Can run any time after A.
    ↓
Phase D (core runner)    — Imports from rendering/, chat/, events/, codecome/config,
                           codecome/session, codecome/graceful. Everything else
                           must be in place first.
    ↓
Phase E (findings)       — Completely independent. Can run any time.
```

Phases A and B could be parallelized (different files, no conflicts). Phases C and E are independent and could run in parallel with A/B. Only Phase D has a hard dependency on A+B+C being complete.

### Import verification after each phase

After each phase, run:
```bash
python -c "from tools.rendering import registry"  # Phase A
python -c "from tools.chat import harness"         # Phase B
python -c "from tools.events.base import BaseEventConsumer"  # Phase C
python -c "from tools.codecome.cli import main"    # Phase D
python -c "from tools.findings.frontmatter import load_frontmatter"  # Phase E
```

---

## 7. File Change Summary

| Phase | Files created | Files modified | Files deleted |
|---|---|---|---|
| A | 15 (`rendering/` modules) | 1 (`run-agent.py` — imports only) | 0 |
| B | 3 (`chat/` modules) | 1 (`run-agent.py` — imports only) | 0 |
| C | 1 (`events/base.py`) | 3 (`events/__init__.py`, `chat_loop.py`, `emitters.py`) | 0 |
| D | 6 (`codecome/` modules) | 2 (Makefile, `run-sweep.py`) | 1 (`run-agent.py` → thin wrapper) |
| E | 8 (`findings/` modules) | 7 (old scripts → thin wrappers) | 0 (wrappers preserved) |

**Total new files:** 33
**Total modified files:** 14
**Total deleted:** 1 (original `run-agent.py` body, wrapper remains)

---

## 8. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Import cycle during extraction | Medium | Compile-time error | Each extraction step verified with `python -c "import ..."` before proceeding |
| Event pipeline regression | Low | Phases produce wrong output | Full `make tests` after each phase; spot-check `make phase-1` |
| Chat TUI breakage | Low | Chat mode unusable | `make chat` smoke test after Phase B and D |
| Makefile target path change | Low | CI/CD breakage | Keep thin wrappers; update Makefile only in Phase D with backward compat |
| Global mutable state (caches, tunables) misrouted | Medium | Subtle rendering bugs | Renderer tunables moved as module-level constants; cache centralized in `rendering/cache.py` |
| Tests breaking on import path change | Medium | Test suite failures | Check `tests/` for direct imports from `run-agent`; update in Phase D |

---

## 9. Testing Strategy

### Pre-migration baseline
```bash
make tests          # Record baseline: all tests should pass
make phase-1        # Smoke test: should produce notes
make status         # List findings
```

### Per-phase verification
```bash
# After each phase:
make tests                              # Full test suite
python tools/run-agent.py --show-model --agent recon  # Smoke test

# After Phase D:
make phase-1 PHASE1_OPTS="--dry-run"    # If dry-run support exists
make chat --dry-run                     # If possible
```

### Post-migration full verification (Phase D)
```bash
make tests                              # Must pass
make phase-1                            # Full recon run
make phase-2                            # Hypothesis generation
tools/gate-check.py 1                   # Gate checks
tools/gate-check.py 2
tools/create-finding.py "Test finding"
tools/list-findings.py
tools/move-finding.py CC-XXXX REJECTED
tools/render-report.py
tools/render-index.py
```

### Specific test areas to add
- **`rendering/cache.py`** — standalone unit tests for cache set/get/invalidate
- **`rendering/registry.py`** — test that all tool names dispatch correctly
- **`events/base.py`** — test shared permission handling and session filtering
- **`findings/frontmatter.py`** — test load/save/replace operations

---

## 10. Open Questions

1. **Should renderers use a common base class?** The `_rich`/`_plain` duplication (~1,300 lines) could be unified with a `ToolRenderer` protocol/ABC and a `RenderMode` enum. This is a nice-to-have but adds complexity; defer to a follow-up plan.

2. **Should the bash sub-renderer chain become a registered plugin system?** Currently hardcoded as `sandbox → bash_shim → generic`. A `ChainOfResponsibility` with a list of `BashInterceptor` callables would make adding new interceptors trivial. Defer.

3. **Should `codecome.yml` parsing get its own module?** Currently YAML parsing is scattered: `load_prompt()` parses `audit.extra_prompts`, `resolve_model_and_variant()` parses `agents.<name>`, `codecome.py` parses `project.name`. A `config.py` module that caches the parsed config would eliminate repeated file reads. Defer to a follow-up.

4. **Should the thin wrappers be permanent?** Keeping `tools/run-agent.py`, `tools/create-finding.py`, etc. as thin wrappers preserves backward compatibility for any external scripts or muscle memory. They add negligible maintenance cost. Recommendation: keep them permanently.

5. **Should `tools/` be renamed or restructured further?** The `tools/` directory mixes library code (packages) with standalone scripts. A Python-idiomatic structure would be a `src/` layout with a `pyproject.toml`, but that's a much larger change. Defer.

---

## 11. References

- [tool-renderers-plan.md](tool-renderers-plan.md) — original renderer design
- [chat-mode-plan.md](chat-mode-plan.md) — chat TUI architecture
- [migrate-to-opencode-serve.md](migrate-to-opencode-serve.md) — server migration (prior major refactor)
- [sync-recovery-plan.md](sync-recovery-plan.md) — session sync after SSE reconnect
- [todowrite-renderer-plan.md](todowrite-renderer-plan.md) — first per-tool renderer
- [apply-patch-renderer-plan.md](apply-patch-renderer-plan.md) — most complex renderer
- [internal-read-suppression-plan.md](internal-read-suppression-plan.md) — read display suppression
- [reasoning-and-error-renderers-plan.md](reasoning-and-error-renderers-plan.md) — reasoning panel design
- [discover-opencode-default-model-plan.md](discover-opencode-default-model-plan.md) — model resolution from DB
- [restore-model-banner-plan.md](restore-model-banner-plan.md) — model banner display
