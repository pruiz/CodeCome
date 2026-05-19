from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from conftest import ROOT


def load_parity_module():
    sys_path = str(ROOT / "tools")
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    import mock_llm_parity
    return mock_llm_parity


class TestMockLLMServer:
    """Unit tests for the mock LLM server."""

    @pytest.fixture(scope="class")
    def server_proc(self):
        script = ROOT / "tools" / "mock_llm_scripts" / "basic.json"
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "tools" / "mock_llm_server.py"), "--port", "0", "--script", str(script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        first_line = proc.stdout.readline()
        import re
        m = re.search(r"http://[^:]+:(\d+)", first_line)
        if not m:
            proc.terminate()
            pytest.fail(f"Could not parse port from server output: {first_line!r}")
        port = int(m.group(1))
        # Health-check
        deadline = time.time() + 5.0
        while time.time() < deadline:
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/models", method="GET")
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                pass
            time.sleep(0.2)
        else:
            proc.terminate()
            pytest.fail("Mock server failed to start")
        yield proc, port
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    def test_models_endpoint(self, server_proc):
        _, port = server_proc
        req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/models", method="GET")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode())
        assert data["object"] == "list"
        assert any(m["id"] == "mockmodel" for m in data["data"])

    def test_chat_completions_streaming(self, server_proc):
        _, port = server_proc
        body = json.dumps({
            "model": "mockmodel",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        }).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            lines = resp.read().decode().splitlines()
        chunks = [json.loads(line[6:]) for line in lines if line.startswith("data: ") and line != "data: [DONE]"]
        assert any(c["choices"][0]["delta"].get("role") == "assistant" for c in chunks)
        assert any(c["choices"][0]["delta"].get("content") == "Hello world!" for c in chunks)

    def test_multi_tool_chunks_have_increasing_index(self, server_proc):
        """Verify that multiple tools in one turn get index 0, 1, 2..."""
        # Build chunks directly without going through the server process.
        script = [
            {"type": "text", "content": "Reading files."},
            {"type": "tool_call", "id": "call_1", "name": "read", "arguments": {"filePath": "README.md"}},
            {"type": "tool_call", "id": "call_2", "name": "read", "arguments": {"filePath": "AGENTS.md"}},
            {"type": "text", "content": "Done."},
            {"type": "done"},
        ]
        sys.path.insert(0, str(ROOT / "tools"))
        import mock_llm_server
        turns = mock_llm_server._parse_script_into_turns(script)
        chunks = mock_llm_server._build_chunks(turns, 0)
        parsed = [json.loads(c) for c in chunks]
        tool_chunks = [c for c in parsed if "tool_calls" in c["choices"][0]["delta"]]
        assert len(tool_chunks) == 2, f"Expected 2 tool chunks, got {len(tool_chunks)}"
        assert tool_chunks[0]["choices"][0]["delta"]["tool_calls"][0]["index"] == 0
        assert tool_chunks[1]["choices"][0]["delta"]["tool_calls"][0]["index"] == 1


class TestNormalizeEvent:
    """Unit tests for event normalization logic."""

    def test_normalize_strips_timestamps_and_ids(self):
        mod = load_parity_module()
        ev = {
            "type": "text",
            "timestamp": 12345,
            "sessionID": "ses_abc",
            "id": "evt_123",
            "part": {
                "id": "prt_1",
                "messageID": "msg_1",
                "sessionID": "ses_abc",
                "text": "hello",
                "type": "text",
                "time": {"start": 1, "end": 2},
            },
        }
        out = mod.normalize_event(ev)
        assert "timestamp" not in out
        assert "sessionID" not in out
        assert "id" not in out
        assert "time" not in out["part"]
        assert "id" not in out["part"]
        assert "messageID" not in out["part"]
        assert out["part"]["text"] == "hello"

    def test_normalize_filters_serve_only_types(self):
        mod = load_parity_module()
        for t in mod._SERVE_ONLY_TYPES:
            assert mod.normalize_event({"type": t}) is None

    def test_normalize_truncates_tool_output(self):
        mod = load_parity_module()
        long_preview = "x" * 500
        long_output = "y" * 500
        ev = {
            "type": "tool_use",
            "part": {
                "type": "tool",
                "state": {
                    "metadata": {"preview": long_preview},
                    "output": long_output,
                },
            },
        }
        out = mod.normalize_event(ev)
        state = out["part"]["state"]
        assert state["metadata"]["preview"].startswith("<truncated")
        assert state["output"].startswith("<truncated")

    def test_normalize_strips_tool_state_time(self):
        mod = load_parity_module()
        ev = {
            "type": "tool_use",
            "part": {
                "type": "tool",
                "state": {"time": {"start": 1, "end": 2}, "status": "completed"},
            },
        }
        out = mod.normalize_event(ev)
        assert "time" not in out["part"]["state"]


@pytest.mark.slow
class TestMockLLMParity:
    """End-to-end parity tests (heavy — invoke real opencode CLI)."""

    @pytest.mark.parametrize("script", [
    ROOT / "tools" / "mock_llm_scripts" / "basic.json",
    ROOT / "tools" / "mock_llm_scripts" / "with_tool.json",
    ROOT / "tools" / "mock_llm_scripts" / "with_permission.json",
    ROOT / "tools" / "mock_llm_scripts" / "comprehensive.json",
    ROOT / "tools" / "mock_llm_scripts" / "with_permission_multi.json",
])
    def test_parity_script(self, script: Path):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "mock_llm_parity.py"), "--script", str(script), "--timeout", "45"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120.0,
        )
        assert result.returncode == 0, (
            f"Parity failed for {script.name}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "Parity OK" in result.stdout
