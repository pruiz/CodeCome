#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""Deterministic parity test between opencode run and opencode serve using a mock LLM.

Usage:
  python tools/mock-llm-parity.py --script tools/mock_llm_scripts/basic.json
"""

from __future__ import annotations

import argparse
import copy
import difflib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from events import EventLoop  # noqa: E402
from opencode.serve import ServerRunner  # noqa: E402

DEFAULT_PROMPT = "Say hello and then stop."
DEFAULT_MODEL = "test/mockmodel"
DEFAULT_AGENT = "test"
DEFAULT_TIMEOUT_S = 30.0
MOCK_HOST = "127.0.0.1"

# Events that only appear in the serve path and should be ignored for parity.
# Note: session.status (retry/busy) is NOT serve-only when _CODECOME_INSIDE_HARNESS=1
# because the status-forwarder plugin emits them to stdout.
# session.idle is deprecated and serve-only.
_SERVE_ONLY_TYPES = {"server.connected", "server.heartbeat", "session.idle", "message.updated", "file.edited", "file.watcher.updated", "todo.updated"}


def _step_sort_key(ev: dict[str, Any]) -> tuple[int, str]:
    """Return a sort key that orders events within a single step deterministically."""
    t = ev.get("type", "")
    if t == "step_start":
        return (0, "")
    if t == "text":
        return (1, ev.get("part", {}).get("text", "")[:50])
    if t == "tool_use":
        call_id = str(ev.get("part", {}).get("callID", ""))
        return (2, call_id)
    if t == "step_finish":
        return (3, "")
    # session.status and error events sort after tool_use but before step_finish
    # to keep them grouped with the step they occur in.
    if t in ("session.status", "error"):
        return (2.5, "")
    return (4, "")


def _sort_events_by_step(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group events by step (delimited by step_start) and sort within each step.
    Also deduplicate session.status events by status_type to handle
    transient status changes that don't affect parity.
    """
    # Deduplicate session.status events by (status_type, status_message).
    # Both run and serve may emit slightly different counts of busy/idle
    # events depending on timing, but the important ones (retry on error)
    # should match.
    seen_status: set[tuple] = set()
    deduped: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("type") == "session.status":
            key = (ev.get("status_type"), ev.get("status_message"))
            if key in seen_status:
                continue
            seen_status.add(key)
        deduped.append(ev)
    events = deduped

    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("type") == "step_start":
            if current:
                groups.append(current)
            current = [ev]
        else:
            current.append(ev)
    if current:
        groups.append(current)

    result: list[dict[str, Any]] = []
    for group in groups:
        result.extend(sorted(group, key=_step_sort_key))
    return result


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class MockServerInfo:
    """Lightweight wrapper around a running mock server process."""

    __slots__ = ("proc", "port")

    def __init__(self, proc: subprocess.Popen[Any], port: int) -> None:
        self.proc = proc
        self.port = port


def _find_free_port(host: str = MOCK_HOST) -> int:
    """Find a free TCP port on the given host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        s.listen(1)
        return int(s.getsockname()[1])


def start_mock_server(script_path: Path, host: str = MOCK_HOST, after_429: int = -1, after_500: int = -1) -> MockServerInfo:
    port = _find_free_port(host)
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "mock-llm-server.py"),
        "--port",
        str(port),
        "--script",
        str(script_path),
    ]
    if after_429 >= 0:
        cmd.extend(["--429-after", str(after_429)])
    if after_500 >= 0:
        cmd.extend(["--500-after", str(after_500)])
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        bufsize=1,
        text=True,
    )

    # Poll health check until the server is ready.
    health_deadline = time.time() + 10.0
    while time.time() < health_deadline:
        if proc.poll() is not None:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(
                f"Mock LLM server exited early (code {proc.returncode}). stderr: {stderr}"
            )
        try:
            req = urllib.request.Request(f"http://{host}:{port}/v1/models", method="GET")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return MockServerInfo(proc, port)
        except Exception:
            pass
        time.sleep(0.1)

    proc.terminate()
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    raise RuntimeError("Mock LLM server failed health check after startup.")


def stop_mock_server(info: MockServerInfo) -> None:
    info.proc.terminate()
    try:
        info.proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        info.proc.kill()
        info.proc.wait()
    # Drain stdout/stderr so the OS buffers get closed (prevents BufferedReader leak).
    if info.proc.stdout:
        try:
            info.proc.stdout.read()
        except Exception:
            pass
    if info.proc.stderr:
        try:
            info.proc.stderr.read()
        except Exception:
            pass


def _post_json(url: str, payload: dict[str, Any], timeout: float = 30.0, auth_token: str | None = None, workspace_dir: str | None = None) -> Any:
    headers = {"Content-Type": "application/json"}
    if auth_token:
        import base64
        encoded = base64.b64encode(f"opencode:{auth_token}".encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {encoded}"
    if workspace_dir:
        headers["x-opencode-directory"] = workspace_dir
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else None


def run_reference(prompt: str, model: str, agent: str, timeout: float) -> list[dict[str, Any]]:
    cmd = [
        "opencode",
        "run",
        "--format",
        "json",
        "--agent",
        agent,
        "--model",
        model,
        prompt,
    ]
    env = os.environ.copy()
    env["_CODECOME_INSIDE_HARNESS"] = "1"
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env)
    events: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _create_model_payload(model: str, *, create: bool) -> dict[str, str]:
    parts = model.split("/", 1)
    if len(parts) == 2:
        if create:
            return {"providerID": parts[0], "id": parts[1]}
        return {"providerID": parts[0], "modelID": parts[1]}
    key = "id" if create else "modelID"
    return {key: model}


def run_serve(prompt: str, model: str, agent: str, timeout: float) -> list[dict[str, Any]]:
    runner = ServerRunner()
    info = runner.start(hostname="127.0.0.1", log_level="WARN")
    base_url = info.base_url

    collected: list[dict[str, Any]] = []

    def collect_render(console: Any, phase: str, label: str, event: dict[str, Any]) -> None:
        collected.append(event)

    try:
        created = _post_json(
            f"{base_url}/session",
            {
                "title": "MockLLM parity test",
                "agent": agent,
                "model": _create_model_payload(model, create=True),
            },
            timeout=10.0,
            auth_token=info.password,
            workspace_dir=str(ROOT),
        )
        session_id = str(created.get("id", ""))
        if not session_id:
            raise RuntimeError("session.create returned empty id")

        loop = EventLoop(base_url, session_id, None, "1", "recon", auth_token=info.password, workspace_dir=str(ROOT))

        # Start event consumer BEFORE sending prompt to avoid losing early SSE events.
        import threading

        event_result_box: dict[str, Any] = {}

        def _consume() -> None:
            try:
                event_result_box["result"] = loop.run(collect_render)
            except Exception as exc:
                event_result_box["error"] = exc

        consumer = threading.Thread(target=_consume, name=f"parity-events-{session_id}", daemon=True)
        consumer.start()

        body = {
            "parts": [{"type": "text", "text": prompt}],
            "agent": agent,
            "model": _create_model_payload(model, create=False),
        }
        _post_json(
            f"{base_url}/session/{session_id}/prompt_async",
            body,
            timeout=timeout,
            auth_token=info.password,
            workspace_dir=str(ROOT),
        )

        consumer.join()
        if "error" in event_result_box:
            raise event_result_box["error"]
    finally:
        runner.stop()

    return collected


def normalize_event(ev: dict[str, Any]) -> dict[str, Any] | None:
    """Remove volatile fields and serve-only events for comparison."""
    ev_type = ev.get("type", "")
    if ev_type in _SERVE_ONLY_TYPES:
        return None
    out = dict(ev)

    # Normalize session.error to "error" type to match run path output.
    # Run emits: {"type": "error", error: {...}}
    # Serve emits: {"type": "session.error", properties: {sessionID, error: {...}}}
    if ev_type == "session.error":
        props = out.pop("properties", {})
        out["type"] = "error"
        out["error"] = props.get("error")
        out.pop("timestamp", None)
        return out

    # Normalize session.status to a flat structure for comparison.
    # Both paths emit the same session.status event structure when
    # _CODECOME_INSIDE_HARNESS=1 is set (status-forwarder plugin active).
    if ev_type == "session.status":
        props = out.pop("properties", {})
        status = props.get("status", {})
        out["status_type"] = status.get("type")
        out["status_attempt"] = status.get("attempt")
        out["status_message"] = status.get("message")
        out["status_next"] = status.get("next")
        out.pop("timestamp", None)
        out.pop("sessionID", None)
        out.pop("id", None)
        return out

    out.pop("timestamp", None)
    out.pop("sessionID", None)
    out.pop("id", None)
    part = out.get("part")
    if isinstance(part, dict):
        part = dict(part)
        part.pop("time", None)
        part.pop("id", None)
        part.pop("messageID", None)
        part.pop("sessionID", None)
        # Truncate large tool output/preview to avoid spurious diff noise
        if ev_type == "tool_use":
            state = part.get("state")
            if isinstance(state, dict):
                state = dict(state)
                for key in ("output", "error"):
                    val = state.get(key)
                    if isinstance(val, str) and len(val) > 200:
                        state[key] = f"<truncated len={len(val)}>"
                metadata = state.get("metadata")
                if isinstance(metadata, dict):
                    metadata = dict(metadata)
                    for key in ("preview", "output"):
                        val = metadata.get(key)
                        if isinstance(val, str) and len(val) > 200:
                            metadata[key] = f"<truncated len={len(val)}>"
                    state["metadata"] = metadata
                # Remove execution timing from tool state
                state.pop("time", None)
                part["state"] = state
        out["part"] = part
    return out


def compare_events(
    run_events: list[dict[str, Any]], serve_events: list[dict[str, Any]]
) -> tuple[bool, str]:
    run_norm = [normalize_event(e) for e in run_events if normalize_event(e) is not None]
    serve_norm = [normalize_event(e) for e in serve_events if normalize_event(e) is not None]

    run_sorted = _sort_events_by_step(run_norm)
    serve_sorted = _sort_events_by_step(serve_norm)

    run_lines = [json.dumps(e, sort_keys=True) for e in run_sorted]
    serve_lines = [json.dumps(e, sort_keys=True) for e in serve_sorted]

    if run_lines == serve_lines:
        return True, ""

    diff = list(
        difflib.unified_diff(
            run_lines,
            serve_lines,
            fromfile="opencode-run",
            tofile="opencode-serve",
            lineterm="",
        )
    )
    return False, "\n".join(diff)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic parity test between opencode run and opencode serve"
    )
    parser.add_argument(
        "--script",
        type=Path,
        default=ROOT / "tools" / "mock_llm_scripts" / "basic.json",
    )
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--agent", default=DEFAULT_AGENT)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--429-after", type=int, default=-1, help="Make mock server return 429 after this many requests (-1 = disabled)")
    parser.add_argument("--500-after", type=int, default=-1, help="Make mock server return 500 after this many requests (-1 = disabled)")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "tmp" / "mock-llm-parity",
    )
    args = parser.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        out_dir / "meta.json",
        {
            "script": str(args.script),
            "prompt": args.prompt,
            "model": args.model,
            "agent": args.agent,
            "timeout": args.timeout,
        },
    )

    config_path = ROOT / "opencode.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    original_base_url = config.get("provider", {}).get("test", {}).get("options", {}).get("baseURL", "")
    mock_info: MockServerInfo | None = None

    try:
        # --- Start mock server and rewrite provider URL -------------------
        mock_info = start_mock_server(args.script, after_429=args.__dict__.get("429_after", -1), after_500=args.__dict__.get("500_after", -1))
        config["provider"]["test"]["options"]["baseURL"] = f"http://{MOCK_HOST}:{mock_info.port}/v1"
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

        run_events = run_reference(args.prompt, args.model, args.agent, args.timeout)

        # Clean up files created by run_reference to ensure serve starts with a clean workspace.
        # This prevents 'exists' metadata in write tool from reflecting leftover state.
        for f in ROOT.glob("tmp/parity-*.txt"):
            f.unlink()

        serve_events = run_serve(args.prompt, args.model, args.agent, args.timeout)
    finally:
        # --- Restore original provider URL --------------------------------
        if mock_info is not None:
            stop_mock_server(mock_info)
        if "options" not in config["provider"]["test"]:
            config["provider"]["test"]["options"] = {}
        if original_base_url:
            config["provider"]["test"]["options"]["baseURL"] = original_base_url
        else:
            config["provider"]["test"]["options"].pop("baseURL", None)
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    _write_json(out_dir / "run.json", run_events)
    _write_json(out_dir / "serve.json", serve_events)

    ok, diff = compare_events(run_events, serve_events)
    if ok:
        print("Parity OK")
        return 0

    print("Parity FAILED", file=sys.stderr)
    diff_path = out_dir / "diff.txt"
    diff_path.write_text(diff, encoding="utf-8")
    print(f"Diff written to {diff_path}", file=sys.stderr)
    print(diff, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
