# Architecture Guidelines for `tools/`

## Directory layout — what goes where

```
tools/
├── run-agent.py                  # Thin wrapper (12 lines) → codecome.cli.main()
├── codecome.py                   # Workspace validation CLI (check/status/next-id)
│
├── codecome/                     # Core runner and configuration
│   ├── cli.py                    #   main(), build_parser() — parse args + dispatch
│   ├── console.py                #   build_console, _emit_fatal_error (CLI helpers)
│   ├── harness.py                #   run_phase_mode() — retry/resume loop
│   ├── config.py                 #   ROOT, env, codecome.yml, prompt, model, thinking
│   ├── session.py                #   OpenCode HTTP: create session, send prompt
│   ├── runner.py                 #   _consume_events, _run_single_attempt
│   ├── transcript.py             #   Transcript class (open/write_event/close)
│   └── version.py                #   OpenCode version checks
│
├── phases/                       # Phase-specific logic
│   └── completion.py             #   phase completion checks, resume prompt builders
│
├── rendering/                    # Tool and event rendering
│   ├── base.py                   #   BaseRenderer (sink, rich, plain properties)
│   ├── context.py                #   RenderContext (root, sink, settings, cache)
│   ├── dispatch.py               #   HAVE_RICH, _get_rendering_ctx, render_event
│   ├── settings.py               #   RenderSettings (20+ tunables from env vars)
│   ├── cache.py                  #   SnapshotCache (file content snapshots for diffs)
│   ├── sink.py                   #   RenderSink protocol + Plain/Rich/Textual sinks
│   ├── registry.py               #   RendererRegistry (dispatch by event type / tool name)
│   ├── utils.py                  #   Shared helpers (path, lexer, diff, read framing)
│   ├── events/                   #   Event renderer classes (one per family)
│   │   ├── base.py               #     EventRenderer base + finish constants
│   │   ├── step_start.py / step_finish.py / text.py / reasoning.py
│   │   ├── tool_use.py / error.py / unknown.py
│   │   ├── session_status.py / session_diff.py / server.py
│   │   ├── message.py / subagent.py
│   │   └── __init__.py           #     Re-exports all symbols
│   └── tools/                    #   Tool renderer classes
│       ├── base.py               #     ToolRenderer, FallbackToolRenderer
│       ├── read.py / write.py / edit.py / glob.py / grep.py
│       ├── apply_patch.py / todo.py / task.py / skill.py / permissions.py
│       └── command/              #     CommandRenderer + interceptors
│           ├── __init__.py       #       CommandRenderer (bash) with interceptor chain
│           └── interceptors/     #       CommandExecutionInterceptor implementations
│               ├── base.py       #         Interceptor protocol
│               ├── sandbox_bootstrap.py
│               ├── rtk_read.py / rtk_grep.py / shell_listing.py
│               └── __init__.py
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
│   ├── harness.py                #   run_harness() entry point
│   └── debug.py                  #   Chat-specific debug logging
│
├── opencode/                     # opencode serve lifecycle
│   └── serve.py                  #   ServerRunner (start, stop, health check)
│
├── findings/                     # Finding / itemdb tooling
│   ├── __init__.py               #   Package re-exports, _colors exposure
│   ├── constants.py              #   ROOT, FINDINGS_ROOT, FindingsContext, regexes
│   ├── frontmatter.py            #   YAML frontmatter parsing and replacement
│   ├── ids.py                    #   Finding ID generation, lookup, iteration
│   ├── create.py                 #   create_finding() implementation
│   ├── move.py                   #   move_finding() implementation
│   ├── listing.py                #   load_findings(), filter_eligible_for_exploit()
│   ├── evidence.py               #   create_evidence() implementation
│   ├── package.py                #   discover_files(), create_bundle()
│   ├── render_report.py          #   render_report() implementation
│   ├── render_index.py           #   render_index() implementation
│   ├── checks.py                 #   Frontmatter validation logic
│   └── checks_entry.py           #   check-frontmatter CLI entrypoint
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

- Event renderers go in `rendering/events/`, one module per renderer family, inheriting `EventRenderer`.
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

Specialised rendering for bash invocations (sandbox-bootstrap JSON, rtk read/grep, rg, ls, find, tree) is implemented as `CommandExecutionInterceptor` implementations. The `CommandRenderer` has a lazy interceptor chain. New interceptors go in `rendering/tools/command/interceptors/`.

### 8. Finding/itemdb helpers live under `tools/findings/`

Frontmatter parsing, finding ID lookup, status directory constants, slug helpers, and finding file iteration belong in `tools/findings/` sibling modules. Do not duplicate these in standalone scripts.

#### `FindingsContext` — dependency injection for filesystem paths

Implementation functions in `findings/` that need filesystem paths accept a `FindingsContext` (or individual keyword arguments with defaults from `findings.constants`). The context is constructed by the **wrapper script** from its module-level constants and passed explicitly.

```python
# In findings/constants.py
@dataclass(frozen=True)
class FindingsContext:
    root: Path
    findings_root: Path
    evidence_root: Path
    ...
    @classmethod
    def default(cls) -> FindingsContext: ...

# In findings/create.py (implementation)
def create_finding(args, *, ctx: Optional[FindingsContext] = None) -> Path:
    ctx = ctx if ctx is not None else FindingsContext.default()
    ...
    finding_id = args.id or next_finding_id(findings_root=ctx.findings_root)

# In create-finding.py (wrapper)
ROOT = Path(__file__).resolve().parents[1]
FINDINGS_ROOT = ROOT / "itemdb" / "findings"
TEMPLATE_PATH = ROOT / "templates" / "finding.md"

def create_finding(args):
    ctx = FindingsContext(root=ROOT, findings_root=FINDINGS_ROOT, template_path=TEMPLATE_PATH, ...)
    return _create_finding(args, ctx=ctx)
```

This pattern keeps implementation code **test-agnostic**: it never inspects `sys.modules`, never scans for wrapper modules, and never knows about test patching. Wrappers own the responsibility of wiring constants to implementations.

### 9. No test-awareness in implementation code

Implementation modules under `tools/findings/` (and all other packages) must **never**:
- Scan `sys.modules` to find wrapper modules or patched constants.
- Use `__import__()` to dynamically resolve a wrapper by name.
- Inspect `__file__` attributes of other modules to identify callers.
- Contain any logic whose sole purpose is to accommodate test monkeypatching.

If a function needs a configurable path or constant, accept it as a parameter with a sensible default from `findings.constants`. The wrapper script is responsible for passing the correct value.

**Anti-pattern** (never do this):
```python
def _get_wrapper():
    for mod in sys.modules.values():
        if getattr(mod, "__file__", "").endswith("create-finding.py"):
            return mod
```

**Correct pattern**:
```python
def create_finding(args, *, ctx=None):
    ctx = ctx or FindingsContext.default()
    # use ctx.findings_root, ctx.template_path, etc.
```

### 10. Dependency direction

Packages should depend downward, not sideways:
```
run-agent.py → codecome/  →  (none)
            → events/     →  (none)
            → rendering/  →  codecome/
            → chat/       →  codecome/, events/

codecome/   → events/, rendering/, phases/ (lazy imports only in execution paths)
phases/     →  codecome/ (config only)
events/     →  (stdlib only, except sse_client ↔ base)
rendering/  →  codecome/ (config only), _colors
chat/       →  codecome/, events/
```

Avoid circular imports. When two packages need each other, prefer callable injection (as done with `render_event_fn` in the runner) or lazy imports inside function bodies.

### 11. Testing

- New renderers need focused unit tests with fixture inputs and recording sinks.
- Event loops are tested with deterministic event generators — not live OpenCode servers.
- CLI and wrapper compatibility is verified with `--help` and `--show-model` smoke tests.
- Thin wrappers must remain thin — their only responsibility is delegation.
