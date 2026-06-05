# Plan: `RenderOutput` Semantic Console Abstraction

## Goal

Replace repeated `HAVE_RICH` / local Rich imports / `_colors` fallback branches with a small semantic output abstraction that preserves rendering quality across all current CodeCome output destinations:

- Rich console output
- Textual RichLog output
- ANSI/plain console fallback

The abstraction should make callers express output intent, not backend mechanics.

Target call-site shape:

```python
from rendering.output import get_output, T

out = get_output(console)
out.header("CodeQL")
out.detail("Running CodeQL analysis...")
out.warn("CodeQL disabled - skipping.")
out.success("CodeQL: analysis completed")
out.error("CodeQL: FAILED")
out.segments(
    ("CodeQL:", T.ACCENT),
    (" skipped", T.WARNING),
    (" - no plan", T.DETAIL),
)
```

## Background

CodeCome already has a rendering subsystem under `tools/rendering/`:

- `rendering.dispatch` detects Rich availability and builds shared rendering contexts.
- `rendering.context.RenderContext` carries active runtime rendering state.
- `rendering.sink.RenderSink` abstracts destination writes.
- `PlainSink` writes to stdout.
- `RichConsoleSink` delegates to `rich.console.Console`.
- `TextualRichLogSink` delegates to Textual RichLog or a thread-safe proxy.
- Existing renderer classes branch through `self.rich` and `self.plain`.

This is a good foundation. The missing piece is a small semantic output facade for orchestration and CLI code that is not naturally represented as stream events or tool renderers.

## Problem

CodeCome currently repeats patterns like:

```python
if HAVE_RICH:
    from rich.rule import Rule
    from rich.text import Text
    console.print(Rule(title="CodeQL", style="cyan"))
else:
    import _colors as C
    print(C.header("CodeQL"))
```

And status variants like:

```python
if HAVE_RICH:
    from rich.text import Text
    console.print(Text(msg, style="bold yellow"))
else:
    import _colors as C
    print(C.warn(msg))
```

Current hotspots include:

- `tools/codecome/phase_1.py`
- `tools/codecome/harness.py`
- `tools/codecome/console.py`
- `tools/codecome.py` for non-runner CLI status output, later migration only
- selected files under `tools/phases/`, later migration only

The repetition creates several issues:

- Call sites know too much about Rich availability.
- Rich imports are scattered through procedural orchestration code.
- Plain ANSI fallback behavior is duplicated manually.
- Mixed-style output requires backend-specific branching.
- Visual semantics such as header, warning, detail, success, and failure are encoded as raw Rich style strings or `_colors` helper calls.
- It is hard to tune CodeCome visual language centrally.
- It is easy for Rich output and plain output to drift semantically.

## Decision

Implement Option 1: a semantic facade above the existing rendering context and sink system.

Name the abstraction `RenderOutput`.

Add:

```text
tools/rendering/output.py
```

Expose:

```python
get_output(console: Any) -> RenderOutput
RenderOutput
T
Tone
Segment
```

Use CodeCome semantic tone tokens as the canonical style API. Do not use Rich style strings as the internal API. Map semantic tones independently to Rich styles and ANSI constants.

## Non-Goals

- Do not remove `_colors.py`.
- Do not refactor every renderer in `tools/rendering/events/` or `tools/rendering/tools/` in the first pass.
- Do not change the `RenderSink` protocol in v1.
- Do not add destination-specific output systems outside `tools/rendering/`.
- Do not modify target source under `src/`.
- Do not introduce a full UI framework abstraction.
- Do not make `RenderOutput` responsible for event dispatch, transcript persistence, or prompt/session logic.
- Do not alter CodeCome phase behavior while migrating output calls.

## Design Principles

- Semantic first: call sites should say `warn`, `success`, `header`, or `detail`, not `yellow`, `green`, or `bold cyan`.
- Backend parity: Rich and ANSI are peer backends with independent mappings from semantic tones.
- Preserve quality: Rich output should continue using `Rule`, `Panel`, and segmented `Text` where those are currently used.
- Preserve fallback semantics: plain output should continue using `_colors` helpers for `ok`, `warn`, `fail`, and `info` where those helpers carry symbols or prefixes.
- Keep sinks simple: `RenderSink` remains a destination abstraction, while `RenderOutput` handles semantic formatting.
- Keep v1 small: migrate orchestration hot spots first, then consider expanding to root CLI tools and renderers.

## Architecture

`RenderOutput` should sit above `RenderSink`:

```text
caller -> RenderOutput -> RenderContext.sink -> stdout / Rich Console / Textual RichLog
```

The existing rendering context remains the composition point:

```python
ctx = _get_rendering_ctx(console)
out = RenderOutput(ctx)
```

The public factory keeps call sites simple:

```python
def get_output(console: Any) -> RenderOutput:
    return RenderOutput(_get_rendering_ctx(console))
```

`RenderOutput` should use `context.sink.mode` to choose rendering behavior:

- `plain`: use `_colors` and `sink.write_text()`.
- `rich`: build Rich renderables and use `sink.write()`.
- `textual`: build Rich renderables and use `sink.write()`.

Rich and Textual share the same renderable construction path.

## Module Layout

New module:

```text
tools/rendering/output.py
```

Potential future exports in `tools/rendering/__init__.py`:

```python
from rendering.output import RenderOutput, T, Tone, get_output
```

Exporting from `rendering.__init__` is optional for v1. Direct imports from `rendering.output` are acceptable and clearer.

## Types And Constants

Use named constants for tones to avoid magic strings in mixed-style calls.

Recommended implementation:

```python
from typing import Literal, TypeAlias

class T:
    PLAIN = "plain"
    HEADER = "header"
    SECTION = "section"
    DETAIL = "detail"
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    STRONG_ERROR = "strong_error"
    ACCENT = "accent"

Tone: TypeAlias = Literal[
    "plain",
    "header",
    "section",
    "detail",
    "info",
    "success",
    "warning",
    "error",
    "strong_error",
    "accent",
]

Segment: TypeAlias = tuple[str, Tone]
```

Do not use single-letter tone constants such as `T.W` or `T.E`. They make mixed lines harder to review.

## Tone Semantics

Initial tones:

- `T.PLAIN`: unstyled/default text.
- `T.HEADER`: major section or phase heading.
- `T.SECTION`: secondary heading or section label.
- `T.DETAIL`: de-emphasized supporting information, metadata, paths, transcript locations, finish reasons.
- `T.INFO`: neutral informational status.
- `T.SUCCESS`: successful status or completed gate.
- `T.WARNING`: warning, skipped state, soft failure, interrupted state, auto-retry notices.
- `T.ERROR`: error details or failed status.
- `T.STRONG_ERROR`: primary failure headline.
- `T.ACCENT`: important label inside a mixed line, usually the left-hand prefix.

Do not add new tones unless there are at least two expected call sites or the existing tone would misrepresent the semantics.

## Backend Tone Maps

Maintain independent semantic-to-backend maps.

Rich map:

```python
_RICH_TONES: dict[str, str | None] = {
    T.PLAIN: None,
    T.HEADER: "bold cyan",
    T.SECTION: "cyan",
    T.DETAIL: "dim",
    T.INFO: "cyan",
    T.SUCCESS: "green",
    T.WARNING: "yellow",
    T.ERROR: "red",
    T.STRONG_ERROR: "bold red",
    T.ACCENT: "bold cyan",
}
```

ANSI map:

```python
_ANSI_TONES: dict[str, str] = {
    T.PLAIN: "",
    T.HEADER: C.BOLD,
    T.SECTION: C.CYAN,
    T.DETAIL: C.DIM,
    T.INFO: C.CYAN,
    T.SUCCESS: C.GREEN,
    T.WARNING: C.YELLOW,
    T.ERROR: C.RED,
    T.STRONG_ERROR: C.BOLD_RED,
    T.ACCENT: C.BOLD_CYAN,
}
```

This design avoids translating Rich style strings into ANSI. Each backend maps the same semantic token to its own presentation.

## API

Initial API:

```python
class RenderOutput:
    def __init__(self, context: RenderContext) -> None: ...

    @property
    def rich(self) -> bool: ...

    @property
    def plain(self) -> bool: ...

    def header(self, title: str, *, tone: Tone = T.HEADER) -> None: ...
    def section(self, title: str, *, tone: Tone = T.SECTION) -> None: ...
    def separator(self, *, tone: Tone = T.PLAIN) -> None: ...
    def line(self, text: str, *, tone: Tone = T.PLAIN) -> None: ...
    def segments(self, *parts: Segment) -> None: ...
    def detail(self, text: str) -> None: ...
    def info(self, text: str) -> None: ...
    def warn(self, text: str) -> None: ...
    def success(self, text: str) -> None: ...
    def error(self, text: str, *, strong: bool = True) -> None: ...
    def panel(self, title: str, text: str, *, tone: Tone = T.ERROR) -> None: ...
```

Include `section()` in v1 if migration reveals simple text headings that should not become `Rule`. If no immediate call site needs it, implement only `header()` and reserve `section()` for later.

## Method Behavior

### `header(title, tone=T.HEADER)`

Rich/Textual:

```python
self.sink.write(Rule(title=title, style=_rich_tone(tone)))
```

Plain:

```python
self.sink.write_text(C.header(title))
```

Rationale: current high-quality Rich branch uses `Rule(title=...)`, while plain branch uses `C.header(...)`.

### `section(title, tone=T.SECTION)`

Rich/Textual:

```python
self.sink.write(Text(title, style=_rich_tone(tone)))
```

Plain:

```python
self.sink.write_text(C.colorize(title, _ansi_tone(tone)))
```

Use for text-only section labels, not major phase boundaries.

### `separator(tone=T.PLAIN)`

Rich/Textual:

```python
self.sink.write(Rule(style=_rich_tone(tone)))
```

Plain:

No-op for v1.

Rationale: current plain branches generally do not print bare separator lines. Adding dashed lines may increase noise.

### `line(text, tone=T.PLAIN)`

Rich/Textual:

```python
self.sink.write(Text(text, style=_rich_tone(tone)))
```

Plain:

```python
self.sink.write_text(C.colorize(text, _ansi_tone(tone)))
```

Use for raw styled lines without status symbols.

### `segments(*parts)`

Input:

```python
out.segments(
    ("CodeQL:", T.ACCENT),
    (" skipped", T.WARNING),
    (" - no plan", T.DETAIL),
)
```

Rich/Textual:

```python
text = Text()
for value, tone in parts:
    text.append(value, style=_rich_tone(tone))
self.sink.write(text)
```

Plain:

```python
self.sink.write_text("".join(C.colorize(value, _ansi_tone(tone)) for value, tone in parts))
```

Validation:

- Empty `parts` should write a blank line or no-op. Prefer no-op to avoid accidental blank lines.
- Empty segment text should be ignored.

### `detail(text)`

Equivalent to:

```python
self.line(text, tone=T.DETAIL)
```

Use for metadata such as model selection, transcript paths, finish reasons, retry counters, and explanatory hints.

### `info(text)`

Rich/Textual:

```python
self.line(text, tone=T.INFO)
```

Plain:

```python
self.sink.write_text(C.info(text))
```

Rationale: preserve current plain info symbol/prefix behavior.

### `warn(text)`

Rich/Textual:

```python
self.line(text, tone=T.WARNING)
```

Plain:

```python
self.sink.write_text(C.warn(text))
```

### `success(text)`

Rich/Textual:

```python
self.line(text, tone=T.SUCCESS)
```

Plain:

```python
self.sink.write_text(C.ok(text))
```

### `error(text, strong=True)`

Rich/Textual:

```python
tone = T.STRONG_ERROR if strong else T.ERROR
self.line(text, tone=tone)
```

Plain:

```python
self.sink.write_text(C.fail(text))
```

Rationale: plain fallback does not currently distinguish `red` and `bold red` in helper semantics. Keep `strong` for Rich quality and future ANSI distinction if needed.

### `panel(title, text, tone=T.ERROR)`

Rich/Textual:

```python
self.sink.write(Panel(Text(text, style=_rich_tone(tone)), title=title, border_style=_rich_border(tone)))
```

Plain:

```python
self.sink.write_text(C.header(title))
self.line(text, tone=tone)
```

Border style can use the same tone with `strong_error` normalized to `red` if needed.

## Helper Functions

Implement private helpers:

```python
def _rich_tone(tone: str) -> str | None:
    return _RICH_TONES.get(tone, _RICH_TONES[T.PLAIN])

def _ansi_tone(tone: str) -> str:
    return _ANSI_TONES.get(tone, _ANSI_TONES[T.PLAIN])

def _colorize(text: str, tone: str) -> str:
    return C.colorize(text, _ansi_tone(tone))
```

Unsupported tones should fall back to plain output rather than raising at runtime. Type checkers and tests should catch incorrect constants during development, but runtime output should remain robust.

## Import Strategy

Avoid importing Rich at module import time in `rendering.output.py`.

Use lazy imports inside Rich/Textual branches:

```python
if self.rich:
    from rich.text import Text
```

This keeps the module importable when Rich is unavailable.

Import `_colors` at module level because it is a local CodeCome utility and already handles `NO_COLOR`, TTY, and dumb terminal behavior.

## Relationship To `HAVE_RICH`

Callers using `RenderOutput` should not import or branch on `HAVE_RICH`.

Before:

```python
from rendering.dispatch import HAVE_RICH
```

After, if the file only needed `HAVE_RICH` for presentation, remove that import and use:

```python
from rendering.output import get_output, T
```

Some files may still need `HAVE_RICH` for console construction or non-output behavior. Do not remove those imports blindly.

## Migration Map

Recommended mappings:

```text
Rule(title="CodeQL", style="cyan")          -> out.header("CodeQL")
Rule(title=..., style="bold cyan")          -> out.header(...)
Rule(style="green")                         -> out.separator(tone=T.SUCCESS)
Rule(style="yellow")                        -> out.separator(tone=T.WARNING)
Rule(style="red")                           -> out.separator(tone=T.ERROR)
Rule(style="bold green")                    -> out.separator(tone=T.SUCCESS)
Text(msg, style="dim")                      -> out.detail(msg)
Text(msg, style="cyan")                     -> out.info(msg) or out.line(msg, tone=T.SECTION)
Text(msg, style="green")                    -> out.success(msg) if status, else out.line(msg, tone=T.SUCCESS)
Text(msg, style="yellow")                   -> out.warn(msg) if warning/skipped, else out.line(msg, tone=T.WARNING)
Text(msg, style="bold yellow")              -> out.warn(msg)
Text(msg, style="red")                      -> out.error(msg, strong=False)
Text(msg, style="bold red")                 -> out.error(msg)
Panel(Text(message, style="red"), ...)      -> out.panel(title, message, tone=T.ERROR)
print(C.header(title))                       -> out.header(title)
print(C.info(msg))                           -> out.info(msg)
print(C.warn(msg))                           -> out.warn(msg)
print(C.ok(msg))                             -> out.success(msg)
print(C.fail(msg))                           -> out.error(msg)
```

Choose semantic method by meaning, not by current color alone. For example, `Text(msg, style="yellow")` may be `out.warn(msg)` for warning/skipped states, but `out.line(msg, tone=T.WARNING)` if the caller intentionally does not want a plain-mode warning symbol.

## Implementation Phases

### Phase A: Add `RenderOutput`

Create `tools/rendering/output.py` with:

- license header matching repository style
- module docstring explaining semantic console output
- `T`, `Tone`, `Segment`
- `_RICH_TONES`
- `_ANSI_TONES`
- private tone lookup helpers
- `RenderOutput`
- `get_output(console)`

Do not migrate callers in this phase except tests.

### Phase B: Add Focused Tests

Create:

```text
tests/test_rendering_output.py
```

Use local test setup consistent with existing rendering tests:

```python
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
```

Test fixture helper:

```python
def _ctx(sink_mode="plain"):
    if sink_mode == "rich":
        from rich.console import Console
        sink = RichConsoleSink(Console(record=True, width=120))
    else:
        sink = PlainSink()
    return RenderContext(root=Path("/fake"), sink=sink, settings=RenderSettings(), cache=SnapshotCache())
```

Plain tests:

- `test_header_plain_includes_title`
- `test_info_plain_includes_message`
- `test_warn_plain_includes_message`
- `test_success_plain_includes_message`
- `test_error_plain_includes_message`
- `test_detail_plain_includes_message`
- `test_line_plain_includes_message`
- `test_segments_plain_preserves_order`
- `test_separator_plain_is_noop`
- `test_unknown_tone_plain_falls_back_to_unstyled_if_runtime_allows`

Rich tests:

- `test_header_rich_records_title`
- `test_separator_rich_records_without_error`
- `test_line_rich_records_text`
- `test_segments_rich_preserves_order`
- `test_panel_rich_records_title_and_body`
- `test_status_helpers_rich_record_text`

Textual-like test:

- Use a fake object with `write(renderable, expand=True)` and wrap it in `TextualRichLogSink`.
- Verify `RenderOutput.line()` and `RenderOutput.segments()` call the fake sink without requiring Textual.

### Phase C: Migrate `tools/codecome/phase_1.py`

This is the biggest hotspot and the best proof of value.

Initial import change:

```python
from rendering.output import get_output, T
```

Keep existing `rendering.dispatch` imports needed for event rendering and configuration:

```python
from rendering.dispatch import _get_rendering_ctx, configure_rendering, render_event
```

Only keep `HAVE_RICH` if any non-output logic still requires it after migration.

Inside output-heavy functions, create an output helper once near the top:

```python
out = get_output(console)
```

Recommended function-level migrations:

- `_run_codeql(console)`
- `_check_codeql_artifacts(console)`
- phase header emission around current line range where `Rule(title=f"Phase {phase_id}: {label}")` is printed
- auto-retry / auto-correction messages
- final phase completion / interruption / failure footers
- final Phase 1 completion line

Avoid deep incidental refactors. Keep control flow unchanged.

### Phase D: Migrate `tools/codecome/harness.py`

This file contains similar output logic for non-subphase phase runs.

Initial import change:

```python
from rendering.output import get_output, T
```

Migrate:

- phase header block
- auto-retry messages
- graceful completion messages
- frontmatter repair messages
- auto-resume messages
- final success/interrupted/failure footer

Keep behavior and message strings stable.

### Phase E: Migrate `tools/codecome/console.py`

Migrate `_emit_fatal_error()` carefully because it writes to stderr today.

Current behavior:

- Rich branch prints a panel through `console.print(...)` to stdout-like console destination.
- Always prints formatted failure to `sys.stderr`.

Decision for v1:

- Keep stderr print unchanged to avoid changing error routing.
- Optionally use `RenderOutput.panel()` for the Rich/display path if it preserves output destination.
- If this creates ambiguity around stderr vs stdout, skip this file in v1 and leave it as a known future migration.

Recommendation: migrate only if the output destination semantics are clearly preserved. Otherwise keep `_emit_fatal_error()` unchanged and document it as an exception.

### Phase F: Optional Root CLI Follow-Up

After the primary runner files are stable, consider migrating selected root CLI output in:

- `tools/codecome.py`
- `tools/phases/artifact_checks.py`
- thin wrapper implementation modules that print status lines

This is not required for v1.

## Migration Discipline

- Do not change message strings unless necessary.
- Do not alter return codes.
- Do not alter retry/resume logic.
- Do not alter transcript paths or event dispatch behavior.
- Do not replace complex Rich renderables in event/tool renderer classes unless the replacement is obviously equivalent.
- Do not mix `print(...)` and `out.*(...)` for the same output block unless stderr routing requires it.
- Use one `out = get_output(console)` per function or major block, not repeated calls before every line.

## Examples

### CodeQL Header

Before:

```python
if HAVE_RICH:
    from rich.rule import Rule
    from rich.text import Text
    console.print(Rule(title="CodeQL", style="cyan"))
else:
    import _colors as C
    print(C.header("CodeQL"))
```

After:

```python
out.header("CodeQL")
```

### Warning

Before:

```python
if HAVE_RICH:
    from rich.text import Text
    console.print(Text(msg, style="yellow"))
else:
    import _colors as C
    print(C.warn(msg))
```

After:

```python
out.warn(msg)
```

### Detail Line

Before:

```python
if HAVE_RICH:
    from rich.text import Text
    console.print(Text(main_line, style="dim"))
else:
    print(C.info(main_line))
```

After, if this is metadata and should not have a plain info symbol:

```python
out.detail(main_line)
```

After, if this is a neutral status item and should preserve `C.info()` behavior:

```python
out.info(main_line)
```

Choose based on meaning, not color.

### Mixed-Style Line

Before, likely backend-specific:

```python
if HAVE_RICH:
    from rich.text import Text
    text = Text()
    text.append("CodeQL:", style="bold cyan")
    text.append(" skipped", style="yellow")
    text.append(" - no plan", style="dim")
    console.print(text)
else:
    import _colors as C
    print(C.colorize("CodeQL:", C.BOLD_CYAN) + C.colorize(" skipped", C.YELLOW) + C.colorize(" - no plan", C.DIM))
```

After:

```python
out.segments(
    ("CodeQL:", T.ACCENT),
    (" skipped", T.WARNING),
    (" - no plan", T.DETAIL),
)
```

## Test Details

### Plain Mode Assertions

Because `_colors.py` disables ANSI when stdout is not a TTY or `NO_COLOR` is set, tests should not depend on escape sequences by default. Assert message text and, where stable, fallback symbols/prefixes.

Examples:

```python
out.warn("careful")
assert "careful" in capsys.readouterr().out
```

For semantic helpers using `_colors`, optionally assert known no-color prefixes if stable in the test environment:

```python
assert "[WARN]" in out
```

But avoid brittle tests that require ANSI escapes.

### Rich Mode Assertions

Use `Console(record=True, width=120)` behind `RichConsoleSink` and inspect `export_text()`.

Assertions should check exported visible text, not Rich object internals:

```python
console = sink.console
assert "CodeQL" in console.export_text()
```

This avoids coupling tests to exact Rich renderable classes except where the behavior is central.

### Textual-Like Assertions

Use a fake sink target:

```python
class FakeLog:
    def __init__(self):
        self.items = []
    def write(self, renderable, expand=True):
        self.items.append((renderable, expand))
```

Then:

```python
sink = TextualRichLogSink(FakeLog())
ctx = RenderContext(..., sink=sink, ...)
RenderOutput(ctx).line("hello", tone=T.INFO)
assert fake.items
```

## Validation Commands

During implementation:

```text
pytest tests/test_rendering_output.py
```

After migration of runner files:

```text
pytest tests/test_rendering_output.py tests/test_rendering_sinks.py tests/test_rendering_events.py
pytest tests/test_phase_1_codeql_plan_repair.py tests/test_phase_1_mid_turn_forgiveness.py
pytest tests/test_codecome_runner.py
```

Final local quality gate before commit or push:

```text
make tests
```

## Compatibility Checks

After migration, verify these manually or with focused tests if practical:

- Rich installed, normal terminal: phase headers still use rules.
- Rich unavailable or simulated unavailable: no import-time crash in `rendering.output`.
- `NO_COLOR=1`: plain output remains readable.
- Output piped to file: no raw Rich markup appears.
- Chat/Textual mode: output renderables still flow through the existing sink.
- Fatal errors still reach stderr where they did before.

## Risks And Mitigations

Risk: plain fallback output loses `C.ok`, `C.warn`, `C.fail`, or `C.info` prefixes.

Mitigation: implement status helpers using `_colors` helper functions in plain mode, not just `line(..., tone=...)`.

Risk: Rich output loses quality by replacing `Rule` or `Panel` with plain colored lines.

Mitigation: `header()`, `separator()`, and `panel()` must emit Rich renderables, not just styled text.

Risk: `detail()` vs `info()` changes plain output semantics.

Mitigation: choose `detail()` for metadata/de-emphasized lines and `info()` for neutral status messages that previously used `C.info()` intentionally.

Risk: hidden dependency cycles via `rendering.dispatch` importing `rendering.output` and `rendering.output` importing `rendering.dispatch`.

Mitigation: keep `rendering.output` imports lazy where needed. `get_output()` can import `_get_rendering_ctx` inside the function to avoid module-level cycles.

Risk: existing tests assert exact output strings.

Mitigation: run targeted phase/harness tests after migration and keep messages stable.

Risk: repeated `get_output(console)` object construction.

Mitigation: use one local `out` per function. If needed later, attach an output object to `RenderContext`, but do not do that in v1.

## Open Decisions

1. Whether `section()` should be included in v1.
2. Whether `separator()` in plain mode should remain a no-op or print a dashed line.
3. Whether `RenderOutput` should eventually be exposed as `ctx.output`.
4. Whether root CLI tools should migrate in the same PR or a follow-up.

Recommendations:

- Include `section()` only if an immediate migration site needs text-only headings.
- Keep plain `separator()` as a no-op in v1.
- Use `get_output(console)` in v1; consider `ctx.output` later.
- Migrate root CLI tools in a follow-up after runner/harness behavior is stable.

## Acceptance Criteria

The first implementation is complete when:

- `tools/rendering/output.py` exists and is covered by focused tests.
- `RenderOutput` supports semantic helpers and mixed-style `segments()`.
- Rich imports are lazy and do not break plain mode.
- At least `tools/codecome/phase_1.py` and `tools/codecome/harness.py` no longer contain repeated presentation-only `HAVE_RICH` branches for migrated blocks.
- Existing behavior and messages are preserved except for intentional cosmetic consolidation.
- Targeted rendering and phase tests pass.
- `make tests` passes before commit or push.

## Suggested Work Order

1. Add `tools/rendering/output.py`.
2. Add `tests/test_rendering_output.py`.
3. Run `pytest tests/test_rendering_output.py`.
4. Migrate `_run_codeql()` and `_check_codeql_artifacts()` in `tools/codecome/phase_1.py`.
5. Run CodeQL/phase-1 related tests.
6. Migrate phase header and footer blocks in `tools/codecome/phase_1.py`.
7. Migrate analogous blocks in `tools/codecome/harness.py`.
8. Run targeted phase/harness tests.
9. Decide whether `tools/codecome/console.py` is safe to migrate without changing stderr behavior.
10. Run `make tests`.
11. If successful, consider a follow-up plan for root CLI output in `tools/codecome.py` and `tools/phases/artifact_checks.py`.
