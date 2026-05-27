# Chat Mode + Textual: Postmortem and Maintenance Guide

**Status:** Final
**Date:** 2026-05-22
**Scope:** `tools/run-agent.py` (`_ChatApp`, `TextualConsoleProxy`), `tools/events/chat_loop.py`
**Audience:** Anyone touching the `--chat` mode TUI code, or upgrading Textual / Python

---

## TL;DR

The interactive `--chat` mode (the Textual TUI launched by `make chat`) sits inside a **narrow, empirically-verified safe envelope** for Textual cross-thread message dispatch on the versions we ship with (**Textual 8.2.6 + Python 3.14.5**). Patterns that the Textual docs imply should work — multiple `Message` subclasses, multiple `@on(...)` handlers, messages with optional fields, multiple `set_interval` callbacks — were observed to **silently freeze Textual's main event loop** when combined inside the real `_ChatApp`, even though the same patterns pass in isolated minimal repros.

**Before changing anything in this area, read [§5 Forbidden patterns](#5-forbidden-patterns-and-why) and [§7 Safe extension recipes](#7-safe-extension-recipes).**

---

## 1. Symptoms we saw

The repeated failure mode was always the same:

1. `make chat` (or `make chat DEBUG=1`) starts the process.
2. Pre-TUI output appears: opencode serve starts, session is created.
3. Textual enters its alternate-screen buffer (terminal "goes black").
4. **The screen stays black forever.** No banner, no widgets visible.
5. The Python process is alive (background threads keep running, the SSE consumer keeps receiving events). The user has to kill the process from another terminal.

When `--debug` is enabled, the debug log under `tmp/chat-debug-<pid>-<ts>.log` shows the **decisive evidence**:

- Background threads (`asyncio_0`, `asyncio_1`, `codecome-chat-consumer`) keep producing log lines indefinitely.
- `post_message(...)` calls from background threads keep firing.
- **Zero** `_heartbeat: tick #N` lines (the `set_interval(1.0, _heartbeat)` canary never fires).
- **Zero** `_on_render_message: ...` lines (the `@on(RenderMessage)` handler never fires).

In short: **Textual's main asyncio event loop on `MainThread` stops processing scheduled callbacks** after `on_mount` returns. Background concurrency is fine; the main loop is dead.

The fact that the heartbeat (a plain `set_interval` callback, nothing to do with Messages) does NOT fire is the smoking gun: this isn't "Messages aren't dispatched", it's "the main loop is not making forward progress on any scheduled callback". Yet the loop is not deadlocked in any visible way — no traceback, no error.

---

## 2. Environment

- Textual `8.2.6`
- Rich `14.x`
- Python `3.14.5` (installed via Homebrew on macOS arm64)
- Terminal: macOS Terminal.app (the symptom was reproducible across different LLM provider/model combos, ruling out anything related to opencode response payloads)

We were unable to fully isolate the root cause to a Textual or CPython 3.14 bug. Minimal `App.run_test()` Pilot repros of every "broken" pattern PASSED outside the real `_ChatApp`. Inside the real app, the same patterns reliably froze the main loop. The most plausible explanation we have is a subtle interaction between Textual's startup ordering, the asyncio thread pool, and one or more of our app-side concurrency choices — but we did not find the precise trigger and stopped chasing it once we had a working envelope.

---

## 3. The bisection that produced the working architecture

We rebuilt `_ChatApp` from scratch as a 5-step ladder, each step adding one piece of complexity and tested via `make chat DEBUG=1`. The matrix below is the gold record of what is safe and what is not on this Textual/Python combination.

| Step | Δ from previous | Result |
|------|-----------------|--------|
| 1    | Bare TUI: `compose()` yielding `RichLog`/`Input`/`Footer`, `on_mount` writing one line | ✅ works |
| 2    | + start `opencode serve` and create a session in the chat harness (still bare ChatApp) | ✅ works |
| 3    | + `TextualConsoleProxy` + inner `RenderMessage(Message)` + `@on(RenderMessage)` handler + a one-shot `set_timer` test post | ✅ works (handler fires) |
| 4    | + raw daemon SSE consumer thread (`chat_loop.start_consumer`) + **synchronous** `chat_loop.send_prompt(...)` blocking inside `on_mount` | ✅ works (model output streams in) |
| 4a   | + `set_interval(1.0, _heartbeat)` canary | ✅ works (ticks fire) |
| 4b   | sync `send_prompt` → `@work(thread=True) _send_initial_prompt` | ✅ works |
| **4c** | + second Message subclass `StateMessage(Message)` + `@on(StateMessage)` handler | ❌ **freezes** |
| 4c-fix | merge `RenderMessage` + `StateMessage` into a single `ChatMessage` class with a `kind` discriminator, single `@on(ChatMessage)` handler | ❌ **freezes** |
| 4c-min | revert class structure to Step 4b's single one-arg `RenderMessage`, but post one extra `RenderMessage(Text("[probe:idle]"))` directly from the consumer's `_render_and_log` for state events | ✅ works |
| 4c-alt | extend `RenderMessage.__init__` to `(renderable=None, state=None, detail=None)` with state branching in the handler | ❌ **freezes** |
| 4c-poll | revert message class to one-arg; add a second `set_interval(0.1, _poll_state)` to poll a `threading.Lock`-protected pending-state slot | ❌ **freezes** |
| **Final** | revert all of the above, then add `@work(thread=True) _send_prompt` + restored `on_input_submitted` (these short-lived workers only fire on user actions; they are isomorphic in shape to the proven-good `_send_initial_prompt`) | ✅ works |

The "Final" row is what now lives in `tools/run-agent.py`. Every ❌ row above is a **forbidden pattern** for this code path until we either upgrade Textual/Python or find the actual root cause.

---

## 4. The architecture that works

Documented in code under the `_ChatApp` class docstring; reproduced here for visibility.

```
make chat
  └─ run-agent.py --chat ...                            (main thread)
        ├─ ServerRunner.start()                         start opencode serve
        ├─ _create_chat_session()                       POST /session
        └─ ChatApp(...).run()                           Textual main loop

                                                        (main thread / asyncio loop)
                                                            │
                                          on_mount ─────────┤
                                            │ query widgets │
                                            │ banner write  │
                                            │ set_interval(1.0, _heartbeat)
                                            │
                                            │ chat_loop.start_consumer(_render_and_log)
                                            │                       │
                                            │                       ▼  (raw daemon thread)
                                            │                 _consumer_worker
                                            │                       │ for event in SseClient.events():
                                            │                       │   _render_and_log(...)
                                            │                       │     ├─ post_message(RenderMessage(Text("[idle/busy]")))   ─┐
                                            │                       │     └─ render_event(console_proxy, ...)                    │
                                            │                       │           └─ console_proxy.print(...)                      │
                                            │                       │                └─ post_message(RenderMessage(renderable))──┤
                                            │                                                                                    │
                                            │ _send_initial_prompt(text) ── @work(thread=True) ── (Textual-managed thread)        │
                                            │                                  HTTP POST /session/{id}/prompt_async (~150 ms)    │
                                            │                                  └─ on failure: _post_error_renderable() ──────────┤
                                            │                                                                                    │
                                            │ ... user types and submits Input ...                                                │
                                            │                                                                                    │
                                            └─ on_input_submitted ── _send_prompt(text) ── @work(thread=True) ──                  │
                                                                                            HTTP POST /session/{id}/prompt_async  │
                                                                                            └─ on failure: _post_error_renderable │
                                                                                                                                  │
                                          @on(RenderMessage) _on_render_message ◄─────────────────────────────────────────────────┘
                                            └─ self.rich_log.write(message.renderable)
```

### Architectural rules

The class docstring of `_ChatApp` lists these in code:

1. **Long-lived consumer = raw daemon thread.** Textual's `@work(thread=True)` is documented for short-lived blocking tasks (the weather-app pattern in [Workers guide](https://textual.textualize.io/guide/workers/)). Using it for an infinite SSE consumer loop froze the main loop. Stick to `chat_loop.start_consumer(...)` (which is also what non-interactive phase mode uses).

2. **Short-lived blocking HTTP = `@work(thread=True)`.** This is the docs-canonical pattern. Two workers in the chat app: `_send_initial_prompt` and `_send_prompt`. Each fires once, makes one HTTP POST, exits.

3. **All cross-thread UI writes go through `RenderMessage(renderable)`** — single one-argument inner-`Message` subclass, single `@on(RenderMessage)` handler, single one-liner body (`self.rich_log.write(message.renderable)`). The proxy posts these from the consumer thread; worker errors post a `RenderMessage(Panel(...))` via `_post_error_renderable`. Everything funnels through one path.

4. **`_render_and_log` mirrors phase mode (parity).** Per-event: write JSON to `transcript_fp` → if `--debug` mirror raw JSON to the chat-debug log file (NOT stderr, which Textual owns) → suppress `reasoning` when thinking is off → call `render_event(...)` (the same dispatcher non-chat uses). No chat-specific filters or markers. State cues come from `render_session_status` printing `session status: busy/idle` through the normal proxy path.

5. **No Input enable/disable toggling from outside `on_input_submitted`.** Doing so required a second `set_interval` polling timer (poller for state from bg threads), which broke dispatch. The Input stays enabled at all times. The "Thinking…" UX is sacrificed; idle/busy is communicated by `render_session_status` printing `session status: busy/idle` in the normal render pipeline (parity with phase mode).

6. **Transcript jsonl is mandatory.** The chat harness opens `tmp/last-chat-<YYYYMMDD-HHMMSS>-pid<pid>.jsonl` line-buffered before constructing `ChatApp`, passes the file handle in via the `transcript_fp` constructor argument, and closes it in the `finally` block. After `app.run()` returns, the outer console prints a `Chat session ended` summary plus the `transcript: tmp/last-chat-...` path (parity with phase mode's per-attempt jsonl + final summary).

7. **Bottom-bar modeline + heartbeat.** The heartbeat (`set_interval(1.0, _heartbeat)`) updates a `Static` widget (id `modeline`) passed as the leftmost child of `Footer` in `compose`. The widget displays `● | provider/model | ↑in ↓out | $cost` with a pulse icon alternating `●`/`◌` each tick. Data comes from `_modeline_info` (atomically refreshed by `_render_and_log` on every `message.updated` event). The heartbeat also writes `_heartbeat: tick #N` to the debug log when `--debug` is set. No second timer, no new handlers — single set_interval doing double duty.

---

## 5. Forbidden patterns (and why)

Each of these was bisected to a black screen + dead main loop in the real `_ChatApp`. Do not (re-)introduce them without a fresh bisection — and if you do find one of them works, **please update this document**.

### 5.1 Multiple `Message` subclasses with multiple `@on(...)` handlers

```python
# DO NOT DO THIS:
class RenderMessage(Message): ...
class StateMessage(Message): ...

@on(RenderMessage)
def _on_render(self, m): ...

@on(StateMessage)
def _on_state(self, m): ...
```

Observed in Step 4c. Main loop dies after `on_mount`.

**Safe alternative:** keep one Message class. Use marker-renderables for sub-categories of events (see [§7.1](#71-add-a-new-cross-thread-render-channel)).

### 5.2 Renaming the Message subclass or changing its `__init__` signature

```python
# DO NOT DO THIS:
class ChatMessage(Message):                            # rename
    def __init__(self, kind, renderable=None, ...): ... # multi-field

# OR THIS:
class RenderMessage(Message):
    def __init__(self, renderable=None, state=None, ...):  # optional fields
        ...
```

Observed in Steps 4c-fix and 4c-alt. Both froze.

**Safe alternative:** `RenderMessage(renderable)` — strictly one positional argument. If you need to attach metadata, encode it inside the renderable (e.g. a tagged `Text` or a custom Rich renderable that carries extra info).

### 5.3 Adding a second `set_interval` callback

```python
# DO NOT DO THIS:
self.set_interval(1.0, self._heartbeat)
self.set_interval(0.1, self._poll_state)   # second timer => freeze
```

Observed in Step 4c-poll. Main loop never fires either timer.

**Safe alternative:** one `set_interval` (the heartbeat). If you need periodic main-thread work, fold it into `_heartbeat` (which runs once per second). For sub-second responsiveness, find a different mechanism — e.g. send a `RenderMessage` from the bg thread to wake up the dispatcher.

### 5.4 Toggling `Input.disabled` / `Input.placeholder` from outside the input handler

Required a `_poll_state` second `set_interval` timer to dispatch idle/busy state from the bg thread to the main thread. See §5.3.

**Safe alternative:** leave the Input always enabled. `render_session_status` already prints `session status: busy/idle` through the normal render pipeline, which is the same cue phase mode emits, so users still get the signal — just not as widget state.

### 5.5 Long-lived `@work(thread=True)` workers (infinite loops)

```python
# DO NOT DO THIS:
@work(thread=True)
def _run_sse_consumer(self):
    while True:
        # consume SSE forever
        ...
```

Observed in an early Step 5 attempt. The infinite worker froze main-loop progress somehow (we never pinned down whether Textual awaits worker completion in a place that blocks the main loop, but the symptom is reliable).

**Safe alternative:** raw `threading.Thread(daemon=True)` for long-lived consumers. Reserve `@work(thread=True)` for tasks that start, do one HTTP/IO call, and exit (the docs' weather-app shape).

### 5.6 `call_from_thread()` for cross-thread UI updates

The Textual docs recommend `call_from_thread()` as the canonical cross-thread UI update path. In our environment, calls to `self.app.call_from_thread(self.rich_log.write, renderable)` from the consumer thread caused the consumer to stop producing events (silent crash) — and the screen stayed blank.

**Safe alternative:** `post_message(RenderMessage(renderable))` — `post_message` is also documented as thread-safe and IS working reliably for us.

### 5.7 Setting an instance attribute named `self.console`

Textual's `App` exposes `self.console` (a Rich Console managed by the driver). Setting `self.console = None` in `_ChatApp.__init__` shadowed it and Textual's `_init_mode → screen._screen_resized(self.size)` path raised `AttributeError: 'NoneType' object has no attribute 'size'`.

**Safe alternative:** name our own attribute `self.rich_console` (or similar). Anything but `self.console`.

### 5.8 Installing custom SIGINT/SIGTERM handlers around `app.run()`

The original implementation forwarded SIGTERM to the opencode server process group via `os.killpg(info.pid, signum)`. Because `ServerRunner.start()` puts the server in a new session (`start_new_session=True`), `os.killpg` from our process raised `PermissionError: [Errno 1] Operation not permitted`, which crashed mid-render and left the terminal in alternate-screen mode.

**Safe alternative:** install no custom signal handlers. Textual handles SIGINT via its own `action_quit` binding. Server cleanup goes in the chat harness `finally` block via `runner.stop()` (which uses `os.killpg` correctly within `ServerRunner`).

---

## 6. The diagnostic toolkit

Built into the code so we never have to reverse-engineer a freeze again.

### 6.1 The `--debug` flag and `tmp/chat-debug-<pid>-<ts>.log`

`make chat DEBUG=1` passes `--debug` to `run-agent.py`. When set:

- `_setup_chat_debug()` opens a per-run, line-buffered log file under `tmp/chat-debug-<pid>-<YYYYMMDD-HHMMSS>.log`.
- `_chat_debug(msg)` writes `[NNN.NNNs] [thread-name] msg` to that file. Safe to call from any thread.
- `ChatEventLoop` accepts a `debug` callback and uses it for consumer-side instrumentation (`_consumer_worker: starting SSE client`, event-number checkpoints, `session idle detected`, exception tracebacks).

The log filename includes the PID and a timestamp so successive runs don't overwrite earlier evidence.

### 6.2 The heartbeat canary

`self.set_interval(1.0, self._heartbeat)` schedules `_heartbeat()` to fire once per second on the main thread. `_heartbeat()` writes `_heartbeat: tick #N (main loop alive)` to the debug log.

If the chat mode appears to freeze, the FIRST thing to do is read `tmp/chat-debug-<latest>.log` and check whether heartbeat ticks are present:

- **Ticks present, but no `_on_render_message` lines:** message dispatch is broken. Look at recent diffs that touched `RenderMessage`, `@on(...)`, or added a second Message class.
- **No ticks at all:** the main asyncio loop is dead/starved. Look for a recent change that touched scheduling (a second `set_interval`, a long-lived `@work` worker, a sync blocking call from a Textual callback).
- **Ticks present AND `_on_render_message` lines AND model events visible but TUI looks wrong:** likely a Rich rendering issue (CSS, widget sizing), not a Textual-dispatch issue.

### 6.3 What "working" looks like

For reference, a healthy run looks like this in the debug log (excerpt from `tmp/chat-debug-9247-20260522-042343.log`):

```
[002.351s] [MainThread]              on_mount: entering
[002.352s] [MainThread]              on_mount: starting SSE consumer (raw daemon thread)
[002.352s] [codecome-chat-consumer]  _consumer_worker: entering event loop
[002.353s] [asyncio_0]               _send_initial_prompt: worker started
[002.520s] [codecome-chat-consumer]  _consumer_worker: event #1 type=server.connected
[002.521s] [codecome-chat-consumer]  TextualConsoleProxy._write: bg thread, post_message(RenderMessage)
[003.351s] [MainThread]              _heartbeat: tick #1 (main loop alive)
[004.351s] [MainThread]              _heartbeat: tick #2 (main loop alive)
[008.116s] [asyncio_0]               _send_prompt: worker posting text len=5
[008.312s] [asyncio_0]               _send_prompt: sent
[011.646s] [codecome-chat-consumer]  _render_and_log: event type=reasoning
...
```

Notable: regular heartbeat ticks, consumer events flowing, the user-input `_send_prompt` worker firing in response to typed input, and the main loop alive through to clean shutdown.

---

## 7. Safe extension recipes

If you need to add a feature, follow one of these recipes verbatim. If your feature doesn't fit any of these, **add a heartbeat-canary-bisection step to your work plan** before touching the code.

### 7.1 Add a new cross-thread render channel

You want to show some new kind of output in the RichLog from a background thread.

✅ Build the renderable on the bg thread and post it through the existing path:

```python
# On a bg thread (consumer or worker):
self.app.post_message(self.app.RenderMessage(my_renderable))
# OR via the proxy if you already have a Rich Console-like interface:
self.console_proxy.print(my_renderable)
```

No new `Message` subclass. No new handler. No new field on `RenderMessage`.

### 7.2 Add a new "kind" of event that needs main-thread state (not just rendering)

You want main-thread side effects (e.g. update a reactive variable, change focus, push a screen) triggered by a bg-thread event.

⚠️ This is exactly the path that produced multiple freezes. Acceptable approaches:

1. **Encode the state in a renderable.** Have the bg thread post a `RenderMessage(MyMarker(...))` where `MyMarker` is a custom Rich renderable that carries the metadata. Have the `_on_render_message` handler check `isinstance(message.renderable, MyMarker)` and dispatch to a main-thread routine when appropriate. (Single Message class, single handler — safe.)

2. **Reuse the heartbeat.** The main-thread `_heartbeat` method runs every second. Have the bg thread set a `threading.Event` or a thread-safe attribute, and have `_heartbeat` (which already runs on the main thread) read it. This adds NO new `set_interval` and stays within the proven envelope. Sub-second latency is sacrificed.

3. **If you absolutely need a second timer:** wrap the new periodic work as additional behaviour inside the existing `_heartbeat`. If you need higher frequency than 1Hz, change `_heartbeat`'s interval (rather than adding a second `set_interval`).

### 7.3 Add a new short-lived `@work(thread=True)` worker

✅ Pattern follows the docs' weather example and our existing `_send_prompt`:

```python
@work(thread=True)
def _do_some_short_blocking_call(self, arg):
    _chat_debug(f"_do_some_short_blocking_call: started arg={arg}")
    try:
        result = some_blocking_io(arg)            # e.g. HTTP POST
        # On success, surface result via the SAME RenderMessage path:
        self.post_message(self.RenderMessage(Text(f"Done: {result}")))
    except Exception as exc:
        _chat_debug(f"_do_some_short_blocking_call: error: {exc}")
        self._post_error_renderable(f"Failed: {exc}")
```

The worker MUST exit. No infinite loops. If you need a long-lived loop, use a raw `threading.Thread(daemon=True)`.

### 7.4 Upgrade Textual or Python

When bumping Textual or Python versions:

1. Run `make chat DEBUG=1` and verify a healthy log (per §6.3).
2. **Optionally** try lifting one of the forbidden patterns from §5 (e.g. add a second Message subclass). If it works in the new versions, document the new minimum versions here and relax the corresponding rule.

The hope is that future Textual/Python releases fix whatever quirk we hit. The forbidden patterns are not desirable per se — they're scar tissue from this version pair.

---

## 8. Why the original chat-mode design didn't survive contact

For historical context, the original plan ([.project/chat-mode-plan.md](./chat-mode-plan.md)) called for:

- A `ChatEventLoop` that wraps `SseClient` (kept ✅).
- Multi-message types for state vs render (dropped ❌ — see §5.1).
- A `_watch_chat_state` asyncio task that polls a thread-safe queue (dropped ❌ — multiple `asyncio.create_task` + `asyncio.to_thread` blocking calls inside `on_mount` were among the early freeze patterns; the resulting design uses no `asyncio.create_task` at all).
- Input enable/disable on idle/busy (dropped ❌ — see §5.4).

The current design preserves the **outcome** the original plan was after (interactive chat over `opencode serve`) but takes a less ambitious path through Textual to stay within what actually works.

---

## 9. Operational checklist when this code breaks again

When (not if) `make chat` mysteriously goes black:

1. Re-run with `make chat DEBUG=1` and grab the newest `tmp/chat-debug-*.log`.
2. Look for `_heartbeat: tick #N` lines.
   - **None:** main loop is dead. Recent change probably introduced a forbidden pattern from §5.
   - **Present but no `_on_render_message`:** message dispatch is dead. Check Message subclasses, `@on(...)` handlers, recent renames.
   - **Both present, model output still missing:** look at the consumer thread side (`_consumer_worker` and `_render_and_log` lines) and the SseClient — the issue is upstream of the TUI.
3. `git log --oneline` since the last known-good run; bisect the diff against the rules in §5.
4. If bisection produces a new "this should work per docs but doesn't" pattern, **update §5** with the new finding (and the matching log evidence) before merging the fix.

---

## 10. Related files

| File | Role |
|------|------|
| `tools/run-agent.py` | Historically housed `_ChatApp`, `TextualConsoleProxy`, the chat harness, debug logging helpers (`_chat_debug`, `_setup_chat_debug`, `_close_chat_debug`). The implementation now lives under `tools/chat/` and `tools/codecome/`. |
| `tools/events/chat_loop.py` | `ChatEventLoop` — owns the SSE consumer daemon thread and the `send_prompt` HTTP helper. Used by chat mode AND by other (potentially) interactive code paths. Has an optional `debug` callback. |
| `tools/events/sse_client.py`, `state_tracker.py`, `emitters.py` | Reused from non-interactive phase mode. Not chat-specific. |
| `tests/test_chat_mode.py` | Unit tests for `ChatEventLoop`, `TextualConsoleProxy`, `_ChatApp._render_and_log` parity, and the chat harness transcript-file lifecycle. Pure Python (no Textual app instance); won't catch the freezes documented here, but does catch parity regressions vs phase mode. |
| `Makefile` (`chat:` target) | Entry point. Accepts `DEBUG=1` to forward `--debug` (which enables the diagnostic log file and the raw-event mirror to it). |
| `.project/chat-mode-plan.md` | Original design plan (pre-bisection). Kept for historical context; this postmortem supersedes it on architecture details. |
| `.project/chat-mode-textual-postmortem.md` | This document. |
| `tmp/chat-debug-*.log` | Per-run diagnostic logs (only when `--debug`). The bisection logs (May 22, 2026) are still around and are the evidence base for §3 and §5. |
| `tmp/last-chat-<ts>-pid<pid>.jsonl` | Per-run transcript jsonl, ALWAYS written. One JSON line per SSE event. Mirrors phase mode's `tmp/last-phase-...jsonl`. The transcript path is printed after the chat session ends. |

---

## 11. Changelog

### 2026-05-23 — Mouse selection: terminal-native via Ctrl+S (Option 1)

- **Removed: `_SelectableRichLog` subclass.** Our manual `style._meta["offset"]` annotation pipeline did not produce a usable selection experience. Deep analysis (documented in [§12](#12-rationale-richlog-mouse-selection-is-not-supported-upstream)) shows RichLog lacks **all four** pieces needed for in-app selection — offset metadata, selection-style rendering inside `render_line`, cache invalidation on `selection_updated`, and `get_selection` text extraction — and reimplementing all four would mean either rendering each renderable twice (once for display, once for plain-text extraction) or replacing RichLog with `Log` (which loses all Rich markup, panels, and colors). Both options were rejected as poor value for the risk.
- **Added: `Ctrl+S` action `action_toggle_mouse_for_select`.** Toggles `App._driver._disable_mouse_support()` / `_enable_mouse_support()` (the canonical driver-level API used by Textual at startup/shutdown). When ON, Textual stops sending mouse-tracking escape sequences and the terminal emulator's native click-drag selection takes over, with Cmd+C / Ctrl+Shift+C copying to the system clipboard. A `[SEL]` indicator appears in the modeline. Status hint with current mode is written to the RichLog on each toggle.
- **Added: startup tip.** `on_mount` now writes a dim italic line after the banner explaining the Option/Alt-drag (no-toggle) and Ctrl+S (toggle) selection paths.
- **Removed imports:** `rich.segment.Segment`, `rich.style.Style`, `textual.strip.Strip` — no longer used.
- **CSS update:** `_SelectableRichLog { ... }` rule renamed to `RichLog { ... }`. `compose()` yields stock `RichLog` and `query_one(RichLog)` replaces the subclass query.
- **Files:** `tools/run-agent.py` (`_ChatApp` BINDINGS adds `ctrl+s`, `__init__` adds `_terminal_select_mode`, new `action_toggle_mouse_for_select`, `_heartbeat` adds `[SEL]` modeline tag, `compose` reverts to stock RichLog, startup hint), `.project/chat-mode-textual-postmortem.md` (new §12 + this entry).
- **Tests:** 268 pass unchanged. `make tests` quality gate clean.

### 2026-05-22 — RichLog suppression, modeline, dedup, sync cleanup

- **Changed: `render_message_updated`** now suppresses in-progress messages. Only "complete" messages (those with a `summary`, `finish` reason, or non-zero tokens) produce output in the RichLog. This eliminates the flood of `> User` / `> Assistant (processing...)` lines that used to appear on every lifecycle event from the SSE stream.
- **Added: bottom-bar modeline.** A `Static` widget is passed as the leftmost child of `Footer` and updated by `_heartbeat` (1 Hz, main thread) from `_modeline_info` (atomically refreshed by `_render_and_log` on every `message.updated` event from the consumer thread). Displays `● | provider/model | ↑in ↓out | $cost` with a pulsing activity indicator that alternates `●` / `◌` each heartbeat tick. No new timers, no new handlers, no bg-thread UI writes — stays within the proven safe envelope.
- **Fixed: composite-key dedup in `_consumer_worker`.** SSE-stream-level `message.updated` duplicates (same message ID, same token-state) are now suppressed via a `(msg_id, has_input)` composite key in `_seen_message_ids`. The transition from "no tokens" to "has tokens" is allowed through so the final token-summary line renders. Plain message IDs are also stored for sync-path dedup.
- **Fixed: `_sync_session_messages` removed from idle path.** Previously called on every `session.idle` / `session.status:idle`, causing a bulk re-fetch of all session messages and emitting duplicate `message.updated` events for every message. The method is retained for future reconnect-catch-up use; for normal operation the SSE stream itself carries all events.
- **Updated: `_trigger_recovery_sync` docstring** notes that sync-after-reconnect is a TODO.
- **Files:** `tools/run-agent.py` (`_ChatApp` modeline, `_update_modeline_info`, `_heartbeat`, `render_message_updated` suppression), `tools/events/chat_loop.py` (composite-key dedup, idle-sync removal).

### 2026-05-22 — Message deduplication + enriched render

- **Fixed: `message.updated` deduplication.** `_consumer_worker` now tracks message IDs from the raw SSE stream in `_seen_message_ids`, so `_sync_session_messages` on idle no longer re-emits duplicate `message.updated` events for messages already seen and rendered. This eliminates the flood of duplicate `> User`/`> Assistant` lines that used to appear on every idle cycle (previously up to 7 duplicates per user message).
- **Improved: `render_message_updated`** (both chat and phase modes):
  - Uses `info.role` (not `info.agent`) to determine the label: `> User` for user messages, `> Assistant` for assistant messages.
  - User messages are rendered dim (no model spam — just `> User`).
  - Assistant messages with tokens populated (complete) show the model and token/cost summary: `> Assistant · provider/model (↑444 ↓57, R28, cache read 24448, $0.0123)` (bold blue).
  - Assistant messages without tokens (in-progress) render as `> Assistant (processing...)` (dim).
  - Handles both SSE-stream shape (`event.properties.info`) and sync-synthesized shape (`event.info`).
  - Cost is shown only when non-zero.
- **Files:** `tools/events/chat_loop.py` (5 lines), `tools/run-agent.py` (`render_message_updated` rewrite).

### 2026-05-22 — Parity pass

- **Added: transcript jsonl.** The chat harness now opens `tmp/last-chat-<YYYYMMDD-HHMMSS>-pid<pid>.jsonl` before starting the TUI and closes it in `finally`. Every SSE event seen by `_render_and_log` is persisted as a JSON line. The file handle is passed into `_ChatApp(transcript_fp=...)`.
- **Added: end-of-session summary.** After `app.run()` returns, the restored terminal prints a green `Chat session ended` rule plus the `transcript: tmp/last-chat-...jsonl` path. Mirrors phase mode's success summary.
- **Added: initial-prompt echo.** Before spawning the `_send_initial_prompt` worker, `on_mount` writes `User: <prompt>` to the RichLog so the user can see what they sent.
- **Added: `--debug` raw-event mirror.** With `--debug`, `_render_and_log` now writes `_render_and_log: raw event: <json>` to the chat-debug log file (rather than stderr, which Textual owns). Phase mode mirrors to stderr; chat mode routes to the same per-run diagnostic file the heartbeat already writes to.
- **Removed: `[idle]` / `[busy]` chat-only state markers.** `_render_and_log` no longer posts these. The non-chat `render_session_status` renderer (already invoked via `render_event`) prints `session status: busy/idle` through the normal proxy path, which is the same signal phase mode emits. This achieves full event parity between chat and phase modes.
- **Tests:** added `TestChatRenderAndLogParity` (7 cases covering transcript writes, OSError swallowing, reasoning suppression, debug-mode mirror, no state-marker emission) and `TestChatTranscriptPath` (1 case verifying the `tmp/last-chat-<ts>-pid<pid>.jsonl` filename pattern is opened and closed by the chat harness). Suite size: 23 → 31 chat tests (260 → 268 project total).
- **Docstring of `_ChatApp` updated.** Reflects the parity changes and the new transcript responsibility.

### 2026-05-22 — Initial working build (post-bisection)

- Established the working architecture documented in §4.
- Documented the failure-mode bisection (§3) and forbidden patterns (§5).
- Added the heartbeat canary + `--debug` chat-debug log file.

---

## 12. Rationale: RichLog mouse selection is not supported upstream

### 12.1 What Textual requires for a widget to be selectable

In-app text selection in Textual is implemented at the `Screen` level (`screen.py` lines 1820-1916) but only works when a widget provides **all four** of the following cooperating pieces:

| Piece | What the widget must do | Why |
|---|---|---|
| **A. Offset metadata** | Each segment in the strip returned by `render_line(y)` must carry `style._meta["offset"] = (char_x, content_y)` | The compositor's `get_widget_and_offset_at(x, y)` (`_compositor.py:944-967`) reads this to translate mouse pixel coordinates into per-character content offsets. Without it, the compositor returns `Offset(0, y)` and selection ranges collapse. |
| **B. Selection rendering** | `render_line` must read `self.text_selection`, fetch `screen--selection` component style, and stylize the selected range with the highlight background | Without this, the user sees no visual change when dragging — the selection exists in `screen.selections` but is invisible. |
| **C. Cache invalidation** | `selection_updated(selection)` must clear the per-line render cache and call `refresh()` | Without this, the freshly-rendered line is taken from cache (which lacks the selection style) on the next paint. |
| **D. Selection extraction** | `get_selection(selection)` must return the plain text under the selection as `(text, "\n")` | `Screen.action_copy_text` iterates `screen.selections` and calls each widget's `get_selection`. Without it, copy-to-clipboard returns nothing. |

The reference implementation is `textual.widgets.Log` (`_log.py:265-362`). `Log` stores plain `str` lines, so it can cheaply build a Rich `Text` per render with selection style applied via `Text.stylize(selection_style, start, end)`, then apply `Strip.apply_offsets(scroll_x, content_y)` — the canonical Textual API for piece A.

### 12.2 What `RichLog` provides (out of the box)

`textual.widgets.RichLog` (`_rich_log.py`) provides **none of the four pieces**. Its `write()` calls `console.render(renderable)` and stores the resulting `Strip` list, with no plain-text representation kept anywhere. Its `render_line` just slices and styles via `apply_style(self.rich_style)`. Selection support has never been added upstream.

### 12.3 What we tried first (and why it didn't work)

The `_SelectableRichLog` subclass attempted to implement only piece A by mutating `self.lines[content_y]` to inject per-segment offset metadata before calling `super().render_line(y)`. This was insufficient because:

1. **Pieces B/C/D were absent.** Even if piece A worked perfectly, the user would see no highlight on drag and nothing would copy to clipboard. From the user's perspective, this is indistinguishable from "selection is broken."
2. **`RichLog._line_cache` is content-blind.** It is keyed on `(y, scroll_x, width, widest)` — if a strip was cached before annotation, the cached (unannotated) version is returned on subsequent paints; our `render_line` override would have had to also invalidate the line cache on every mutation.
3. **`char_offset = len(segment.text)` is correct for ASCII but drifts for wide CJK/emoji** because the compositor mixes `cell_length` (for boundary checks) with `len(text)` (for offsets). Stock `Strip.apply_offsets` has the same limitation, so this is more of an upstream caveat than a bug, but it's worth noting.

### 12.4 Why we did not fully implement A+B+C+D

A complete in-app selection implementation would require:

- Storing each renderable's plain-text representation alongside its strips (involves a second `console.render(...)` pass per renderable with a styles-stripped console, or maintaining a parallel `list[str]` synchronised with `self.lines`).
- A custom `render_line` / `_render_line` pair that consults `text_selection`, gets the `screen--selection` style, restyles segments in the selected range, and calls `Strip.apply_offsets(scroll_x, content_y)`.
- A custom `selection_updated` that clears `_line_cache` and `self._render_line_cache`.
- A custom `get_selection` that extracts from the plain-text store.

That is ~150 lines of new code added inside the very widget the compositor calls on every paint. The bisection postmortem (§5) repeatedly shows that seemingly innocuous additions to this code path silently freeze Textual's main loop on this Textual 8.2.6 + Python 3.14.5 combo. The risk-to-value ratio is poor.

### 12.5 The terminal-native escape hatch (chosen path)

Every modern terminal emulator (iTerm2, macOS Terminal, gnome-terminal, Alacritty, kitty, Windows Terminal, …) provides mouse-driven text selection over its display buffer, with system-clipboard integration. Textual normally captures mouse events, which prevents the terminal from seeing the drag. There are two well-known escape hatches:

1. **Modifier-key bypass.** Hold Option/Alt on macOS terminals (or Shift on most Linux/Windows terminals) while dragging. The terminal sees the drag as "not for the application" and performs its native selection. This works without any application support.
2. **Driver-level mouse toggle.** Textual's driver has `_enable_mouse_support()` / `_disable_mouse_support()` (`drivers/linux_driver.py:121, 169`), which write `\x1b[?1000h`/`\x1b[?1000l` and friends to enable/disable the terminal's mouse-reporting modes. When disabled, mouse events are no longer intercepted by Textual, and the terminal performs native selection.

We use **(2)** behind the `Ctrl+S` action and **document (1)** in the startup tip so users have both paths available. A `[SEL]` indicator appears in the modeline when terminal-select mode is on, and toggling either way prints a status hint into the RichLog.

### 12.6 Limitations of the chosen approach

- **No in-app visual feedback.** When `Ctrl+S` is on, the terminal draws the selection; the Textual app is unaware. This is by design.
- **Mouse-driven Textual interactions are disabled while `[SEL]` is on.** Scrolling via mouse wheel, clicking the input, etc. require toggling back. Keyboard interactions remain unaffected.
- **Selection persists across redraws.** Because the terminal owns the selection, new output from `_render_and_log` may scroll the buffer and visually disrupt the selection. The user is expected to copy, then toggle back.

These trade-offs are acceptable: terminal-native selection is the standard pattern for every other interactive CLI (`less`, `vim`, `tmux` copy-mode bypass, etc.), and users already know how their terminal handles it.

### 12.7 If future Textual adds RichLog selection support

If a future Textual version implements pieces A-D on `RichLog` itself, the canonical path is to drop the `Ctrl+S` action, remove the startup tip, and let upstream selection work. The forbidden-patterns list in §5 still applies regardless.
