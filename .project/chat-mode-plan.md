# Chat Mode Implementation Plan

**Status:** Draft
**Date:** 2026-05-21
**Target:** `tools/run-agent.py`, `tools/events/`, `Makefile`
**Risk Level:** Medium (adds new mode to existing harness)

---

## 1. Executive Summary

Add an interactive `--chat` mode to `run-agent.py` that reuses the existing `opencode serve` infrastructure (`ServerRunner`, `EventLoop`, `SseClient`, `StateTracker`) but runs in a multi-turn loop: idle → wait for user input → send prompt → consume SSE → idle again.

The Textual TUI provides the user-facing interface: a `RichLog` upper panel (driven by the existing render pipeline) and an `Input` lower panel for typing messages.

---

## 2. Architecture

```
make chat
  └─ run-agent.py --chat
       ├─ ServerRunner.start()              # reuse tools/opencode/serve.py
       ├─ POST /session                     # reuse _create_session()
       ├─ ChatApp.run()                     # Textual TUI (new)
       │    ├─ RichLog (upper panel)        # receives rendered events
       │    ├─ Input (lower panel)          # user types messages
       │    └─ QuitScreen (Ctrl+C modal)    # confirm quit
       └─ ChatEventLoop                     # new: idle→prompt→idle loop
            ├─ SseClient                    # reuse tools/events/sse_client.py
            ├─ StateTracker                 # reuse tools/events/state_tracker.py
            ├─ emit_event()                 # reuse tools/events/emitters.py
            └─ POST /session/{id}/message   # reuse _send_prompt_to_session()
```

### Key Design Decisions

1. **Reuse `ServerRunner`** — no need to spawn `opencode serve` manually; `ServerRunner.start()` handles health checks, ephemeral ports, and auth tokens.

2. **New `ChatEventLoop` class** — a thin wrapper around `EventLoop` that:
   - Does NOT exit on session idle
   - Instead, signals the TUI that the session is ready for the next prompt
   - Uses `asyncio`-compatible event signaling (or `queue.Queue`) to coordinate between the SSE consumer thread and the TUI main thread

3. **Single session, multi-turn** — the session is created once. Each user message is sent as a new `POST /session/{id}/message` with a single text part.

4. **Rendering stays the same** — all events flow through the existing `render_event()` → `render_text()` / `render_tool_use()` / etc. pipeline. The `TextualConsoleProxy` bridges Rich `Console.print()` to `RichLog.write()`.

---

## 3. New Files / Changes

### 3.1 `tools/events/chat_loop.py` (NEW)

```python
class ChatEventLoop:
    """Multi-turn event loop: idle → signal ready → send prompt → consume → idle."""

    def __init__(self, base_url, session_id, console, auth_token=None, workspace_dir=None):
        ...

    def start_consumer(self, render_fn):
        """Start SSE consumer in background thread. Signals via queue."""
        ...

    def send_prompt(self, text, agent=None, model=None, variant=None):
        """POST /session/{id}/message with text part."""
        ...

    def stop(self):
        """Signal consumer thread to exit."""
        ...
```

**Test strategy:**
- Unit test with `FakeSseClient` (same pattern as `test_new_serve_stack.py`)
- Test prompt→idle→prompt→idle cycle
- Test stop() cleanly terminates consumer
- Test error handling (bad prompt, server down)

### 3.2 `tools/run-agent.py` (MODIFY)

Changes:
1. **argparse**: Add `--chat` flag, `--prompt` arg (for initial greeting)
2. **Validation**: When `--chat`, `--phase` is not required
3. **Chat path**: After server start + session creation, launch `ChatApp` instead of the phase loop
4. **Textual TUI**: `ChatApp`, `QuitScreen`, `TextualConsoleProxy` classes (conditionally imported)

### 3.3 `Makefile` (MODIFY)

```makefile
CHAT ?= 0
ifeq ($(CHAT),1)
WRAPPER_ARGS += --chat
endif

chat: venv-check
	@$(PYTHON) tools/run-agent.py --chat --label "Interactive Chat" --agent $(or $(AGENT),auditor) --prompt "Please introduce yourself and wait for my instructions."
```

Also add `$(WRAPPER_ARGS)` to all phase targets (phases 1-6).

### 3.4 `requirements.txt` (MODIFY)

```
textual>=0.80.0
```

### 3.5 `tests/test_chat_mode.py` (NEW)

Tests:
1. `TestChatEventLoop` — unit tests with fake SSE client
2. `TestChatArgparse` — `--chat` flag parsing, validation rules
3. `TestTextualConsoleProxy` — Rich → RichLog bridging
4. `TestChatMainEntry` — integration test with mocked server (monkeypatch `ServerRunner`, `_create_session`, `ChatEventLoop`)

---

## 4. Test Plan

### 4.1 Unit Tests (fast, no opencode binary)

| Test | What | How |
|------|------|-----|
| `test_chat_event_loop_single_turn` | One prompt → SSE events → idle → ready | `FakeSseClient` yields canned events |
| `test_chat_event_loop_multi_turn` | Prompt → idle → prompt → idle → stop | Two canned event sequences |
| `test_chat_event_loop_stop_during_busy` | Stop signal while processing | `queue.Queue` + thread sync |
| `test_chat_event_loop_permission_rejected` | Permission auto-reject in chat mode | `FakeSseClient` with `permission.asked` |
| `test_chat_event_loop_error_recovery` | SSE disconnect → reconnect → continue | `FakeSseClient` with reconnect |
| `test_chat_argparse_requires_label_and_agent` | Missing required args | `parser.parse_args()` |
| `test_chat_argparse_chat_skips_phase` | `--chat` without `--phase` | `parser.parse_args()` |
| `test_textual_console_proxy_single_arg` | Proxy forwards single renderable | Mock `RichLog.write` |
| `test_textual_console_proxy_no_args` | Proxy writes empty line | Mock `RichLog.write` |
| `test_textual_console_proxy_multi_args` | Proxy wraps in `Group` | Mock `RichLog.write` |

### 4.2 Integration Tests (requires opencode binary, marked `@pytest.mark.component`)

| Test | What | How |
|------|------|-----|
| `test_chat_main_starts_server` | `main()` with `--chat` starts server | Monkeypatch `ChatApp` to capture args |
| `test_chat_main_missing_textual` | `--chat` without textual → error | Monkeypatch import to fail |

### 4.3 Parity Tests (using mock-llm-server.py)

Future: extend `mock-llm-parity.py` to test chat mode parity with a multi-turn script.

---

## 5. Implementation Order

1. ✅ Write this plan
2. Add `--chat` flag + argparse changes to `run-agent.py`
3. Implement `ChatEventLoop` in `tools/events/chat_loop.py`
4. Write unit tests for `ChatEventLoop`
5. Implement `TextualConsoleProxy` + `ChatApp` + `QuitScreen` in `run-agent.py`
6. Wire chat path in `main()`
7. Add `chat:` target + `WRAPPER_ARGS` to `Makefile`
8. Add `textual` to `requirements.txt`
9. Write integration tests
10. Run full test suite (`make tests`)
11. Rebase on master

---

## 6. Obsolete Artifacts

The following are no longer needed and should be removed:

- `.project/chat-bridge-plan.md` — proposed a plugin bridge approach; superseded by direct serve usage
- `test_tui.py` — standalone prototype; superseded by integrated `ChatApp`

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Textual TUI blocks SSE consumer | SSE runs in daemon thread; TUI uses `call_from_thread()` |
| Server outlives TUI quit | `ServerRunner.stop()` called in cleanup; signal handler forwards SIGTERM |
| Race: prompt sent before session ready | `ChatEventLoop` uses a ready queue; prompt blocks until consumer signals idle |
| Textual not installed | Early `ImportError` check with helpful message |
