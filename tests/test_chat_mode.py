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
        proxy = module.TextualConsoleProxy(fake_log)
        return proxy, fake_log

    def test_single_arg_writes_directly(self, proxy_and_log):
        proxy, fake_log = proxy_and_log
        from rich.text import Text
        proxy.print(Text("hello"))
        fake_log.write.assert_called_once()
        assert fake_log.write.call_args[0][0].plain == "hello"

    def test_no_args_writes_empty_line(self, proxy_and_log):
        proxy, fake_log = proxy_and_log
        proxy.print()
        fake_log.write.assert_called_once()

    def test_multi_args_wraps_in_group(self, proxy_and_log):
        proxy, fake_log = proxy_and_log
        from rich.text import Text
        proxy.print(Text("a"), Text("b"))
        fake_log.write.assert_called_once()
        # Should be a Group
        from rich.console import Group
        assert isinstance(fake_log.write.call_args[0][0], Group)


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
