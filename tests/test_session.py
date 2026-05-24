from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from conftest import ROOT, load_tool_module


def _load_session_module():
    return load_tool_module("codecome_session", "tools/codecome/session.py")


class TestGetHeaders:
    def test_no_auth_no_workspace(self):
        module = _load_session_module()
        headers = module._get_headers(None, None)
        assert headers == {"Content-Type": "application/json"}

    def test_with_auth_token(self):
        module = _load_session_module()
        headers = module._get_headers("secret123", None)
        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"].startswith("Basic ")
        # Decode and verify
        import base64
        decoded = base64.b64decode(headers["Authorization"].split(" ", 1)[1]).decode("utf-8")
        assert decoded == "opencode:secret123"

    def test_with_workspace_dir(self):
        module = _load_session_module()
        headers = module._get_headers(None, "/workspace")
        assert headers["x-opencode-directory"] == "/workspace"

    def test_with_both(self):
        module = _load_session_module()
        headers = module._get_headers("tok", "/ws")
        assert "Authorization" in headers
        assert headers["x-opencode-directory"] == "/ws"


class TestCreateSession:
    @patch("urllib.request.urlopen")
    def test_create_session_without_model(self, mock_urlopen):
        module = _load_session_module()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"id": "sess-abc"}).encode("utf-8")
        mock_urlopen.return_value = mock_resp

        sid = module.create_session("http://localhost:8080", "1", "recon", None, None, None)
        assert sid == "sess-abc"

        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://localhost:8080/session"
        payload = json.loads(req.data)
        assert payload["title"] == "CodeCome Phase 1"
        assert payload["agent"] == "recon"
        assert "model" not in payload

    @patch("urllib.request.urlopen")
    def test_create_session_with_provider_model(self, mock_urlopen):
        module = _load_session_module()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"id": "sess-xyz"}).encode("utf-8")
        mock_urlopen.return_value = mock_resp

        sid = module.create_session(
            "http://localhost:8080", "2", "auditor", "openai/gpt-5", None, None
        )
        assert sid == "sess-xyz"

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data)
        assert payload["model"] == {"providerID": "openai", "id": "gpt-5"}

    @patch("urllib.request.urlopen")
    def test_create_session_with_bare_model(self, mock_urlopen):
        module = _load_session_module()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"id": "sess-bare"}).encode("utf-8")
        mock_urlopen.return_value = mock_resp

        sid = module.create_session(
            "http://localhost:8080", "3", "reviewer", "gpt-5", None, None
        )
        assert sid == "sess-bare"

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data)
        assert payload["model"] == {"id": "gpt-5"}

    @patch("urllib.request.urlopen")
    def test_create_session_empty_id_raises(self, mock_urlopen):
        module = _load_session_module()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"id": ""}).encode("utf-8")
        mock_urlopen.return_value = mock_resp

        with pytest.raises(RuntimeError, match="empty session ID"):
            module.create_session("http://localhost:8080", "1", "recon", None, None, None)


class TestCreateChatSession:
    @patch("urllib.request.urlopen")
    def test_chat_session_has_permission_deny(self, mock_urlopen):
        module = _load_session_module()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"id": "chat-1"}).encode("utf-8")
        mock_urlopen.return_value = mock_resp

        sid = module.create_chat_session("http://localhost:8080", "auditor", None, None, None)
        assert sid == "chat-1"

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data)
        assert payload["title"] == "CodeCome Chat"
        assert "permission" in payload
        assert len(payload["permission"]) == 3


class TestSendPromptToSession:
    @patch("urllib.request.urlopen")
    def test_send_prompt_basic(self, mock_urlopen):
        module = _load_session_module()
        mock_urlopen.return_value = MagicMock()

        module.send_prompt_to_session(
            "http://localhost:8080", "sess-1", "hello", "recon", None, None, None, None
        )

        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://localhost:8080/session/sess-1/prompt_async"
        assert req.method == "POST"
        payload = json.loads(req.data)
        assert payload["parts"] == [{"type": "text", "text": "hello"}]
        assert payload["agent"] == "recon"

    @patch("urllib.request.urlopen")
    def test_send_prompt_with_model_and_variant(self, mock_urlopen):
        module = _load_session_module()
        mock_urlopen.return_value = MagicMock()

        module.send_prompt_to_session(
            "http://localhost:8080",
            "sess-1",
            "hello",
            "recon",
            "anthropic/claude-opus-4",
            "max",
            None,
            None,
        )

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data)
        assert payload["model"] == {"providerID": "anthropic", "modelID": "claude-opus-4"}
        assert payload["variant"] == "max"

    @patch("urllib.request.urlopen")
    def test_send_prompt_http_error_raises(self, mock_urlopen):
        module = _load_session_module()
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(
            "http://localhost:8080/session/sess-1/prompt_async",
            500,
            "Internal Server Error",
            {},
            None,
        )

        with pytest.raises(RuntimeError, match="Failed to send prompt: HTTP 500"):
            module.send_prompt_to_session(
                "http://localhost:8080", "sess-1", "hello", "recon", None, None, None, None
            )
