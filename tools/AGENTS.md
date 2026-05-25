# Architecture Guidelines for `tools/`

## Directory layout — what goes where

```
tools/
├── run-agent.py                  # Thin wrapper (12 lines) → codecome.cli.main()
├── codecome.py                   # Workspace validation CLI (check/status/next-id)
│
├── codecome/                     # Core runner and configuration
│   ├── cli.py                    #   main(), build_parser() — runtime entry point
│   ├── cli_render.py             #   HAVE_RICH, build_console, render_event, _get_rendering_ctx
│   ├── config.py                 #   env, codecome.yml, prompt, model, thinking resolution
│   ├── session.py                #   OpenCode HTTP: create session, send prompt
│   ├── runner.py                 #   _consume_events, _run_single_attempt
│   ├── graceful.py               #   phase completion checks, resume prompt builders
│   ├── transcript.py             #   transcript path/open/close helpers
│   └── version.py                #   OpenCode version checks
│
├── rendering/                    # Tool and event rendering
│   ├── base.py                   #   BaseRenderer (sink, rich, plain properties)
│   ├── context.py                #   RenderContext (root, sink, settings, cache)
│   ├── settings.py               #   RenderSettings (20+ tunables from env vars)
│   ├── cache.py                  #   SnapshotCache (file content snapshots for diffs)
│   ├── sink.py                   #   RenderSink protocol + Plain/Rich/Textual sinks
│   ├── registry.py               #   RendererRegistry (dispatch by event type / tool name)
│   ├── events.py                 #   Event renderer classes (StepStart, Text, Error, …)
│   ├── utils.py                  #   Shared helpers (path, lexer, diff, read framing)
│   ├── tools/                    #   Tool renderer classes
│   │   ├── base.py               #     ToolRenderer, FallbackToolRenderer
│   │   ├── read.py / write.py / edit.py / glob.py / grep.py
│   │   ├── command.py            #     CommandRenderer (bash) with interceptor chain
│   │   ├── apply_patch.py / todo.py / task.py / skill.py / permissions.py
│   │   └── interceptors/         #     CommandExecutionInterceptor implementations
│   │       ├── sandbox_bootstrap.py
│   │       ├── rtk_read.py / rtk_grep.py / shell_listing.py
│   │       └── base.py           #     Interceptor protocol
│
├── events/                       # SSE event consumption
│   ├── base.py                   #   BaseEventLoop (shared: filters, permissions, sync, dedup)
│   ├── phase_loop.py             #   PhaseEventLoop (single-session → RunResult)
│   ├── chat_loop.py              #   ChatEventLoop (multi-turn chat)
│   ├── sse_client.py             #   SseClient (raw SSE stream + reconnect)
│   ├── state_tracker.py          #   StateTracker (delta → finalized part)
│   └── emitters.py               #   emit_event() bridge
│
├── chat/                         # Interactive chat TUI (Textual)
│   ├── app.py                    #   _ChatApp, TextualConsoleProxy, render/log helpers
│   ├── harness.py                #   _run_chat_mode() entry point
│   └── debug.py                  #   Chat-specific debug logging
│
├── opencode/                     # opencode serve lifecycle
│   └── serve.py                  #   ServerRunner (start, stop, health check)
│
├── findings/                     # Finding / itemdb tooling (future consolidated package)
│
├── _colors.py                    # Shared ANSI color and symbol utilities
├── gate-check.py                 # Phase readiness gates
├── check-frontmatter.py          # Frontmatter validation
├── sandbox-bootstrap.py          # Sandbox environment setup
├── run-sweep.py                  # Batch file sweeps
├── list-findings.py / create-finding.py / move-finding.py / …   # Script wrappers
└── mock-llm-*.py / mock-llm-scripts/                             # Test infrastructure
```

## Rules

### 1. Historical scripts are thin wrappers

Standalone scripts at the `tools/` root (e.g. `create-finding.py`, `list-findings.py`) should be thin wrappers that delegate to their respective packages. Their implementation lives in the package, not the script.

Example (`tools/run-agent.py`):
```python
from codecome.cli import main
if __name__ == "__main__":
    raise SystemExit(main())
```

### 2. `codecome/config.py` is configuration only — no execution

`config.py` resolves env vars, `codecome.yml`, prompt extras, model/variant/thinking, and color modes. It must NOT contain:
- Server start/stop
- Session creation
- Prompt submission
- Phase loops
- Retry/resume logic
- Phase completion checks

### 3. Event loops live under `tools/events/`

- `BaseEventLoop` owns shared SSE/session mechanics (filtering, permissions, sync, dedup, headers).
- `PhaseEventLoop` (in `phase_loop.py`) extends it for single-session consumption.
- `ChatEventLoop` (in `chat_loop.py`) extends it for multi-turn chat.
- Never add new event loop classes outside `tools/events/`.

### 4. Renderers live under `tools/rendering/`

- Event renderers go in `rendering/events.py`, inheriting `EventRenderer`.
- Tool renderers go in `rendering/tools/`, inheriting `ToolRenderer`.
- Renderers receive **normalized dict** events/tool states — do not introduce custom event objects.
- Rich and Textual renderers may emit arbitrary Rich renderables (Panel, Group, Text, Table, Syntax, Rule, …) through a `RenderSink`. The sink abstracts *where* output goes; it does not restrict *what* renderers can draw.

### 5. Sinks: three destinations, one code path

- `PlainSink` — plain strings to stdout (no Rich dependency).
- `RichConsoleSink` — delegates to `rich.console.Console`.
- `TextualRichLogSink` — delegates to a Textual RichLog or thread-safe proxy.

Rich and Textual renderers share the same `render()` code path; only the sink differs. Use `self.rich` / `self.plain` properties from `BaseRenderer` to branch.

### 6. Snapshot/diff state belongs in `SnapshotCache`

File content snapshots used by Write/Edit/ApplyPatch renderers for diff computation must live in `rendering/cache.SnapshotCache`. Do not introduce new module-level globals for caching.

### 7. Command-specific rendering uses `CommandExecutionInterceptor`

Specialised rendering for bash invocations (sandbox-bootstrap JSON, rtk read/grep, rg, ls, find, tree) is implemented as `CommandExecutionInterceptor` implementations. The `CommandRenderer` has a lazy interceptor chain. New interceptors go in `rendering/tools/interceptors/`.

### 8. Finding/itemdb helpers live under `tools/findings/`

Frontmatter parsing, finding ID lookup, status directory constants, slug helpers, and finding file iteration belong in `tools/findings/frontmatter.py` or sibling modules. Do not duplicate these in standalone scripts.

### 9. Dependency direction

Packages should depend downward, not sideways:
```
run-agent.py → codecome/  →  (none)
            → events/     →  (none)
            → rendering/  →  codecome/
            → chat/       →  codecome/, events/

codecome/   → events/, rendering/ (lazy imports only in execution paths)
events/     →  (stdlib only, except sse_client ↔ base)
rendering/  →  codecome/
chat/       →  codecome/, events/
```

Avoid circular imports. When two packages need each other, prefer callable injection (as done with `render_event_fn` in the runner) or lazy imports inside function bodies.

### 10. Testing

- New renderers need focused unit tests with fixture inputs and recording sinks.
- Event loops are tested with deterministic event generators — not live OpenCode servers.
- CLI and wrapper compatibility is verified with `--help` and `--show-model` smoke tests.
- Thin wrappers must remain thin — their only responsibility is delegation.
