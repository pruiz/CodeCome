# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Chat app: Textual-based interactive chat TUI classes.

Provides:
  - TextualConsoleProxy: RichLog bridge for background-thread console output.
  - ChatApp / QuitScreen: module-level type hints (real classes set after try/except).
  - _chat_render_and_log / _chat_update_modeline_info: standalone helpers,
    callable without Textual (for testing parity).
  - _QuitScreen: quit confirmation modal.
  - _ChatApp: the Textual App.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chat.debug import _chat_debug  # noqa: E402
from rendering.dispatch import render_event  # noqa: E402

# ---------------------------------------------------------------------------
# Rich imports — same fallback pattern as run-agent.py
# ---------------------------------------------------------------------------

try:
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.text import Text

    HAVE_RICH = True
except ImportError:  # pragma: no cover
    Console = Any  # type: ignore[assignment]
    Group = tuple  # type: ignore[assignment]
    Panel = None  # type: ignore[assignment]
    Rule = None  # type: ignore[assignment]
    Text = None  # type: ignore[assignment]
    HAVE_RICH = False

# ---------------------------------------------------------------------------
# Module-level type hints — real classes set by the try/except block below.
# ---------------------------------------------------------------------------

ChatApp: Any = None
QuitScreen: Any = None


# ---------------------------------------------------------------------------
# TextualConsoleProxy — RichLog bridge (outside try/except; no Textual imports needed)
# ---------------------------------------------------------------------------

class TextualConsoleProxy:
    """Bridge Rich Console.print() calls to a Textual RichLog widget.

    Thread-safe: main-thread calls write directly to RichLog; background-
    thread calls post a RenderMessage which is dispatched on the main
    thread by the @on(RenderMessage) handler.  This is the pattern from
    Textual docs (post_message is thread-safe).
    """

    def __init__(self, rich_log, app):
        self.rich_log = rich_log
        self.app = app
        self.encoding = "utf-8"

    def print(self, *args, **kwargs):
        """Bridge to RichLog.write(). **kwargs is accepted for compatibility
        with rich.console.Console.print() but is intentionally ignored
        (style/end etc. are not forwarded to RichLog)."""
        if not args:
            from rich.text import Text

            self._write(Text())
            return
        if len(args) == 1:
            self._write(args[0])
        else:
            from rich.console import Group

            self._write(Group(*args))

    def _write(self, renderable):
        import threading

        if threading.current_thread() is threading.main_thread():
            _chat_debug("TextualConsoleProxy._write: main thread, direct write")
            self.rich_log.write(renderable)
        else:
            _chat_debug("TextualConsoleProxy._write: bg thread, post_message(RenderMessage)")
            self.app.post_message(self.app.RenderMessage(renderable))


# ---------------------------------------------------------------------------
# Standalone chat-app methods — available even when Textual is not
# installed, so that tests can exercise _render_and_log parity without
# launching a real TUI.
# ---------------------------------------------------------------------------

def _chat_render_and_log(self, console, phase, label, event):
    """Standalone version of _ChatApp._render_and_log.  See the docstring
    on the class for the full contract.

    When bound via ``__get__`` to a _ChatApp instance, ``self`` is
    guaranteed to carry the attributes accessed below."""
    self.event_recorder.record(event)
    render_event(console, phase, label, event)
    _chat_update_activity_state(self, event)
    if event.get("type") == "message.updated":
        _chat_update_modeline_info(self, event)


def _chat_update_modeline_info(self, event: dict[str, Any]) -> None:
    """Standalone version of _ChatApp._update_modeline_info."""
    info = event.get("info")
    if not isinstance(info, dict):
        props = event.get("properties", {})
        info = props.get("info", {}) if isinstance(props, dict) else {}
    if not isinstance(info, dict):
        return
    if info.get("role") != "assistant":
        return
    model_id = str(info.get("modelID", "")).strip()
    provider_id = str(info.get("providerID", "")).strip()
    if not model_id:
        mdl = info.get("model", {})
        if isinstance(mdl, dict):
            model_id = str(mdl.get("modelID", "")).strip()
            provider_id = str(mdl.get("providerID", "")).strip()
    model_label = f"{provider_id}/{model_id}" if provider_id and model_id else (model_id or "\u2026")
    tokens = info.get("tokens", {})
    if isinstance(tokens, dict):
        _in = tokens.get("input", 0)
        _out = tokens.get("output", 0)
        token_str = f"\u2191{_in} \u2193{_out}"
    else:
        token_str = ""
    cost = info.get("cost", 0) or 0
    cost_str = f" ${cost:.4f}" if cost else ""
    try:
        meta = f"{model_label} | {token_str}{cost_str}" if token_str else f"{model_label}{cost_str}"
        self._modeline_meta = meta.strip()
    except AttributeError:
        pass


def _chat_update_activity_state(self, event: dict[str, Any]) -> None:
    """Track footer activity state using only arriving events."""
    event_type = str(event.get("type", ""))
    now = time.monotonic()

    def set_state(state: str, *, started_at: float | None = None) -> None:
        try:
            self._modeline_state = state
            self._modeline_state_since = now if started_at is None else started_at
        except AttributeError:
            pass

    if event_type == "server.connected":
        try:
            self._modeline_connected = True
        except AttributeError:
            pass
        return

    if event_type == "server.heartbeat":
        return

    if event_type in {"session.status", "session.idle"}:
        if event_type == "session.idle":
            set_state("idle")
            return
        props = event.get("properties", {}) if isinstance(event.get("properties"), dict) else {}
        status = props.get("status", {}) if isinstance(props.get("status"), dict) else {}
        status_type = str(status.get("type", ""))
        if status_type == "idle":
            set_state("idle")
        elif status_type in {"busy", "retry"} and getattr(self, "_modeline_state", "idle") != "thinking":
            set_state("busy")
        return

    if event_type == "reasoning":
        part = event.get("part", {}) if isinstance(event.get("part"), dict) else {}
        text = str(part.get("text", "")).strip()
        metadata = part.get("metadata", {}) if isinstance(part.get("metadata"), dict) else {}
        openai_meta = metadata.get("openai", {}) if isinstance(metadata.get("openai"), dict) else {}
        has_hidden_reasoning = bool(openai_meta.get("reasoningEncryptedContent"))
        if has_hidden_reasoning and not text:
            started_at = getattr(self, "_modeline_state_since", None) if getattr(self, "_modeline_state", "") == "thinking" else now
            set_state("thinking", started_at=started_at)
        elif text:
            set_state("busy")
        return

    if event_type == "text":
        set_state("idle")
        return

    if event_type in {"tool_use", "step_start", "step_finish", "message.updated"}:
        set_state("busy")


# ---------------------------------------------------------------------------
# Textual classes — guarded by import, matching run-agent.py pattern
# ---------------------------------------------------------------------------

try:
    from textual import on, work
    from textual.app import App, ComposeResult
    from textual.message import Message
    from textual.widgets import RichLog, Input, Footer, Static, Button, Label
    from textual.binding import Binding
    from textual.containers import Grid, Horizontal
    from textual.screen import ModalScreen

    class _QuitScreen(ModalScreen[bool]):
        CSS = """
        _QuitScreen {
            align: center middle;
        }
        #quit-dialog {
            grid-size: 2;
            grid-gutter: 1 2;
            grid-rows: 1fr 3;
            padding: 0 1;
            width: 60;
            height: 11;
            border: thick $background 80%;
            background: $surface;
        }
        #quit-question {
            column-span: 2;
            height: 1fr;
            width: 1fr;
            content-align: center middle;
        }
        Button {
            width: 100%;
        }
        """

        def compose(self) -> ComposeResult:
            yield Grid(
                Label("Are you sure you want to quit?", id="quit-question"),
                Button("Quit", id="quit-confirm", variant="error"),
                Button("Cancel", id="quit-cancel", variant="primary"),
                id="quit-dialog",
            )

        def on_button_pressed(self, event: Button.Pressed) -> None:
            self.dismiss(event.button.id == "quit-confirm")

    class _ChatApp(App):
        """Interactive chat harness — final design (post-bisection).

        Design follows Textual docs (https://textual.textualize.io/guide/workers):

          * The SSE consumer runs in a raw daemon thread (started via
            chat_loop.start_consumer).  Textual's @work(thread=True) is
            reserved for short-lived blocking tasks (the docs' weather-
            app pattern); using it for an infinite consumer loop froze
            the main event loop in our environment (Textual 8.2.6 /
            Python 3.14).

          * All UI updates from background threads (renderables AND
            state markers AND errors) go through ONE one-argument
            Message subclass (RenderMessage(renderable)) and ONE @on
            handler that just calls rich_log.write.  post_message is
            documented as thread-safe.  Bisection found that any
            departure from this exact shape (adding a second Message
            subclass, renaming it, adding optional fields, or even
            adding a second set_interval callback) silently freezes
            Textual's message dispatch on this version, even though
            the same patterns work in isolated repros.  We don't
            understand the root cause; staying inside this working
            envelope is the pragmatic path forward.

          * _render_and_log mirrors phase mode's behaviour exactly
            (parity with non-interactive runs).  Per-event side effects:
            persist to the transcript jsonl, mirror raw JSON to the
            chat-debug log when --debug is set, suppress 'reasoning'
            when thinking is off, then delegate to the SAME
            render_event() dispatcher non-chat uses.  No chat-specific
            filters or markers — `render_session_status` already
            prints `session status: busy/idle` and that's the only
            state cue we surface.  We do NOT toggle the Input widget's
            enabled/placeholder state, because doing that required a
            second set_interval poller which broke dispatch in our
            bisection.  The Input stays enabled at all times.

          * Errors from @work workers post a red Panel renderable via
            _post_error_renderable() — same RenderMessage path.

          * Short-lived HTTP calls (initial prompt, user prompt send)
            run as @work(thread=True) workers — the canonical docs
            pattern (matches the weather-app example).

          * The transcript is opened in run_harness and the
            Transcript instance is passed in via the `transcript`
            constructor argument; _render_and_log calls
            transcript.write_event() per SSE event (parity with
            phase mode).

          * A set_interval(1.0) heartbeat continuously logs a debug
            tick from the main thread and also updates the bottom-bar
            status line (modeline) with live token usage and an
            activity pulse.  The modeline data is fed by
            _render_and_log on every message.updated event.
        """

        CSS = """
        RichLog {
            height: 1fr;
            border-bottom: solid green;
            background: black;
        }
        Input {
            height: 3;
        }
        #bottom-bar {
            dock: bottom;
            height: 1;
            background: $footer-background;
        }
        #status-left {
            width: auto;
            min-width: 26;
            height: 1;
            padding: 0 1;
            color: $footer-foreground;
            background: $footer-background;
        }
        #status-meta {
            width: 1fr;
            height: 1;
            padding: 0 1;
            content-align: center middle;
            color: $footer-foreground;
            background: $footer-background;
        }
        #footer-right {
            width: auto;
            height: 1;
        }
        Footer {
            dock: none;
        }
        """

        # Ctrl+S toggles Textual's mouse capture so the user can use the
        # terminal's native mouse selection (which produces system-clipboard
        # copy via the terminal emulator).  RichLog has no in-app selection
        # support upstream, so terminal-native selection is the supported
        # path.  See .project/chat-mode-textual-postmortem.md §4 / §12.
        BINDINGS = [
            Binding("ctrl+c", "request_quit", "Quit"),
            Binding("ctrl+s", "toggle_mouse_for_select", "Select mode"),
        ]

        class RenderMessage(Message):
            """Single thread-safe message type — carries a Rich renderable
            to be written to the RichLog on the main thread.

            Bisection showed that extending this class with optional
            fields (`state`, `detail`) silently breaks Textual's message
            dispatch on this version (Textual 8.2.6 / Python 3.14), even
            though the same pattern works in isolation.  Whatever the
            root cause, we keep this class strictly one-argument
            (positional, `renderable`) and use a thread-safe pending-state
            slot + main-thread polling timer for idle/busy/error
            transitions instead.
            """

            def __init__(self, renderable):
                super().__init__()
                self.renderable = renderable

        def __init__(self, server_info=None, session_id=None, initial_prompt="", args=None, model=None, variant=None, thinking_on=None, transcript=None):
            super().__init__()
            self.server_info = server_info
            self.session_id = session_id
            self.initial_prompt = initial_prompt
            self.args = args
            self.model = model
            self.variant = variant
            self.thinking_on = thinking_on
            from codecome.transcript import Transcript
            self.transcript = transcript if transcript is not None else Transcript.null()
            from codecome.recording import EventRecorder
            self.event_recorder = EventRecorder(
                self.transcript,
                debug=getattr(args, "debug", False),
                debug_fn=_chat_debug,
            )
            self.chat_loop = None
            self.console_proxy = None
            self.rich_log = None
            self.chat_input = None
            self.modeline = None
            self.modeline_meta = None
            self._heartbeat_count = 0
            # Updated by _render_and_log (consumer thread) on every
            # message.updated event.  Read by _heartbeat (main thread)
            # to drive the status-line in the bottom bar.
            self._modeline_meta = ""
            self._modeline_state = "idle"
            self._modeline_state_since = None
            self._modeline_connected = True
            # Tracks Ctrl+S terminal-select mode.  When True, Textual mouse
            # handling is disabled so the terminal emulator's native mouse
            # selection works (which copies to the system clipboard via the
            # terminal itself).  Default off (Textual mouse handling on).
            self._terminal_select_mode = False

        def compose(self) -> ComposeResult:
            yield RichLog(id="log", markup=False, auto_scroll=True)
            yield Input(id="chat_input", placeholder="Type a message and press Enter...")
            with Horizontal(id="bottom-bar"):
                yield Static("ready", id="status-left")
                yield Static("", id="status-meta")
                yield Footer(id="footer-right")

        def on_mount(self) -> None:
            _chat_debug("on_mount: entering")
            self.rich_log = self.query_one(RichLog)
            self.chat_input = self.query_one(Input)
            self.modeline = self.query_one("#status-left", Static)
            self.modeline_meta = self.query_one("#status-meta", Static)
            self.console_proxy = TextualConsoleProxy(self.rich_log, self)
            from rendering import dispatch as rendering_dispatch

            rendering_dispatch.reconfigure_rendering(
                self.console_proxy,
                render_reasoning=bool(self.thinking_on),
            )
            _chat_debug("on_mount: proxy created")

            # Set initial modeline with model/agent info.
            provider = (self.model or "").split("/", 1)[0] if self.model else ""
            _model_id = (self.model or "").split("/", 1)[1] if self.model and "/" in self.model else (self.model or "\u2026")
            model_label = f"{provider}/{_model_id}" if provider else _model_id
            self.modeline.update("\u25cf \u00b7 Idle")
            self.modeline_meta.update(model_label)

            # Heartbeat canary — fires every 1s on the main thread.  Helpful
            # in the debug log to confirm the event loop is alive.
            self.set_interval(1.0, self._heartbeat)
            _chat_debug("on_mount: heartbeat installed")

            # Write banner (main thread, direct write).
            if HAVE_RICH:
                from rich.rule import Rule

                self.rich_log.write(Rule(title="Chat: Interactive Harness", style="bold cyan"), expand=True)
                model_label = self.model or "(unknown)"
                variant_label = self.variant or "(unknown)"
                parts = [f"agent={self.args.agent if self.args else '?'}", f"model={model_label}"]
                if self.variant is not None:
                    parts.append(f"variant={variant_label}")
                parts.append(f"thinking={'on' if self.thinking_on else 'off'}")
                self.rich_log.write(Text("  ".join(parts), style="dim"), expand=True)
                # Hint about selection: RichLog doesn't support in-app
                # mouse selection upstream; document the terminal-native
                # path so users can copy output.
                self.rich_log.write(
                    Text(
                        "Tip: hold Option/Alt (macOS) or Shift (most terminals) "
                        "while dragging to select text, or press Ctrl+S to toggle "
                        "terminal-select mode (disables Textual mouse).",
                        style="dim italic",
                    ),
                    expand=True,
                )
            _chat_debug("on_mount: banner written")

            # Construct the chat event loop.
            from events.chat_loop import ChatEventLoop

            _chat_debug("on_mount: creating ChatEventLoop")
            self.chat_loop = ChatEventLoop(
                base_url=self.server_info.base_url,
                session_id=self.session_id,
                console=self.console_proxy,
                auth_token=self.server_info.password,
                workspace_dir=str(Path(__file__).resolve().parents[2]),
                debug=_chat_debug if self.args and self.args.debug else None,
            )

            # Raw daemon thread — the SSE consumer.
            _chat_debug("on_mount: starting SSE consumer (raw daemon thread)")
            self.chat_loop.start_consumer(self._render_and_log)
            _chat_debug("on_mount: consumer thread started")

            # Initial prompt: send via worker but don't echo the full text.
            # The prompt comes from prompts/chat-initial.md (bootstrap
            # instructions for the agent, not something the user typed).
            # The SSE stream will emit a dim `> User` summary line once the
            # daemon acknowledges the message, matching subsequent prompts.
            if self.initial_prompt:
                self.rich_log.write(Text("(initializing session\u2026)", style="bold cyan"), expand=True)
                _chat_debug(f"on_mount: spawning initial-prompt worker ({len(self.initial_prompt)} chars)")
                self._send_initial_prompt(self.initial_prompt)

            _chat_debug("on_mount: done")

        # --- Main-thread heartbeat canary ---

        def _heartbeat(self) -> None:
            self._heartbeat_count += 1
            _chat_debug(f"_heartbeat: tick #{self._heartbeat_count} (main loop alive)")

            # Update the bottom-bar state lane and the right-aligned
            # metadata lane. Both are fed by event-arrival updates from
            # _render_and_log on the consumer thread.
            pulse = "\u25cf" if self._heartbeat_count % 2 else "\u25cc"
            sel_tag = " [SEL]" if self._terminal_select_mode else ""
            connected = getattr(self, "_modeline_connected", True)
            state = getattr(self, "_modeline_state", "idle")
            state_since = getattr(self, "_modeline_state_since", None)

            if not connected:
                state_icon = "\u00b7"
                state_text = "Offline"
            elif state == "thinking":
                state_icon = "~"
                if state_since is None:
                    state_text = "Thinking..."
                else:
                    elapsed = max(time.monotonic() - state_since, 0.0)
                    state_text = "Thinking..." if elapsed < 2.0 else f"Thinking {elapsed:.1f}s"
            elif state == "busy":
                state_icon = ">"
                state_text = "Busy"
            else:
                state_icon = "\u00b7"
                state_text = "Idle"

            self.modeline.update(f"{pulse}{sel_tag} {state_icon} {state_text}")

            meta = getattr(self, "_modeline_meta", "") or ""
            if not meta:
                provider = (self.model or "").split("/", 1)[0] if self.model else ""
                _model_id = (self.model or "").split("/", 1)[1] if self.model and "/" in self.model else (self.model or "\u2026")
                meta = f"{provider}/{_model_id}" if provider else _model_id
            if self.modeline_meta is not None:
                self.modeline_meta.update(meta)

        # --- Textual workers (@work(thread=True)) — short-lived only ---

        @work(thread=True)
        def _send_initial_prompt(self, text) -> None:
            """Send the initial prompt in a Textual-managed thread."""
            _chat_debug("_send_initial_prompt: worker started")
            try:
                self.chat_loop.send_prompt(
                    text,
                    self.args.agent if self.args else "auditor",
                    self.model,
                    self.variant,
                )
                _chat_debug("_send_initial_prompt: sent")
            except Exception as exc:
                _chat_debug(f"_send_initial_prompt: error: {exc}")
                self._post_error_renderable(f"Failed to send initial prompt: {exc}")

        @work(thread=True)
        def _send_prompt(self, text) -> None:
            """Send a user prompt in a Textual-managed thread."""
            _chat_debug(f"_send_prompt: worker posting text len={len(text)}")
            try:
                self.chat_loop.send_prompt(
                    text,
                    self.args.agent if self.args else "auditor",
                    self.model,
                    self.variant,
                )
                _chat_debug("_send_prompt: sent")
            except Exception as exc:
                _chat_debug(f"_send_prompt: error: {exc}")
                self._post_error_renderable(f"Failed to send: {exc}")

        def _post_error_renderable(self, detail: str) -> None:
            """Helper callable from any thread.  Posts a RenderMessage
            carrying a red error panel — sent through the same single
            RenderMessage(renderable) path as everything else."""
            from rich.panel import Panel

            panel = Panel(Text(detail, style="bold red"), title="Chat Error", border_style="red")
            self.post_message(self.RenderMessage(panel))

        # --- Message handler (run on main thread).  Single handler,
        # single Message subclass — see RenderMessage docstring.

        @on(RenderMessage)
        def _on_render_message(self, message: RenderMessage) -> None:
            if self.rich_log is not None:
                self.rich_log.write(message.renderable, expand=True)

        # --- Consumer-thread callback ---

        def _render_and_log(self, console, phase, label, event):
            _chat_render_and_log(self, console, phase, label, event)

        def _update_modeline_info(self, event: dict[str, Any]) -> None:
            _chat_update_modeline_info(self, event)

        # --- UI actions ---

        def action_request_quit(self) -> None:
            def finish_quit(confirmed):
                if confirmed:
                    self.exit()

            self.push_screen(_QuitScreen(), finish_quit)

        def action_toggle_mouse_for_select(self) -> None:
            """Toggle terminal-native mouse selection mode (Ctrl+S).

            RichLog has no upstream support for in-app mouse text
            selection.  As a pragmatic alternative, this action toggles
            Textual's mouse reporting off so the terminal emulator's
            native mouse selection takes over (which copies to the
            system clipboard via the terminal itself).

            When off (default): Textual handles mouse, terminal-native
            drag is intercepted.  Hold Option/Alt (macOS) or Shift
            (most terminals) while dragging to bypass Textual without
            toggling.

            When on: mouse reporting is disabled at the terminal level.
            User can click-drag to select, and Cmd+C / Ctrl+Shift+C in
            the terminal copies to the clipboard.  Textual mouse
            interactions (scrolling, clicking widgets) won't work until
            toggled back.
            """
            driver = self._driver
            if driver is None:
                return
            if not self._terminal_select_mode:
                # Enter terminal-select mode: turn off Textual mouse.
                try:
                    # TODO(phase-a4): These are private Textual APIs; they may break
                    # on future releases. Replace with public API once available.
                    driver._disable_mouse_support()
                except Exception:
                    return
                self._terminal_select_mode = True
                hint = Text(
                    "[select mode ON] Textual mouse disabled. "
                    "Click-drag to select; copy via terminal "
                    "(Cmd+C on macOS / Ctrl+Shift+C on Linux). "
                    "Press Ctrl+S again to exit.",
                    style="bold yellow",
                )
                self.rich_log.write(hint, expand=True)
            else:
                # Exit terminal-select mode: turn Textual mouse back on.
                try:
                    # TODO(phase-a4): These are private Textual APIs; they may break
                    # on future releases. Replace with public API once available.
                    driver._enable_mouse_support()
                except Exception:
                    return
                self._terminal_select_mode = False
                hint = Text(
                    "[select mode OFF] Textual mouse re-enabled.",
                    style="bold yellow",
                )
                self.rich_log.write(hint, expand=True)

        async def on_input_submitted(self, message: Input.Submitted) -> None:
            """Handle Enter on the chat Input — send the typed prompt
            through the @work(thread=True) _send_prompt worker.

            The Input is NOT disabled while sending — bisection found
            that toggling the Input's disabled/placeholder state from
            outside this handler (via a poller) broke Textual dispatch
            on this version.  Keeping the input always-enabled is fine
            in practice; the user just sees their next input echoed
            after the previous response."""
            text = message.value.strip()
            if not text:
                return
            self.chat_input.value = ""
            self.rich_log.write("", expand=True)
            self.rich_log.write(Text(f"User: {text}", style="bold cyan"), expand=True)
            self._send_prompt(text)

    ChatApp = _ChatApp
    QuitScreen = _QuitScreen

except ImportError:
    pass
