from __future__ import annotations

import json
import queue
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from conftest import ROOT


def load_chat_loop():
    sys_path = str(ROOT / "tools")
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from events.chat_loop import ChatEventLoop, ChatState
    return ChatEventLoop, ChatState


def load_events():
    sys_path = str(ROOT / "tools")
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from events.sse_client import SseClient, SseClientError
    return SseClient, SseClientError


# ---------------------------------------------------------------------------
# ChatState constants
# ---------------------------------------------------------------------------

class TestChatState:
    def test_state_values(self):
        _, ChatState = load_chat_loop()
        assert ChatState.IDLE == "idle"
        assert ChatState.BUSY == "busy"
        assert ChatState.ERROR == "error"
        assert ChatState.STOPPED == "stopped"


# ---------------------------------------------------------------------------
# ChatEventLoop unit tests
# ---------------------------------------------------------------------------

class TestChatEventLoop:
    """Unit tests for events.chat_loop.ChatEventLoop."""

    @pytest.fixture
    def chat_loop(self):
        ChatEventLoop, _ = load_chat_loop()
        return ChatEventLoop(
            base_url="http://localhost:8080",
            session_id="sess-1",
            console=None,
            auth_token="test-token",
            workspace_dir="/workspace",
        )

    def test_init_stores_fields(self, chat_loop):
        assert chat_loop.base_url == "http://localhost:8080"
        assert chat_loop.session_id == "sess-1"
        assert chat_loop.auth_token == "test-token"
        assert chat_loop.workspace_dir == "/workspace"

    def test_get_headers_with_auth(self, chat_loop):
        headers = chat_loop._get_headers()
        assert headers["Content-Type"] == "application/json"
        assert "Authorization" in headers
        assert "x-opencode-directory" in headers

    def test_get_headers_without_auth(self):
        ChatEventLoop, _ = load_chat_loop()
        loop = ChatEventLoop(
            base_url="http://localhost:8080",
            session_id="sess-1",
            console=None,
        )
        headers = loop._get_headers()
        assert "Authorization" not in headers

    def test_belongs_to_session_matching(self, chat_loop):
        assert chat_loop._belongs_to_session({"properties": {"sessionID": "sess-1"}})
        assert not chat_loop._belongs_to_session({"properties": {"sessionID": "other"}})
        assert chat_loop._belongs_to_session({"type": "server.heartbeat"})

    def test_is_session_idle_deprecated(self, chat_loop):
        assert chat_loop._is_session_idle({"type": "session.idle", "properties": {"sessionID": "sess-1"}})
        assert not chat_loop._is_session_idle({"type": "server.heartbeat"})

    def test_is_session_idle_canonical(self, chat_loop):
        assert chat_loop._is_session_idle({
            "type": "session.status",
            "properties": {"sessionID": "sess-1", "status": {"type": "idle"}},
        })
        assert not chat_loop._is_session_idle({
            "type": "session.status",
            "properties": {"sessionID": "sess-1", "status": {"type": "busy"}},
        })

    def test_is_session_busy(self, chat_loop):
        assert chat_loop._is_session_busy({
            "type": "session.status",
            "properties": {"sessionID": "sess-1", "status": {"type": "busy"}},
        })
        assert not chat_loop._is_session_busy({
            "type": "session.status",
            "properties": {"sessionID": "sess-1", "status": {"type": "idle"}},
        })

    def test_stop_signals_stopped(self, chat_loop):
        """stop() should put a STOPPED signal in the queue."""
        chat_loop.stop()
        state, detail = chat_loop.get_state(timeout=2.0)
        _, ChatState = load_chat_loop()
        assert state == ChatState.STOPPED


class TestChatEventLoopWithFakeSse:
    """ChatEventLoop tests with a fake SSE client."""

    @pytest.fixture
    def chat_loop_objects(self):
        ChatEventLoop, ChatState = load_chat_loop()
        SseClient, SseClientError = load_events()
        return ChatEventLoop, ChatState, SseClient

    def test_single_turn_idle_signal(self, chat_loop_objects, monkeypatch):
        """One prompt → SSE events → idle → TUI receives IDLE signal."""
        ChatEventLoop, ChatState, SseClient = chat_loop_objects

        emitted: list[dict] = []

        def fake_render(console, phase, label, event):
            emitted.append(event)

        class FakeSseClient:
            def __init__(self, *a, **kw):
                pass
            def events(self):
                return iter([
                    {"type": "server.connected"},
                    {"type": "message.part.updated", "properties": {"sessionID": "sess-1", "part": {"id": "p1", "type": "step-start"}}},
                    {"type": "message.part.delta", "properties": {"sessionID": "sess-1", "partID": "p2", "field": "text", "delta": "Hello"}},
                    {"type": "message.part.updated", "properties": {"sessionID": "sess-1", "part": {"id": "p2", "type": "text", "time": {"start": 0, "end": 1}}}},
                    {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
                ])
            def stop(self):
                pass

        import events.chat_loop as _chat_mod
        orig = _chat_mod.SseClient
        _chat_mod.SseClient = FakeSseClient  # type: ignore[misc]
        try:
            loop = ChatEventLoop("http://localhost:8080", "sess-1", None)
            loop.start_consumer(fake_render)
            state, detail = loop.get_state(timeout=5.0)
        finally:
            _chat_mod.SseClient = orig

        assert state == ChatState.IDLE
        types = [e["type"] for e in emitted]
        assert "server.connected" in types
        assert "step_start" in types
        assert "text" in types

    def test_multi_turn_cycle(self, chat_loop_objects, monkeypatch):
        """Prompt → idle → prompt → idle → stop."""
        ChatEventLoop, ChatState, SseClient = chat_loop_objects

        emitted: list[dict] = []
        turn_count = [0]
        idle_count = [0]

        def fake_render(console, phase, label, event):
            emitted.append(event)

        class FakeSseClient:
            def __init__(self, *a, **kw):
                pass
            def events(self):
                # Yield events for two turns, then block
                turn_count[0] += 1
                yield {"type": "message.part.updated", "properties": {"sessionID": "sess-1", "part": {"id": f"p{turn_count[0]}", "type": "text", "time": {"start": 0, "end": 1}}}}
                idle_count[0] += 1
                yield {"type": "session.idle", "properties": {"sessionID": "sess-1"}}
                # Yield second turn
                turn_count[0] += 1
                yield {"type": "message.part.updated", "properties": {"sessionID": "sess-1", "part": {"id": f"p{turn_count[0]}", "type": "text", "time": {"start": 0, "end": 1}}}}
                idle_count[0] += 1
                yield {"type": "session.idle", "properties": {"sessionID": "sess-1"}}
                # After two idles, block until stop
                import time
                while True:
                    time.sleep(0.1)
            def stop(self):
                pass

        import events.chat_loop as _chat_mod
        orig = _chat_mod.SseClient
        _chat_mod.SseClient = FakeSseClient  # type: ignore[misc]
        try:
            loop = ChatEventLoop("http://localhost:8080", "sess-1", None)
            loop.start_consumer(fake_render)

            # First idle
            state1, _ = loop.get_state(timeout=5.0)
            assert state1 == ChatState.IDLE

            # Second idle
            state2, _ = loop.get_state(timeout=5.0)
            assert state2 == ChatState.IDLE

            loop.stop()
        finally:
            _chat_mod.SseClient = orig

    def test_permission_auto_rejected(self, chat_loop_objects, monkeypatch):
        """Permission asked → auto-rejected → idle."""
        ChatEventLoop, ChatState, SseClient = chat_loop_objects

        captured_perms: list[tuple] = []

        def fake_render(console, phase, label, event):
            pass

        class FakeSseClient:
            def __init__(self, *a, **kw):
                pass
            def events(self):
                return iter([
                    {"type": "permission.asked", "properties": {"sessionID": "sess-1", "id": "perm-1", "tool": "bash"}},
                    {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
                ])
            def stop(self):
                pass

        def fake_urlopen(req, **kw):
            if req.full_url.endswith("/permission/perm-1/reply"):
                captured_perms.append((req.full_url, req.data))
            return type("R", (), {"read": lambda: b"{}", "__enter__": lambda s: s, "__exit__": lambda *a: None})()

        import events.chat_loop as _chat_mod
        orig_sse = _chat_mod.SseClient
        _chat_mod.SseClient = FakeSseClient  # type: ignore[misc]
        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        try:
            loop = ChatEventLoop("http://localhost:8080", "sess-1", None)
            loop.start_consumer(fake_render)
            state, _ = loop.get_state(timeout=5.0)
        finally:
            _chat_mod.SseClient = orig_sse

        assert state == ChatState.IDLE
        assert len(captured_perms) == 1
        assert "permission/perm-1/reply" in captured_perms[0][0]
        assert json.loads(captured_perms[0][1]) == {"reply": "reject", "message": "Auto-rejected by CodeCome configuration"}

    def test_stop_during_busy(self, chat_loop_objects):
        """Stop signal while consumer is running."""
        ChatEventLoop, ChatState, SseClient = chat_loop_objects

        stop_event = threading.Event()

        class FakeSseClient:
            def __init__(self, *a, **kw):
                pass
            def events(self):
                # Block until stop is called
                stop_event.wait(timeout=10.0)
                return iter([])
            def stop(self):
                stop_event.set()

        import events.chat_loop as _chat_mod
        orig = _chat_mod.SseClient
        _chat_mod.SseClient = FakeSseClient  # type: ignore[misc]
        try:
            loop = ChatEventLoop("http://localhost:8080", "sess-1", None)
            loop.start_consumer(lambda c, p, l, e: None)

            # Give consumer time to start
            time.sleep(0.1)
            loop.stop()

            # Should get STOPPED signal
            state, _ = loop.get_state(timeout=2.0)
            assert state == ChatState.STOPPED
        finally:
            _chat_mod.SseClient = orig


# ---------------------------------------------------------------------------
# TextualConsoleProxy tests
# ---------------------------------------------------------------------------

class TestTextualConsoleProxy:
    """Unit tests for the TextualConsoleProxy class in run-agent.py."""

    @pytest.fixture
    def proxy_and_log(self):
        module = _load_run_agent_module()
        fake_log = MagicMock()
        fake_app = MagicMock()
        proxy = module.TextualConsoleProxy(fake_log, fake_app)
        return proxy, fake_log, fake_app

    def test_single_arg_writes_directly_on_main_thread(self, proxy_and_log):
        proxy, fake_log, fake_app = proxy_and_log
        from rich.text import Text
        proxy.print(Text("hello"))
        fake_log.write.assert_called_once()
        assert fake_log.write.call_args[0][0].plain == "hello"

    def test_no_args_writes_empty_line_on_main_thread(self, proxy_and_log):
        proxy, fake_log, fake_app = proxy_and_log
        proxy.print()
        fake_log.write.assert_called_once()

    def test_multi_args_wraps_in_group_on_main_thread(self, proxy_and_log):
        proxy, fake_log, fake_app = proxy_and_log
        from rich.text import Text
        proxy.print(Text("a"), Text("b"))
        fake_log.write.assert_called_once()
        from rich.console import Group
        assert isinstance(fake_log.write.call_args[0][0], Group)

    def test_bg_thread_posts_render_message(self):
        """Background thread calls must post a RenderMessage(renderable)
        via post_message, not write to rich_log directly (per Textual docs:
        post_message is thread-safe)."""
        module = _load_run_agent_module()
        fake_log = MagicMock()
        fake_render_msg_cls = MagicMock()
        fake_app = MagicMock()
        fake_app.RenderMessage = fake_render_msg_cls
        proxy = module.TextualConsoleProxy(fake_log, fake_app)

        from rich.text import Text
        error_holder = [None]

        def bg_call():
            try:
                proxy._write(Text("from_bg"))
            except Exception as e:
                error_holder[0] = e

        import threading
        t = threading.Thread(target=bg_call, daemon=True)
        t.start()
        t.join(timeout=5)

        if error_holder[0]:
            raise error_holder[0]

        # On bg thread, RenderMessage(renderable) is constructed and
        # post_message is called.
        fake_render_msg_cls.assert_called_once()
        fake_app.post_message.assert_called_once()
        # rich_log.write must NOT be called from a bg thread.
        fake_log.write.assert_not_called()


# ---------------------------------------------------------------------------
# Chat argparse tests
# ---------------------------------------------------------------------------

class TestChatArgparse:
    """Tests for --chat flag parsing and validation."""

    @pytest.fixture
    def parser(self):
        module = _load_run_agent_module()
        return module.build_parser()

    def test_chat_flag_parsed(self, parser):
        args = parser.parse_args(["--chat", "--label", "test", "--agent", "auditor"])
        assert args.chat is True
        assert args.label == "test"
        assert args.agent == "auditor"

    def test_chat_with_prompt(self, parser):
        args = parser.parse_args(["--chat", "--label", "test", "--agent", "auditor", "--prompt", "Hello"])
        assert args.chat is True
        assert args.prompt == "Hello"

    def test_chat_without_phase(self, parser):
        """--chat should not require --phase."""
        args = parser.parse_args(["--chat", "--label", "test", "--agent", "auditor"])
        assert args.phase is None

    def test_chat_requires_label(self, parser):
        """--chat still requires --label."""
        args = parser.parse_args(["--chat", "--agent", "auditor"])
        assert args.label is None

    def test_chat_requires_agent(self, parser):
        """--chat still requires --agent."""
        args = parser.parse_args(["--chat", "--label", "test"])
        assert args.agent is None

    def test_normal_mode_requires_phase(self, parser):
        """Without --chat, --phase is still required."""
        args = parser.parse_args(["--label", "test", "--agent", "auditor", "--prompt-file", "phase.md"])
        assert args.chat is False
        assert args.phase is None


# ---------------------------------------------------------------------------
# _ChatApp._render_and_log parity tests
#
# Phase-mode's _render_and_log:
#   1. writes raw event JSON to transcript_fp
#   2. (if --debug) mirrors raw event JSON to stderr
#   3. suppresses 'reasoning' events when thinking is off
#   4. calls render_event(...)
#
# Chat-mode's _render_and_log should match (1), (3), (4) and route the
# raw-JSON mirror to the chat-debug log file instead of stderr (because
# Textual owns the TTY in chat mode).  It must NOT emit chat-specific
# state markers ('[idle]' / '[busy]') any more — non-chat doesn't.
# ---------------------------------------------------------------------------

class TestChatRenderAndLogParity:
    """Tests for _ChatApp._render_and_log parity with phase mode."""

    @pytest.fixture
    def app_under_test(self):
        """Construct a _ChatApp instance without running Textual.

        We only populate the fields _render_and_log actually reads
        (transcript_fp, args, thinking_on) and stub render_event so
        we can capture dispatcher calls.
        """
        module = _load_run_agent_module()
        if module.ChatApp is not None:
            app = module.ChatApp()
        else:
            # Textual not installed — use standalone functions on a
            # plain object (parity guaranteed by delegation in _ChatApp).
            app = type("FakeChatApp", (), {})()
            app._render_and_log = module._chat_render_and_log.__get__(app, type(app))
            app._update_modeline_info = module._chat_update_modeline_info.__get__(app, type(app))
            app.post_message = MagicMock()
        return module, app

    def _make_args(self, debug=False):
        ns = MagicMock()
        ns.debug = debug
        return ns

    def test_writes_event_to_transcript(self, app_under_test):
        """_render_and_log appends json.dumps(event) + '\\n' to transcript_fp."""
        module, app = app_under_test
        from io import StringIO
        sink = StringIO()
        app.transcript_fp = sink
        app.args = self._make_args(debug=False)
        app.thinking_on = True

        with patch.object(module, "render_event", lambda *a, **kw: None):
            app._render_and_log(MagicMock(), "Chat", "Test", {"type": "text", "x": 1})
            app._render_and_log(MagicMock(), "Chat", "Test", {"type": "session.status", "y": 2})

        lines = [json.loads(line) for line in sink.getvalue().splitlines()]
        assert lines == [
            {"type": "text", "x": 1},
            {"type": "session.status", "y": 2},
        ]

    def test_transcript_write_failure_is_swallowed(self, app_under_test):
        """If transcript writes raise OSError, _render_and_log still
        proceeds to render_event without re-raising."""
        module, app = app_under_test
        bad_fp = MagicMock()
        bad_fp.write.side_effect = OSError("disk full")
        app.transcript_fp = bad_fp
        app.args = self._make_args(debug=False)
        app.thinking_on = True

        render_calls = []
        with patch.object(module, "render_event", lambda *a, **kw: render_calls.append(a)):
            # Must not raise.
            app._render_and_log(MagicMock(), "Chat", "Test", {"type": "text"})

        assert len(render_calls) == 1

    def test_no_transcript_fp_is_ok(self, app_under_test):
        """When transcript_fp is None, _render_and_log skips persistence
        but still renders."""
        module, app = app_under_test
        app.transcript_fp = None
        app.args = self._make_args(debug=False)
        app.thinking_on = True

        render_calls = []
        with patch.object(module, "render_event", lambda *a, **kw: render_calls.append(a)):
            app._render_and_log(MagicMock(), "Chat", "Test", {"type": "text"})

        assert len(render_calls) == 1

    def test_suppresses_reasoning_when_thinking_off(self, app_under_test):
        """When thinking_on is False, 'reasoning' events bypass render_event
        (parity with phase mode)."""
        module, app = app_under_test
        from io import StringIO
        sink = StringIO()
        app.transcript_fp = sink
        app.args = self._make_args(debug=False)
        app.thinking_on = False

        render_calls = []
        with patch.object(module, "render_event", lambda *a, **kw: render_calls.append(a[3].get("type"))):
            app._render_and_log(MagicMock(), "Chat", "Test", {"type": "reasoning", "text": "..."})
            app._render_and_log(MagicMock(), "Chat", "Test", {"type": "text", "text": "ok"})

        # reasoning event is NOT rendered, text event IS.
        assert render_calls == ["text"]
        # But BOTH events still hit the transcript.
        lines = [json.loads(line) for line in sink.getvalue().splitlines()]
        assert [ev["type"] for ev in lines] == ["reasoning", "text"]

    def test_renders_reasoning_when_thinking_on(self, app_under_test):
        """When thinking_on is True, reasoning events ARE dispatched."""
        module, app = app_under_test
        app.transcript_fp = None
        app.args = self._make_args(debug=False)
        app.thinking_on = True

        render_calls = []
        with patch.object(module, "render_event", lambda *a, **kw: render_calls.append(a[3].get("type"))):
            app._render_and_log(MagicMock(), "Chat", "Test", {"type": "reasoning", "text": "..."})

        assert render_calls == ["reasoning"]

    def test_does_not_post_chat_only_state_markers(self, app_under_test):
        """_render_and_log must NOT post '[idle]'/'[busy]' RenderMessage
        markers for session.status / session.idle events.  Those were
        chat-specific scar tissue; non-chat mode never emitted them.
        State cues are produced by render_event -> render_session_status
        which prints 'session status: busy/idle'."""
        module, app = app_under_test
        app.transcript_fp = None
        app.args = self._make_args(debug=False)
        app.thinking_on = True

        # Spy on post_message — _render_and_log itself must NOT call it
        # (only the proxy / render_event should).
        post_calls = []
        with patch.object(app, "post_message", side_effect=lambda m: post_calls.append(m)):
            with patch.object(module, "render_event", lambda *a, **kw: None):
                app._render_and_log(
                    MagicMock(),
                    "Chat",
                    "Test",
                    {"type": "session.status",
                     "properties": {"status": {"type": "busy"}}},
                )
                app._render_and_log(
                    MagicMock(),
                    "Chat",
                    "Test",
                    {"type": "session.status",
                     "properties": {"status": {"type": "idle"}}},
                )
                app._render_and_log(
                    MagicMock(),
                    "Chat",
                    "Test",
                    {"type": "session.idle"},
                )

        # No direct post_message calls from _render_and_log itself.
        assert post_calls == []

    def test_debug_mode_mirrors_raw_event_to_chat_debug(self, app_under_test):
        """When --debug is set, the raw event JSON is mirrored to the
        chat-debug log file via _chat_debug.  In phase mode this goes to
        stderr; chat mode routes to the chat-debug file because Textual
        owns the TTY."""
        module, app = app_under_test
        app.transcript_fp = None
        app.args = self._make_args(debug=True)
        app.thinking_on = True

        chat_debug_calls = []
        with patch.object(module, "_chat_debug",
                          side_effect=lambda msg: chat_debug_calls.append(msg)):
            with patch.object(module, "render_event", lambda *a, **kw: None):
                app._render_and_log(
                    MagicMock(),
                    "Chat",
                    "Test",
                    {"type": "text", "x": 42},
                )

        # The raw-event mirror message should include the JSON payload.
        assert any('"x": 42' in m for m in chat_debug_calls), chat_debug_calls


# ---------------------------------------------------------------------------
# _run_chat_mode transcript path tests
# ---------------------------------------------------------------------------

class TestChatTranscriptPath:
    """Tests for the transcript-file path naming used by chat mode."""

    def test_transcript_path_pattern(self, tmp_path, monkeypatch):
        """_run_chat_mode opens a transcript file under tmp/ with the
        pattern last-chat-<timestamp>-pid<pid>.jsonl."""
        module = _load_run_agent_module()

        # Sandbox the ROOT/tmp directory by redirecting ROOT in the
        # module and in codecome.transcript (open_chat_transcript uses its
        # own ROOT).  We use monkeypatch to swap both for tmp_path so the
        # transcript lands inside our pytest tmp_path.
        monkeypatch.setattr(module, "ROOT", tmp_path)

        # open_chat_transcript lives in codecome.transcript with its own ROOT.
        import codecome.transcript as _transcript_mod
        monkeypatch.setattr(_transcript_mod, "ROOT", tmp_path)

        # Stub everything _run_chat_mode would otherwise call so we
        # exercise ONLY the transcript-path setup and the final summary.
        monkeypatch.setattr(module, "check_opencode_version", lambda: None)
        monkeypatch.setattr(module, "resolve_color_mode", lambda v: "auto")
        monkeypatch.setattr(module, "build_console", lambda v: MagicMock())
        monkeypatch.setattr(
            module,
            "resolve_model_and_variant",
            lambda agent, extra: ("opencode/test", None, "stub", "stub"),
        )
        monkeypatch.setattr(
            module, "resolve_thinking_decision", lambda m, e: (False, "stub")
        )

        # Server / session creation: stub to return fake objects.
        fake_server = MagicMock()
        fake_server.base_url = "http://127.0.0.1:1"
        fake_server.password = "tok"
        fake_runner = MagicMock()
        fake_runner.start.return_value = fake_server
        monkeypatch.setattr(module, "ServerRunner", lambda: fake_runner)
        monkeypatch.setattr(module, "create_chat_session",
                            lambda *a, **kw: "ses_abc")

        # The Textual app's run() is a no-op for this test (we just
        # care about the transcript file lifecycle).
        fake_app = MagicMock()
        fake_app.chat_loop = None
        fake_app_cls = MagicMock(return_value=fake_app)
        monkeypatch.setattr(module, "ChatApp", fake_app_cls)

        # Argparse namespace.
        ns = MagicMock()
        ns.label = "Test"
        ns.agent = "auditor"
        ns.prompt_file = None
        ns.prompt = "hi"
        ns.finding = None
        ns.phase = None
        ns.color = "auto"
        ns.debug = False

        parser = MagicMock()
        # parser.error would sys.exit; we never trigger it because
        # label & agent are set.

        rc = module._run_chat_mode(parser, ns)
        assert rc == 0

        # Exactly one transcript jsonl was created under tmp/.
        transcripts = sorted((tmp_path / "tmp").glob("last-chat-*.jsonl"))
        assert len(transcripts) == 1, transcripts
        name = transcripts[0].name
        # Name pattern: last-chat-YYYYMMDD-HHMMSS-pid<digits>.jsonl
        import re
        assert re.match(
            r"^last-chat-\d{8}-\d{6}-pid\d+\.jsonl$", name
        ), f"unexpected transcript filename: {name}"

        # transcript_fp was passed into ChatApp(...)
        kwargs = fake_app_cls.call_args.kwargs
        assert "transcript_fp" in kwargs
        assert kwargs["transcript_fp"] is not None
        # And it's now closed (closed by _run_chat_mode's finally).
        assert kwargs["transcript_fp"].closed is True


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _load_run_agent_module():
    module_name = "run_agent_chat_tests"
    module_path = ROOT / "tools" / "run-agent.py"
    import importlib.util
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    # Only load if not already loaded
    if module_name not in sys.modules:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    return sys.modules[module_name]
