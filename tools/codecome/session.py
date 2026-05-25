# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
OpenCode HTTP API helpers: auth headers, create session, create chat session,
send prompt.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def _get_headers(auth_token: str | None, workspace_dir: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if auth_token:
        import base64
        encoded = base64.b64encode(f"opencode:{auth_token}".encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {encoded}"
    if workspace_dir:
        headers["x-opencode-directory"] = workspace_dir
    return headers


def send_prompt_to_session(
    base_url: str,
    session_id: str,
    prompt: str,
    agent: str,
    model: str | None,
    variant: str | None,
    auth_token: str | None,
    workspace_dir: str | None,
) -> None:
    url = f"{base_url}/session/{session_id}/prompt_async"
    payload: dict[str, Any] = {
        "parts": [{"type": "text", "text": prompt}],
        "agent": agent,
    }
    if model:
        parts = model.split("/", 1)
        if len(parts) == 2:
            # NOTE: prompt_async expects "modelID", not "id".
            # Session creation (POST /session) uses "id" instead.
            # See _create_model_payload() in mock-llm-parity.py for the
            # authoritative reference.
            payload["model"] = {"providerID": parts[0], "modelID": parts[1]}
        else:
            payload["model"] = {"modelID": model}
    if variant:
        payload["variant"] = variant
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers=_get_headers(auth_token, workspace_dir),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            pass  # 204 expected
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Failed to send prompt: HTTP {exc.code}") from exc


def create_session(
    base_url: str,
    phase: str,
    agent: str,
    model: str | None,
    auth_token: str | None,
    workspace_dir: str | None,
) -> str:
    payload: dict[str, Any] = {"title": f"CodeCome Phase {phase}", "agent": agent}
    if model:
        parts = model.split("/", 1)
        if len(parts) == 2:
            # NOTE: session creation (POST /session) expects "id", not "modelID".
            # Prompt submission (prompt_async) uses "modelID" instead.
            # See _create_model_payload() in mock-llm-parity.py for the
            # authoritative reference.
            payload["model"] = {"providerID": parts[0], "id": parts[1]}
        else:
            payload["model"] = {"id": model}
    req = urllib.request.Request(
        f"{base_url}/session",
        data=json.dumps(payload).encode("utf-8"),
        headers=_get_headers(auth_token, workspace_dir),
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=10.0)
    data = json.loads(resp.read().decode("utf-8"))
    sid = str(data.get("id", ""))
    if not sid:
        raise RuntimeError("Server returned empty session ID")
    return sid


def create_chat_session(
    base_url: str,
    agent: str,
    model: str | None,
    auth_token: str | None,
    workspace_dir: str | None,
) -> str:
    payload: dict[str, Any] = {
        "title": "CodeCome Chat",
        "agent": agent,
        "permission": [
            {"permission": "question", "action": "deny", "pattern": "*"},
            {"permission": "plan_enter", "action": "deny", "pattern": "*"},
            {"permission": "plan_exit", "action": "deny", "pattern": "*"},
        ],
    }
    if model:
        parts = model.split("/", 1)
        if len(parts) == 2:
            # Session creation uses "id" (see create_session above).
            payload["model"] = {"providerID": parts[0], "id": parts[1]}
        else:
            payload["model"] = {"id": model}
    req = urllib.request.Request(
        f"{base_url}/session",
        data=json.dumps(payload).encode("utf-8"),
        headers=_get_headers(auth_token, workspace_dir),
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=10.0)
    data = json.loads(resp.read().decode("utf-8"))
    sid = str(data.get("id", ""))
    if not sid:
        raise RuntimeError("Server returned empty session ID")
    return sid
