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
  {"type": "text", "content": "Done."}
  {"type": "done"}

Multi-turn support:
  The server maintains a simple turn counter.
  Turn 1 emits everything up to and including the first tool_call.
  Turn 2 emits everything after the first tool_call.
  This covers the standard OpenCode flow: assistant text → tool_call →
  tool execution → assistant final text.

Usage:
  python tools/mock_llm_server.py --port 0 --script tools/mock_llm_scripts/basic.json
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


class MockLLMHandler(BaseHTTPRequestHandler):
    """Handle OpenAI-compatible requests with deterministic scripted responses."""

    script: list[dict] = []
    turn_counter: int = 0
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

            # Detect if this request contains tool results (multi-turn).
            messages = payload.get("messages", [])
            has_tool_result = any(
                m.get("role") in ("tool", "function")
                or m.get("tool_call_id")
                for m in messages
            )

            chunks = self._build_chunks(has_tool_result=has_tool_result)
            self._send_sse(chunks)
        else:
            self.send_response(404)
            self.end_headers()

    def _build_chunks(self, has_tool_result: bool = False) -> list[str]:
        chunks: list[str] = []
        # Standard OpenAI streaming usually starts with a role delta.
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

        script = self.__class__.script

        # Split script around the first tool_call for multi-turn.
        first_tool_idx = None
        for i, action in enumerate(script):
            if action.get("type") == "tool_call":
                first_tool_idx = i
                break

        if has_tool_result and first_tool_idx is not None:
            # Turn 2: emit everything after the first tool_call.
            actions_to_emit = script[first_tool_idx + 1:]
        else:
            # Turn 1: emit everything up to and including the first tool_call.
            if first_tool_idx is not None:
                actions_to_emit = script[:first_tool_idx + 1]
            else:
                actions_to_emit = script

        for action in actions_to_emit:
            if action.get("type") == "text":
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
            elif action.get("type") == "tool_call":
                tool_id = action.get("id", "call_1")
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
                                            "index": 0,
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
            elif action.get("type") == "done":
                chunks.append(
                    json.dumps({
                        "id": "mock-chunk",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": "mockmodel",
                        "choices": [
                            {"index": 0, "delta": {}, "finish_reason": "stop"}
                        ],
                    })
                )

        return chunks


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
        MockLLMHandler.script = json.load(fh)

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
