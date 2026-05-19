#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""Minimal OpenAI-compatible mock LLM server for deterministic parity testing.

Reads a JSON script file and serves standard endpoints:
  GET  /v1/models
  POST /v1/chat/completions  (streaming SSE)

The JSON script is a list of actions:
  {"type": "text", "content": "Hello!"}
  {"type": "tool_call", "id": "call_1", "name": "read", "arguments": {"filePath": "foo.txt"}}
  {"type": "tool_call", "id": "call_2", "name": "read", "arguments": {"filePath": "bar.txt"}}
  {"type": "text", "content": "Done."}
  {"type": "done"}

Multi-turn support:
  A "turn" = optional leading text + all consecutive tool_calls that follow it.
  The turn ends when the next action is text (after tools) or done.
  The server counts tool result messages in the incoming request to determine
  which turn to serve (stateless dispatch).

Usage:
  python tools/mock-llm-server.py --port 0 --script tools/mock_llm_scripts/basic.json
  # Prints: MockLLM serving on http://127.0.0.1:49234
"""

from __future__ import annotations

import argparse
import json
import socketserver
import sys
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path


def _parse_script_into_turns(script: list[dict]) -> list[list[dict]]:
    """Split a linear script into turns.

    A turn is: optional text + all consecutive tool_calls that follow it.
    The 'done' action marks the end of the conversation and is its own turn.
    """
    turns: list[list[dict]] = []
    current_turn: list[dict] = []
    in_tool_block = False

    for action in script:
        action_type = action.get("type", "")

        if action_type == "done":
            # Flush current turn if any
            if current_turn:
                turns.append(current_turn)
                current_turn = []
            # done is its own sentinel turn
            turns.append([action])
            break

        if action_type == "text":
            if in_tool_block and current_turn:
                # Previous turn ended with tools; start new turn
                turns.append(current_turn)
                current_turn = []
            current_turn.append(action)
            in_tool_block = False
        elif action_type == "tool_call":
            current_turn.append(action)
            in_tool_block = True
        else:
            # Unknown action type — pass through in current turn
            current_turn.append(action)

    # Flush final turn if not done yet
    if current_turn:
        turns.append(current_turn)

    return turns


def _count_tool_results(messages: list[dict]) -> int:
    """Count how many tool/role messages are in the conversation history."""
    count = 0
    for m in messages:
        role = m.get("role", "")
        if role in ("tool", "function"):
            count += 1
        # Also check for tool_call_id which indicates a tool result
        if m.get("tool_call_id"):
            count += 1
    return count


class MockLLMHandler(BaseHTTPRequestHandler):
    """Handle OpenAI-compatible requests with deterministic scripted responses."""

    script: list[dict] = []
    turns: list[list[dict]] = []
    server_version = "MockLLM/1.0"

    def log_message(self, format: str, *args: object) -> None:
        pass

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse(self, chunks: list[str]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(f"data: {chunk}\n\n".encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def do_GET(self) -> None:
        if self.path == "/v1/models":
            self._send_json({
                "object": "list",
                "data": [{"id": "mockmodel", "object": "model"}],
            })
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        if self.path == "/v1/chat/completions":
            try:
                content_len = int(self.headers.get("Content-Length", "0"))
                if content_len:
                    body = self.rfile.read(content_len)
                    payload = json.loads(body.decode("utf-8"))
                else:
                    payload = {}
            except Exception:
                payload = {}

            # Determine which turn to serve based on conversation history.
            # Each assistant message in the history corresponds to a completed turn.
            messages = payload.get("messages", [])
            assistant_count = sum(1 for m in messages if m.get("role") == "assistant")
            turns = self.__class__.turns
            turn_index = assistant_count
            if turn_index >= len(turns):
                turn_index = len(turns) - 1 if turns else 0

            chunks = self._build_chunks_for_turn(turn_index)
            self._send_sse(chunks)
        else:
            self.send_response(404)
            self.end_headers()

def _build_chunks(turns: list[list[dict]], turn_index: int) -> list[str]:
    """Build SSE chunks for a specific turn."""
    chunks: list[str] = []

    if not turns or turn_index >= len(turns):
        # No more turns — emit empty stop
        chunks.append(
            json.dumps({
                "id": "mock-chunk-empty",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "mockmodel",
                "choices": [
                    {"index": 0, "delta": {}, "finish_reason": "stop"}
                ],
            })
        )
        return chunks

    turn = turns[turn_index]

    # Standard role delta
    chunks.append(
        json.dumps({
            "id": "mock-chunk-0",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "mockmodel",
            "choices": [
                {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
            ],
        })
    )

    # Separate text and tool actions
    text_actions = [a for a in turn if a.get("type") == "text"]
    tool_actions = [a for a in turn if a.get("type") == "tool_call"]
    is_done_turn = any(a.get("type") == "done" for a in turn)

    # Emit text deltas
    for action in text_actions:
        chunks.append(
            json.dumps({
                "id": "mock-chunk",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "mockmodel",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": action["content"]},
                        "finish_reason": None,
                    }
                ],
            })
        )

    # Emit tool_calls deltas (all tools in this turn share the same assistant message)
    if tool_actions:
        for idx, action in enumerate(tool_actions):
            tool_id = action.get("id", f"call_{idx+1}")
            tool_name = action["name"]
            arguments = json.dumps(action.get("arguments", {}))
            chunks.append(
                json.dumps({
                    "id": "mock-chunk",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": "mockmodel",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": idx,
                                        "id": tool_id,
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": arguments,
                                        },
                                    }
                                ]
                            },
                            "finish_reason": None,
                        }
                    ],
                })
            )

    # Determine finish_reason
    if is_done_turn:
        finish_reason = "stop"
    elif tool_actions:
        finish_reason = "tool_calls"
    else:
        finish_reason = "stop"

    chunks.append(
        json.dumps({
            "id": "mock-chunk",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "mockmodel",
            "choices": [
                {"index": 0, "delta": {}, "finish_reason": finish_reason}
            ],
        })
    )

    return chunks


class MockLLMHandler(BaseHTTPRequestHandler):
    """Handle OpenAI-compatible requests with deterministic scripted responses."""

    script: list[dict] = []
    turns: list[list[dict]] = []
    server_version = "MockLLM/1.0"

    def log_message(self, format: str, *args: object) -> None:
        pass

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse(self, chunks: list[str]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(f"data: {chunk}\n\n".encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def do_GET(self) -> None:
        if self.path == "/v1/models":
            self._send_json({
                "object": "list",
                "data": [{"id": "mockmodel", "object": "model"}],
            })
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        if self.path == "/v1/chat/completions":
            try:
                content_len = int(self.headers.get("Content-Length", "0"))
                if content_len:
                    body = self.rfile.read(content_len)
                    payload = json.loads(body.decode("utf-8"))
                else:
                    payload = {}
            except Exception:
                payload = {}

            # Determine which turn to serve based on conversation history.
            # Each assistant message in the history corresponds to a completed turn.
            messages = payload.get("messages", [])
            assistant_count = sum(1 for m in messages if m.get("role") == "assistant")
            turns = self.__class__.turns
            turn_index = assistant_count
            if turn_index >= len(turns):
                turn_index = len(turns) - 1 if turns else 0

            chunks = _build_chunks(turns, turn_index)
            self._send_sse(chunks)
        else:
            self.send_response(404)
            self.end_headers()


def main() -> int:
    parser = argparse.ArgumentParser(description="Mock OpenAI-compatible LLM server")
    parser.add_argument("--port", type=int, default=0, help="Port (0 = ephemeral)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--script", type=Path, required=True)
    args = parser.parse_args()

    if not args.script.exists():
        print(f"Script not found: {args.script}", file=sys.stderr)
        return 1

    with args.script.open("r", encoding="utf-8") as fh:
        script = json.load(fh)

    MockLLMHandler.script = script
    MockLLMHandler.turns = _parse_script_into_turns(script)

    with socketserver.ThreadingTCPServer((args.host, args.port), MockLLMHandler) as httpd:
        actual_port = httpd.server_address[1]
        print(f"MockLLM serving on http://{args.host}:{actual_port} (script: {args.script})")
        sys.stdout.flush()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
