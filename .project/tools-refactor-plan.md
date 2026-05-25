# Plan: Refactor `tools/` Directory Structure

**Status:** Draft, revised after architecture review
**Date:** 2026-05-23
**Target:** `tools/run-agent.py`, `tools/events/`, rendering/chat support, and later finding/itemdb tooling
**Risk Level:** Medium (large structural refactor, all phase targets affected)

---

## 1. Executive Summary

`tools/run-agent.py` has grown to **5,876 lines** with many distinct concerns in a single file: CLI parsing, model/prompt resolution, OpenCode session lifecycle, event consumption, terminal rendering, Textual chat, retry/resume policy, frontmatter repair, and phase completion heuristics.

This plan keeps the useful inventory from the original draft but changes the execution strategy:

1. Split the work into two independent epics:
   - **Epic A:** runner / rendering / events / chat.
   - **Epic B:** findings / itemdb tooling.
2. Extract stable core helpers before doing the larger renderer refactor.
3. Refactor rendering around **specific renderer classes** for each event/tool family.
4. Keep renderers close to the existing normalized event dictionaries; do not introduce a custom event model unless a later need appears.
5. Support three rendering destinations explicitly:
   - plain terminal output,
   - Rich terminal output,
   - Textual chat output through a RichLog-compatible sink.
6. Move file snapshot/diff state into an explicit `SnapshotCache`.
7. Introduce `PhaseEventLoop` and `ChatEventLoop`, sharing common SSE/session/dedup/permission logic through a base event loop.
8. Preserve compatibility through thin wrappers at historical script paths.
9. Add `tools/AGENTS.md` to document the architecture rules for future changes.
10. Add explicit unit, fixture, smoke, and acceptance gates so each migration step is verifiable.

The goal is not only to move code out of `run-agent.py`, but to make future changes safer and easier to review.

---

## 2. Current Architecture — Full Inventory

### 2.1 File size breakdown

```text
tools/
├── run-agent.py               5,876  ← MONOLITH
├── events/
│   ├── __init__.py              393  ← EventLoop orchestrator
│   ├── chat_loop.py             392  ← ChatEventLoop (multi-turn)
│   ├── state_tracker.py         203  ← Delta → finalized parts
│   ├── sse_client.py            200  ← SSE stream + reconnect
│   └── emitters.py               32  ← Callable bridge
├── opencode/
│   ├── serve.py                 333  ← ServerRunner lifecycle
│   └── __init__.py               23
├── _colors.py                   163  ← ANSI codes
├── codecome.py                  469  ← Workspace validation CLI
├── gate-check.py                339  ← Phase readiness gates
├── run-sweep.py                 214  ← Batch file sweeps
├── sandbox-bootstrap.py         389  ← Sandbox setup/validation
├── create-finding.py            201
├── move-finding.py              186
├── create-evidence.py            99
├── package-finding.py           153
├── list-findings.py             198
├── render-report.py             494
├── render-index.py              157
├── check-frontmatter.py         138
├── list-risk-files.py            75
├── script-to-asciinema.py        76
├── mock-llm-server.py           180
├── mock-llm-parity.py           162
└── mock-llm-scripts/             6 JSON files
```

### 2.2 `run-agent.py` responsibilities

`run-agent.py` currently contains these concerns:

| Concern | Examples |
|---|---|
| CLI and startup | `build_parser()`, `main()`, signal forwarding, version checks |
| Model/config resolution | `resolve_model_and_variant()`, OpenCode DB discovery, runtime probe, thinking decision |
| Prompt loading | prompt file loading, `codecome.yml` extra prompts, env-provided prompt extras |
| OpenCode session HTTP | create session, create chat session, send prompt, auth headers |
| Event consumption glue | `_consume_events()`, `_run_single_attempt()` |
| Rendering | all generic event renderers and all tool renderers |
| Rendering state | global tunables, snapshot cache, path helpers, diff helpers |
| Command-specific rendering | sandbox-bootstrap JSON rendering, `rtk`/`rg`/`ls`/`find`/`tree` shims |
| Phase policy | finish reason classification, auto-resume prompts, graceful completion checks |
| Frontmatter repair | local validation and minimal auto-repair retry loop |
| Chat TUI | Textual app, RichLog proxy, chat debug logging, modeline |

### 2.3 `events/` package structure

```text
events/
├── __init__.py          EventLoop — phase runner orchestrator
├── chat_loop.py         ChatEventLoop — multi-turn chat consumer
├── sse_client.py        SseClient — raw SSE stream with reconnection
├── state_tracker.py     StateTracker — delta → finalized part translation
└── emitters.py          emit_event() — small callable bridge
```

`EventLoop` and `ChatEventLoop` already separate phase and chat lifecycle, but they duplicate important shared logic:

- permission auto-reject,
- session message sync,
- session filtering,
- idle detection,
- deduplication,
- finalized event emission.

The final design should keep the phase/chat split while moving the common parts into a base event loop.

### 2.4 Finding management scripts — duplication catalog

Several scripts duplicate these patterns:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _colors as C
ROOT = Path(__file__).resolve().parents[1]
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FINDING_ID_RE = re.compile(r"\bCC-(\d{4,})\b")
FINDINGS_ROOT = ROOT / "itemdb" / "findings"
```

This is real duplication, but it should be addressed as a separate findings/itemdb epic rather than mixed into the runner/rendering refactor.

---

## 3. Problems Catalog

### P1: `run-agent.py` is a monolith

Many unrelated concerns share one file. Renderer work, chat changes, model-resolution changes, and phase-runner changes all collide in the same module.

### P2: Rendering lacks module boundaries

Rendering is implemented as a large collection of functions plus global settings. Tool renderers and generic event renderers live together in `run-agent.py`, and the main dispatch function is a long hardcoded chain.

### P3: Rich/plain rendering is duplicated

Most tool renderers have separate `_rich` and `_plain` functions. Some duplication is unavoidable, but the current structure repeats dispatch and setup logic too much.

### P4: Rendering state is implicit

Path roots, Rich availability, display tunables, and the write/diff snapshot cache are module-level globals. Some are stable for the duration of one wrapper run, but they should still be explicit runtime context.

### P5: Snapshot cache side effects are hidden

Read/write/edit/apply_patch renderers use a cache-like mechanism to show useful diffs. That behavior is useful, but the state should be explicit and isolated as `SnapshotCache`.

### P6: EventLoop / ChatEventLoop duplication

Phase and chat consumption share a lot of SSE/session mechanics but currently implement them separately.

### P7: Command execution rendering is implicit

The current bash rendering path has special cases for CodeCome commands and shell helper patterns. This coupling is intentional and useful, but it should be represented as an explicit interceptor chain rather than buried in the main tool dispatcher.

### P8: Finding scripts duplicate frontmatter/path helpers

Finding/itemdb CLI scripts should keep their stable entrypoints, but reusable logic belongs in a shared package.

### P9: Current tests are too broad for a safe structural refactor

A single `make tests` gate is not enough for this migration. Rendering, event-loop behavior, command interceptors, wrapper compatibility, and finding helper behavior need focused tests and acceptance checks.

---

## 4. Target Architecture

```text
tools/
├── _colors.py                          # unchanged
│
├── codecome/                           # Core runner/config package
│   ├── __init__.py
│   ├── cli.py                          # main(), build_parser(), top-level banners
│   ├── config.py                       # env, codecome.yml, prompt, model, color/render settings
│   ├── session.py                      # OpenCode HTTP session/prompt helpers
│   ├── runner.py                       # phase attempt loop and high-level orchestration
│   ├── graceful.py                     # phase completion checks and resume prompt builders
│   ├── transcript.py                   # transcript path/open/write helpers
│   └── version.py                      # OpenCode version checks
│
├── rendering/                          # Rendering package
│   ├── __init__.py
│   ├── context.py                      # RenderContext
│   ├── settings.py                     # RenderSettings
│   ├── cache.py                        # SnapshotCache
│   ├── sink.py                         # PlainSink, RichConsoleSink, TextualRichLogSink
│   ├── registry.py                     # RendererRegistry
│   ├── events.py                       # generic event renderer classes
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py                     # ToolRenderer base class
│   │   ├── todo.py                     # TodoRenderer
│   │   ├── read.py                     # ReadRenderer
│   │   ├── write.py                    # WriteRenderer
│   │   ├── edit.py                     # EditRenderer
│   │   ├── apply_patch.py              # ApplyPatchRenderer
│   │   ├── glob.py                     # GlobRenderer
│   │   ├── grep.py                     # GrepRenderer
│   │   ├── task.py                     # TaskRenderer
│   │   ├── skill.py                    # SkillRenderer
│   │   └── command/                    # CommandRenderer + interceptors
│   │       ├── __init__.py             #   CommandRenderer for bash/tool command execution
│   │       └── interceptors/
│   │           ├── __init__.py
│   │           ├── base.py             #   CommandExecutionInterceptor protocol/base
│   │           ├── sandbox_bootstrap.py #  sandbox-bootstrap / make sandbox-* renderer
│   │           ├── rtk_read.py         #   rtk read / cat/head/tail equivalent rendering
│   │           ├── rtk_grep.py         #   rtk grep / rg equivalent rendering
│   │           └── shell_listing.py    #   ls/find/tree listing rendering
│
├── chat/                               # Chat TUI package
│   ├── __init__.py
│   ├── app.py                          # Textual App and QuitScreen
│   ├── console_proxy.py                # Textual-safe RichLog proxy/sink support
│   ├── debug.py                        # chat debug log helpers
│   └── harness.py                      # run_chat_mode()
│
├── events/                             # Event consumption package
│   ├── __init__.py                     # compatibility exports
│   ├── base.py                         # BaseEventLoop shared logic
│   ├── phase_loop.py                   # PhaseEventLoop
│   ├── chat_loop.py                    # ChatEventLoop
│   ├── sse_client.py                   # unchanged or minimally changed
│   ├── state_tracker.py                # unchanged or minimally changed
│   └── emitters.py                     # unchanged or removed if no longer needed
│
├── opencode/                           # unchanged
│   ├── __init__.py
│   └── serve.py
│
├── findings/                           # Later epic: consolidated finding management
│   ├── __init__.py
│   ├── frontmatter.py
│   ├── create.py
│   ├── move.py
│   ├── listing.py
│   ├── evidence.py
│   ├── package.py
│   ├── render_report.py
│   └── render_index.py
│
├── AGENTS.md                           # architecture guidelines for tools/
│
├── run-agent.py                        # thin wrapper, compatibility entrypoint
├── create-finding.py                   # thin wrapper after findings epic
├── move-finding.py                     # thin wrapper after findings epic
├── list-findings.py                    # thin wrapper after findings epic
├── create-evidence.py                  # thin wrapper after findings epic
├── package-finding.py                  # thin wrapper after findings epic
├── render-report.py                    # thin wrapper after findings epic
├── render-index.py                     # thin wrapper after findings epic
│
├── gate-check.py                       # unchanged initially
├── sandbox-bootstrap.py                # unchanged initially
├── run-sweep.py                        # unchanged initially, may keep calling wrapper
├── codecome.py                         # unchanged initially; unification with run-agent.py deferred to Phase 2
├── check-frontmatter.py                # unchanged initially
├── list-risk-files.py                  # unchanged initially
├── script-to-asciinema.py              # unchanged
├── mock-llm-server.py                  # unchanged
├── mock-llm-parity.py                  # unchanged
└── mock-llm-scripts/                   # unchanged
```

---

## 5. Rendering Design

### 5.1 Renderer inputs

Renderers should receive the normalized event dictionaries that the event layer already produces. Do not introduce a custom event object model in this refactor.

```python
Event = dict[str, Any]
ToolState = dict[str, Any]
```

Generic event renderers receive the whole event:

```python
class EventRenderer:
    event_types: tuple[str, ...] = ()

    def render(self, event: dict[str, Any]) -> bool:
        ...
```

Tool renderers receive the tool name and tool state extracted from a `tool_use` event:

```python
class ToolRenderer:
    tool_names: tuple[str, ...] = ()

    def render(self, tool_name: str, state: dict[str, Any]) -> bool:
        ...
```

This keeps the boundary simple and close to the current implementation.

### 5.2 Specific renderer classes

Use one renderer class per event/tool family. Avoid a single giant renderer class.

Examples:

```text
Generic event renderers:
- ServerConnectedRenderer
- ServerHeartbeatRenderer
- MessageUpdatedRenderer
- TextEventRenderer
- ReasoningEventRenderer
- StepStartRenderer
- StepFinishRenderer
- ErrorEventRenderer
- SessionStatusRenderer
- SessionDiffRenderer
- SubagentStatusRenderer
- UnknownEventRenderer

Tool renderers:
- TodoRenderer
- ReadRenderer
- WriteRenderer
- EditRenderer
- ApplyPatchRenderer
- GlobRenderer
- GrepRenderer
- CommandRenderer
- TaskRenderer
- SkillRenderer
- FallbackToolRenderer
```

### 5.3 Render context

Renderers share a small runtime context:

```python
@dataclass
class RenderContext:
    root: Path
    sink: RenderSink
    settings: RenderSettings
    cache: SnapshotCache
```

This replaces scattered globals such as `ROOT`, Rich/Textual destination checks, render tunables, and snapshot cache state.

### 5.4 Render sinks: destination abstraction, not layout abstraction

The sink abstracts where output is written. It should not restrict what renderers can draw.

Rendering must support three destinations:

1. **Plain**: basic text output, no Rich renderables, no ANSI dependency.
2. **Rich console**: normal terminal phase run using `rich.console.Console`.
3. **Textual chat**: chat mode writing Rich renderables into a Textual `RichLog` or thread-safe proxy.

```python
class RenderSink(Protocol):
    mode: Literal["plain", "rich", "textual"]

    def write(self, renderable: Any, *, expand: bool = True) -> None:
        ...

    def write_text(self, text: str) -> None:
        ...
```

Implementations:

```text
PlainSink
  - writes plain strings to stdout
  - used when Rich is unavailable or color/rich output is disabled

RichConsoleSink
  - wraps rich.console.Console
  - renderers may write arbitrary Rich renderables: Panel, Group, Text, Table, Syntax, Rule, etc.

TextualRichLogSink
  - wraps a Textual RichLog or a thread-safe proxy
  - renderers may write the same Rich renderables as RichConsoleSink
```

Rich and Textual normally share the same `render_rich()` code path; only the sink differs.

### 5.5 Base renderer helpers

A base renderer may provide convenience helpers, but should not impose a fixed layout such as “everything is a panel”.

```python
class BaseRenderer:
    def __init__(self, context: RenderContext) -> None:
        self.context = context

    @property
    def sink(self) -> RenderSink:
        return self.context.sink

    @property
    def rich(self) -> bool:
        return self.context.sink.mode in ("rich", "textual")

    @property
    def plain(self) -> bool:
        return self.context.sink.mode == "plain"
```

Individual renderers remain free to emit the Rich renderables that best fit their output.

### 5.6 SnapshotCache

Move file snapshot/diff state into a dedicated component:

```python
class SnapshotCache:
    def set(self, path: Path, content: str) -> None: ...
    def get(self, path: Path) -> str | None: ...
    def invalidate_stale(self) -> None: ...
    def reread(self, path: Path) -> None: ...
```

Expected use:

```text
ReadRenderer        -> may populate cache
WriteRenderer       -> may compare/update cache
EditRenderer        -> may reread cache
ApplyPatchRenderer  -> may reread cache
Search/render shims -> may invalidate stale entries before rendering
```

### 5.7 CommandExecutionInterceptor

Command execution rendering is intentionally CodeCome-aware. Special rendering for `tools/sandbox-bootstrap.py --format json`, `make sandbox-*`, `rtk read`, `rtk grep`, `rg`, `ls`, `find`, or `tree` is product behavior, not accidental coupling.

Model this as a command renderer plus an interceptor chain:

```python
class CommandExecutionInterceptor(Protocol):
    name: str

    def try_render(
        self,
        command: str,
        state: dict[str, Any],
        renderer: "CommandRenderer",
    ) -> bool:
        ...
```

```python
class CommandRenderer(ToolRenderer):
    tool_names = ("bash",)

    def render(self, tool_name: str, state: dict[str, Any]) -> bool:
        command = self.extract_command(state)
        for interceptor in self.interceptors:
            if interceptor.try_render(command, state, self):
                return True
        return self.render_generic_command(state)
```

This keeps CodeCome-specific command knowledge organized and extensible without growing the main tool dispatcher.

---

## 6. Event Loop Design

### 6.1 Class layout

```text
events/
├── base.py         BaseEventLoop
├── phase_loop.py   PhaseEventLoop
├── chat_loop.py    ChatEventLoop
├── sse_client.py
└── state_tracker.py
```

`BaseEventLoop` owns shared mechanics:

- SSE client construction hooks,
- session filtering,
- permission auto-reject,
- session message sync,
- deduplication,
- finalized event emission,
- common HTTP headers.

`PhaseEventLoop` owns phase-specific lifecycle:

- consume one session until idle,
- update and return `RunResult`,
- support recovery sync after reconnect,
- terminate when the phase attempt is complete.

`ChatEventLoop` owns chat-specific lifecycle:

- long-lived consumer,
- multi-turn `send_prompt()`,
- stop semantics for the TUI,
- no single-attempt `RunResult` completion contract.

### 6.2 Compatibility alias

Keep import compatibility during migration:

```python
# events/__init__.py
from events.phase_loop import PhaseEventLoop

EventLoop = PhaseEventLoop
```

---

## 7. CodeCome Core Package Design

### 7.1 `codecome/config.py`

`codecome/config.py` is intentionally transversal. It should centralize CodeCome configuration resolution, but it must not contain execution logic.

Allowed in `config.py`:

- env helpers,
- cached `codecome.yml` loading,
- prompt extra configuration,
- model/variant resolution,
- thinking mode resolution,
- color/output mode resolution,
- render settings creation.

Not allowed in `config.py`:

- server start/stop,
- session creation,
- prompt submission,
- phase attempt loops,
- retry/autoresume loops,
- phase completion checks.

### 7.2 Other core modules

```text
codecome/version.py
  OpenCode version checks.

codecome/session.py
  OpenCode HTTP API helpers: headers, create session, create chat session, send prompt.

codecome/graceful.py
  Phase completion checks, required artifact checks, resume prompt builders.

codecome/transcript.py
  Transcript path naming, opening, writing, closing helpers.

codecome/runner.py
  Phase execution attempt orchestration.

codecome/cli.py
  CLI parser, main(), startup banner, exit summary, signal handling.
```

`tools/run-agent.py` remains as a thin wrapper to `codecome.cli.main()`.

---

## 8. Phased Implementation Plan

## Epic A — Runner / Rendering / Events / Chat

### Phase A1 — Extract stable core helpers

**Goal:** Reduce `run-agent.py` before the larger rendering refactor.

Create:

```text
tools/codecome/
├── __init__.py
├── config.py
├── session.py
├── version.py
├── graceful.py
└── transcript.py
```

Move:

- `check_opencode_version()` and version constants,
- `truthy_env()`,
- prompt loading and extra prompt config,
- model/variant/thinking resolution,
- color/output mode resolution,
- OpenCode session and prompt HTTP helpers,
- graceful phase completion helpers,
- resume prompt builders,
- transcript path/open/write helpers.

Keep `run-agent.py` behavior unchanged.

### Phase A2 — Introduce rendering foundation

**Goal:** Add the rendering architecture without migrating all renderers at once.

Create:

```text
tools/rendering/
├── __init__.py
├── context.py
├── settings.py
├── cache.py
├── sink.py
├── registry.py
├── events.py
├── tools/__init__.py
├── tools/base.py
├── command_interceptors/__init__.py
└── command_interceptors/base.py
```

Add:

- `RenderContext`,
- `RenderSettings`,
- `SnapshotCache`,
- `RenderSink` implementations,
- base `EventRenderer` and `ToolRenderer`,
- `RendererRegistry`,
- base `CommandExecutionInterceptor`.

### Phase A3 — Migrate renderers incrementally

**Goal:** Move and refactor renderers in small behavior-preserving batches.

Suggested subphases:

1. `TodoRenderer`, `TaskRenderer`, `SkillRenderer`, permission/error helpers.
2. `ReadRenderer`, `WriteRenderer`, `EditRenderer`, plus `SnapshotCache` integration.
3. `ApplyPatchRenderer`.
4. `GlobRenderer` and `GrepRenderer`.
5. `CommandRenderer` with generic command rendering.
6. `CommandExecutionInterceptor` implementations for sandbox-bootstrap, `rtk read`, `rtk grep`, and shell listing commands.
7. Generic event renderers in `rendering/events.py`.
8. Fallback tool/event renderers.

At each step, `tools/run-agent.py` should still work.

### Phase A4 — Extract Chat TUI

**Goal:** Move chat code out of `run-agent.py` and make chat use the same rendering infrastructure.

Create:

```text
tools/chat/
├── __init__.py
├── app.py
├── console_proxy.py
├── debug.py
└── harness.py
```

Move:

- Textual app,
- quit modal,
- RichLog proxy,
- chat debug logging,
- `_run_chat_mode()`.

Chat should use `TextualRichLogSink` or an equivalent proxy-compatible sink.

### Phase A5 — Extract phase runner and CLI

**Goal:** Leave `tools/run-agent.py` as a thin compatibility wrapper.

Create:

```text
tools/codecome/
├── cli.py
└── runner.py
```

Move:

- `build_parser()`,
- `main()`,
- phase execution loop,
- frontmatter repair loop,
- auto-resume loop,
- signal handling,
- final exit summaries.

Replace `tools/run-agent.py` with:

```python
#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codecome.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

### Phase A6 — Refactor events package

**Goal:** Share SSE/session/dedup/permission logic between phase and chat loops.

Create/refactor:

```text
tools/events/
├── base.py
├── phase_loop.py
├── chat_loop.py
├── __init__.py
```

Move shared logic to `BaseEventLoop` and keep compatibility alias `EventLoop = PhaseEventLoop`.

### Phase A7 — Add tools architecture guide

**Goal:** Prevent future changes from reintroducing a monolith.

Create `tools/AGENTS.md` with these guidelines:

- historical scripts are thin wrappers;
- core runner logic lives under `tools/codecome/`;
- `codecome/config.py` is transversal config only, not execution logic;
- event loops live under `tools/events/`;
- renderers live under `tools/rendering/`;
- renderers receive normalized dict events/tool states;
- Rich and Textual renderers can emit arbitrary Rich renderables through a sink;
- snapshot/diff state belongs in `SnapshotCache`;
- command-specific rendering is implemented through `CommandExecutionInterceptor`;
- finding/itemdb helpers live under `tools/findings/`.

## Epic B — Findings / itemdb tooling

### Phase B1 — Extract shared finding helpers

Create:

```text
tools/findings/
├── __init__.py
└── frontmatter.py
```

Move shared helpers:

- frontmatter loading/parsing,
- finding ID regex and lookup,
- status directory constants,
- iterating finding files,
- next finding ID,
- slug helpers,
- frontmatter scalar/nested replacement helpers.

### Phase B2 — Move finding scripts behind wrappers

Move implementation into:

```text
tools/findings/
├── create.py
├── move.py
├── listing.py
├── evidence.py
├── package.py
├── render_report.py
└── render_index.py
```

Keep historical scripts as thin wrappers.

### Phase B3 — Update references

Update Makefile/docs/AGENTS references only where needed. Prefer keeping existing CLI paths stable.

---

## 9. Dependency and Ordering Notes

Recommended order:

```text
A1 core helpers
  ↓
A2 rendering foundation
  ↓
A3 renderer migration
  ↓
A4 chat extraction
  ↓
A5 runner/CLI extraction
  ↓
A6 events base loop
  ↓
A7 tools/AGENTS.md
```

Epic B is independent and can happen after Epic A or in parallel if done by a separate PR sequence.

Why not extract renderers first?

- The renderer refactor is important, but the current renderers depend on many globals and helpers.
- Extracting stable core helpers first reduces noise and lowers the risk of the renderer migration.
- Rendering should be refactored, not merely moved function-by-function.

---

## 10. Testing Strategy

The refactor must be validated with focused tests, not only by running the broad test suite. Each phase should add or update tests around the component being moved.

### 10.1 Pre-migration baseline

Before implementation starts, capture a known-good baseline:

```bash
make tests
python tools/run-agent.py --help
python tools/run-agent.py --show-model --agent recon
```

If practical, also run a small/mock phase target or an existing recorded/mock OpenCode flow and keep representative `tmp/last-phase-*.jsonl` snippets as fixtures.

### 10.2 Unit tests to add

#### Rendering

Suggested layout:

```text
tests/rendering/
├── test_snapshot_cache.py
├── test_registry.py
├── test_sinks.py
├── test_read_renderer.py
├── test_write_renderer.py
├── test_apply_patch_renderer.py
├── test_grep_renderer.py
├── test_command_renderer.py
└── test_command_interceptors.py
```

Required coverage:

| Component | Required tests |
|---|---|
| `SnapshotCache` | `set/get`, stale invalidation, reread existing file, reread missing file, capacity/LRU if implemented |
| `RendererRegistry` | dispatch by generic event type, dispatch by `tool_use` tool name, fallback for unknown event/tool |
| `PlainSink` | works without Rich, writes plain strings, does not require ANSI support |
| `RichConsoleSink` | accepts arbitrary Rich renderables such as `Text`, `Panel`, `Table`, `Group`, `Syntax` |
| `TextualRichLogSink` | delegates to a fake RichLog/proxy and preserves `expand` |
| `ReadRenderer` | file/directory framing, internal read suppression, cache population |
| `WriteRenderer` | new-file output, diff output with cached previous content, cache update |
| `EditRenderer` | old/new diff rendering and cache reread behavior |
| `ApplyPatchRenderer` | `*** Begin Patch` envelope, unified diff fallback, JSON patch list variant |
| `GlobRenderer` / `GrepRenderer` | file-list vs `path:line:text` mode, result caps, no-match output |
| `CommandRenderer` | interceptor ordering, fallback generic command rendering |
| `CommandExecutionInterceptor` | sandbox-bootstrap JSON, `rtk read`, `rtk grep`, `ls/find/tree` recognition |

Renderer tests should not require a real terminal. Use fake/recording sinks, for example:

```python
class RecordingSink:
    mode = "rich"

    def __init__(self):
        self.items = []

    def write(self, renderable, *, expand=True):
        self.items.append((renderable, expand))

    def write_text(self, text):
        self.items.append((text, True))
```

#### Events

Suggested layout:

```text
tests/events/
├── test_state_tracker.py
├── test_base_event_loop.py
├── test_phase_event_loop.py
└── test_chat_event_loop.py
```

Required coverage:

| Component | Required tests |
|---|---|
| `StateTracker` | accumulate deltas, emit finalized text only on `time.end`, emit tool only on `completed`/`error`, ignore in-progress parts |
| `BaseEventLoop` | session filtering, idle detection, auth/workspace headers, permission auto-reject with mocked HTTP |
| Session sync | `GET /session/{id}/message` synthesizes unseen finalized events |
| Dedup | no double-rendering after sync/reconnect for the same `part.id`/message |
| `PhaseEventLoop` | consumes fixture stream until idle and returns expected `RunResult` |
| `ChatEventLoop` | supports long-lived multi-turn consumption and `stop()` semantics |

Mock `SseClient.events()` with deterministic event generators. Do not require a live OpenCode server for unit tests.

#### CodeCome core

Suggested layout:

```text
tests/codecome/
├── test_config.py
├── test_session.py
├── test_graceful.py
├── test_transcript.py
└── test_cli_smoke.py
```

Required coverage:

| Component | Required tests |
|---|---|
| `config.py` | model precedence: `OPENCODE_ARGS` > env > `codecome.yml` > discovery |
| Prompt loading | finding placeholder replacement, extra prompts from yml/file/env, error when placeholder is required but missing |
| Thinking decision | Anthropic provider default, non-Anthropic default, env override, `--thinking` override |
| `session.py` | create-session payloads, prompt payloads, model provider/modelID split, variant handling, auth/workspace headers |
| `graceful.py` | phase 1 artifacts, phase 2 pending finding, phase 4 evidence, phase 5 exploited/not-feasible paths |
| `transcript.py` | stable naming, attempt counters, JSONL writing, no collision in normal use |

#### Findings

For Epic B:

```text
tests/findings/
├── test_frontmatter.py
├── test_finding_lookup.py
├── test_create.py
├── test_move.py
├── test_listing.py
└── test_package.py
```

Required coverage:

| Component | Required tests |
|---|---|
| `load_frontmatter` | valid YAML, missing frontmatter, invalid YAML |
| finding lookup | by `CC-0001`, by filename, across status directories |
| next ID | ignores `.gitkeep`, computes next ID from existing findings |
| move | moves status directory and updates frontmatter status |
| wrappers | historical scripts still run `--help` successfully |

### 10.3 Golden / fixture tests for rendering

Add representative event fixtures so renderer behavior is checked directly:

```text
tests/fixtures/rendering/
├── read_file_event.json
├── write_file_event.json
├── apply_patch_event.json
├── grep_lines_event.json
├── sandbox_validate_bash_event.json
├── task_event.json
├── reasoning_event.json
└── expected/
    ├── read_file.plain.txt
    ├── write_file.plain.txt
    ├── apply_patch.plain.txt
    └── ...
```

For plain mode, compare stable text output.

For Rich/Textual, avoid fragile ANSI snapshots. Prefer one of:

1. `RecordingSink` checks for renderable types and important text fragments.
2. `rich.console.Console(record=True, width=120)` with color disabled and stable exported text.
3. Key-string assertions: title, path, diff summary, status, error text, etc.

Acceptance goal:

```text
- plain mode output contains the same key information as before;
- rich mode emits structured Rich renderables instead of falling back to raw JSON;
- textual mode uses the same Rich rendering path as rich console, with a different sink.
```

### 10.4 CLI and wrapper compatibility tests

Historical paths must keep working:

```bash
python tools/run-agent.py --help
python tools/run-agent.py --show-model --agent recon
python tools/create-finding.py --help
python tools/list-findings.py --help
python tools/move-finding.py --help
python tools/render-report.py --help
python tools/render-index.py --help
```

After `run-agent.py` becomes a wrapper, explicitly verify:

```text
- `python tools/run-agent.py ...` works;
- `python -m codecome.cli ...` works if supported;
- Makefile targets still invoke a valid path;
- `tools/run-sweep.py` still works without modification or is updated in the same PR.
```

---

## 11. Acceptance Gates

Each phase must define automated checks, smoke/manual checks, and acceptance criteria. A phase is not complete merely because `make tests` passes.

| Phase | Required automated checks | Smoke/manual checks | Acceptance criteria |
|---|---|---|---|
| A1 core helpers | `py_compile`, `make tests`, `test_config.py`, `test_session.py`, `test_graceful.py` | `python tools/run-agent.py --show-model --agent recon` | CLI behavior unchanged; model/prompt/session payload logic covered; no runner logic in `config.py` |
| A2 rendering foundation | `py_compile`, `make tests`, `test_sinks.py`, `test_registry.py`, `test_snapshot_cache.py` | import `rendering.*` modules | `RenderContext`, sinks, registry, settings, and cache exist and are tested; no renderer migration required yet |
| A3 renderer migration | renderer unit tests plus fixture/golden tests for each migrated family | `--color never` and `--color always` smoke runs | migrated renderers handle known fixture events; fallback still works; plain/rich/textual destinations remain supported |
| A4 chat extraction | `py_compile`, `make tests`, sink/proxy tests | manual `make chat` or equivalent Textual smoke test | chat imports cleanly; RichLog output path works; known Textual threading pattern preserved |
| A5 runner/CLI extraction | `py_compile`, `make tests`, CLI smoke tests | run key Makefile target or mock phase flow | `tools/run-agent.py` is a thin wrapper; exit codes, transcript naming, auto-resume, and frontmatter repair behavior remain compatible |
| A6 events refactor | `test_base_event_loop.py`, `test_phase_event_loop.py`, `test_chat_event_loop.py` | phase and chat smoke tests | shared logic lives in `BaseEventLoop`; phase loop returns correct `RunResult`; chat loop remains multi-turn and long-lived |
| A7 `tools/AGENTS.md` | docs lint if available | manual review | architecture rules documented: wrappers, config boundary, renderers, sinks, snapshot cache, event loops, command interceptors, findings |
| B1 findings helpers | `test_frontmatter.py`, `test_finding_lookup.py` | run helper imports | shared helpers cover parsing, lookup, status dirs, next ID, slug/replacement helpers |
| B2 findings wrappers | tests for migrated commands | wrapper `--help` smoke tests | old script paths still work; implementations live under `tools/findings/`; no duplicated frontmatter parser remains in migrated scripts |
| B3 references | `make tests`, docs/link checks if available | Makefile/manual command checks | Makefile/docs references are updated only where needed; stable CLI paths preserved |

### Global acceptance after Epic A

```text
- `tools/run-agent.py` has no substantial logic; it delegates to `codecome.cli`.
- Phase mode supports plain terminal and Rich terminal rendering.
- Chat mode uses Textual/RichLog and shares renderer classes where applicable.
- Event loops are separated as `PhaseEventLoop` and `ChatEventLoop`.
- Shared SSE/session/dedup/permission logic lives in `BaseEventLoop`.
- CodeCome-specific command rendering is represented as `CommandExecutionInterceptor` implementations.
- Snapshot/diff state is isolated in `SnapshotCache`.
- Existing Makefile targets and script paths still work.
```

### Global acceptance after Epic B

```text
- Finding/itemdb helpers are shared under `tools/findings/`.
- Historical scripts remain as wrappers.
- No duplicated frontmatter parser remains in migrated scripts.
- Reports and indexes are generated as before.
```

---

## 12. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---:|---:|---|
| Import cycles during extraction | Medium | High | Small PRs, py_compile after each phase, keep wrappers |
| Renderer behavior regression | Medium | Medium | Migrate renderer families incrementally, keep input dict contract, add fixture tests |
| Rich/Textual behavior divergence | Medium | Medium | Use shared Rich render path with different sinks; test sinks with fake outputs |
| Plain output degradation | Medium | Medium | PlainSink and explicit plain branches remain supported; plain golden tests |
| Snapshot diff bugs | Medium | Medium | Isolate in SnapshotCache and add unit tests |
| Event loop regression | Medium | High | Delay BaseEventLoop until after runner/render split; add deterministic event-loop tests |
| Chat TUI freeze/regression | Medium | High | Preserve known Textual threading pattern, isolate sink/proxy changes carefully, manual smoke test |
| Makefile/script path breakage | Low | High | Keep thin wrappers permanently, add wrapper smoke tests |
| Findings migration affects reports | Medium | Medium | Move findings tools as separate epic with wrappers and itemdb fixture tests |
| False confidence from broad tests only | Medium | High | Require acceptance gates and focused tests per phase |

---

## 13. Open Questions

1. **Should the renderer classes be instantiated once per run or recreated per event?**
   Recommendation: instantiate once at startup with a shared `RenderContext`.

2. **Should `TextualRichLogSink` wrap `RichLog` directly or the existing thread-safe proxy?**
   Recommendation: wrap the existing thread-safe proxy initially to preserve the known-working Textual threading model.

3. **Should `emitters.py` survive after `RendererRegistry` exists?**
   Recommendation: keep it until events refactor is complete; remove only if the final dependency direction no longer needs it.

4. **Should `tools/AGENTS.md` be created in the same PR as the plan or during implementation?**
   Recommendation: create it early, ideally with the first implementation PR, so future agents follow the architecture while the migration is underway.

5. **Should findings/itemdb be moved before or after runner/rendering?**
   Recommendation: treat as independent Epic B. It is useful, but should not block the `run-agent.py` decomposition.

---

## 14. References

- [tool-renderers-plan.md](tool-renderers-plan.md) — original renderer design
- [chat-mode-plan.md](chat-mode-plan.md) — chat TUI architecture
- [migrate-to-opencode-serve.md](migrate-to-opencode-serve.md) — server migration
- [sync-recovery-plan.md](sync-recovery-plan.md) — session sync after SSE reconnect
- [todowrite-renderer-plan.md](todowrite-renderer-plan.md) — first per-tool renderer
- [apply-patch-renderer-plan.md](apply-patch-renderer-plan.md) — complex patch renderer
- [internal-read-suppression-plan.md](internal-read-suppression-plan.md) — read display suppression
- [reasoning-and-error-renderers-plan.md](reasoning-and-error-renderers-plan.md) — reasoning/error panel design
- [discover-opencode-default-model-plan.md](discover-opencode-default-model-plan.md) — model resolution from DB
- [restore-model-banner-plan.md](restore-model-banner-plan.md) — model banner display
