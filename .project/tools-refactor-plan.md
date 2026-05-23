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
└── mock_llm_scripts/             6 JSON files
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
│   │   ├── command.py                  # CommandRenderer for bash/tool command execution
│   │   ├── sandbox.py                  # sandbox rendering helpers/interceptor support
│   │   ├── task.py                     # TaskRenderer
│   │   └── skill.py                    # SkillRenderer
│   └── command_interceptors/
│       ├── __init__.py
│       ├── base.py                     # CommandExecutionInterceptor protocol/base
│       ├── sandbox_bootstrap.py        # sandbox-bootstrap / make sandbox-* renderer
│       ├── rtk_read.py                 # rtk read / cat/head/tail equivalent rendering
│       ├── rtk_grep.py                 # rtk grep / rg equivalent rendering
│       └── shell_listing.py            # ls/find/tree listing rendering
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
├── codecome.py                         # unchanged initially
├── check-frontmatter.py                # unchanged initially
├── list-risk-files.py                  # unchanged initially
├── script-to-asciinema.py              # unchanged
├── mock-llm-server.py                  # unchanged
├── mock-llm-parity.py                  # unchanged
└── mock_llm_scripts/                   # unchanged
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

### Pre-migration baseline

```bash
make tests
python tools/run-agent.py --show-model --agent recon
```

If practical, also run a small/mock phase target or an existing recorded/mock OpenCode flow.

### Per-phase checks

After each phase:

```bash
python -m py_compile $(find tools -name '*.py' -not -path '*/.venv/*')
make tests
python tools/run-agent.py --show-model --agent recon
```

Additional phase-specific checks:

```bash
# After rendering changes
python tools/run-agent.py --show-model --agent recon --color never
python tools/run-agent.py --show-model --agent recon --color always

# After chat extraction
# Run a chat smoke test if Textual is installed and a lightweight manual check is acceptable.

# After events changes
# Run both phase mode and chat mode smoke tests.

# After findings changes
tools/create-finding.py "Test finding"
tools/list-findings.py
tools/move-finding.py CC-XXXX REJECTED
tools/render-index.py
tools/render-report.py
```

### Tests to add

- `SnapshotCache`: set/get/invalidate/reread behavior.
- `RendererRegistry`: dispatch by event type and tool name.
- `CommandExecutionInterceptor`: command matching and fallback ordering.
- `RenderSink`: plain/rich/textual sink smoke behavior.
- `BaseEventLoop`: session filtering, idle detection, permission handling, dedup.
- `findings/frontmatter.py`: frontmatter parsing and finding lookup.

---

## 11. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---:|---:|---|
| Import cycles during extraction | Medium | High | Small PRs, py_compile after each phase, keep wrappers |
| Renderer behavior regression | Medium | Medium | Migrate renderer families incrementally, keep input dict contract |
| Rich/Textual behavior divergence | Medium | Medium | Use shared Rich render path with different sinks |
| Plain output degradation | Medium | Medium | PlainSink and explicit plain branches remain supported |
| Snapshot diff bugs | Medium | Medium | Isolate in SnapshotCache and add unit tests |
| Event loop regression | Medium | High | Delay BaseEventLoop until after runner/render split; add tests first where possible |
| Chat TUI freeze/regression | Medium | High | Preserve known Textual threading pattern, isolate sink/proxy changes carefully |
| Makefile/script path breakage | Low | High | Keep thin wrappers permanently |
| Findings migration affects reports | Medium | Medium | Move findings tools as separate epic with wrappers |

---

## 12. Open Questions

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

## 13. References

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
