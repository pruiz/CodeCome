from __future__ import annotations

import json
from io import BytesIO
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
    def test_send_prompt_http_error_raises(self, mock_urlopen, monkeypatch):
        module = _load_session_module()
        monkeypatch.setenv("CODECOME_PROMPT_MAX_RETRIES", "1")
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(
            "http://localhost:8080/session/sess-1/prompt_async",
            500,
            "Internal Server Error",
            {},
            BytesIO(b"server says no"),
        )

        with pytest.raises(RuntimeError, match="Failed to send prompt: HTTP 500: server says no"):
            module.send_prompt_to_session(
                "http://localhost:8080", "sess-1", "hello", "recon", None, None, None, None
            )

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_send_prompt_retries_on_timeout(self, mock_urlopen, mock_sleep):
        module = _load_session_module()

        # First two calls timeout, third succeeds.
        mock_urlopen.side_effect = [
            TimeoutError("timed out"),
            TimeoutError("timed out"),
            MagicMock(),
        ]

        module.send_prompt_to_session(
            "http://localhost:8080", "sess-1", "hello", "recon", None, None, None, None
        )

        assert mock_urlopen.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_send_prompt_retries_exhausted_raises(self, mock_urlopen, mock_sleep):
        module = _load_session_module()

        mock_urlopen.side_effect = TimeoutError("timed out")

        with pytest.raises(RuntimeError, match="timed out"):
            module.send_prompt_to_session(
                "http://localhost:8080", "sess-1", "hello", "recon", None, None, None, None
            )

        assert mock_urlopen.call_count == 3  # default max retries

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_send_prompt_no_retry_on_4xx(self, mock_urlopen, mock_sleep):
        module = _load_session_module()
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(
            "http://localhost:8080/session/sess-1/prompt_async",
            400,
            "Bad Request",
            {},
            BytesIO(b"bad"),
        )

        with pytest.raises(RuntimeError, match="HTTP 400"):
            module.send_prompt_to_session(
                "http://localhost:8080", "sess-1", "hello", "recon", None, None, None, None
            )

        assert mock_urlopen.call_count == 1
        assert mock_sleep.call_count == 0

    @patch("urllib.request.urlopen")
    def test_get_session_status_busy_from_status_map(self, mock_urlopen):
        module = _load_session_module()
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps({"sess-1": {"type": "busy"}}).encode("utf-8")
        mock_urlopen.return_value = mock_resp

        status = module.get_session_status("http://localhost:8080", "sess-1", None, None)

        assert status == "busy"
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://localhost:8080/session/status"

    @patch("urllib.request.urlopen")
    def test_get_session_status_retry_from_status_map(self, mock_urlopen):
        module = _load_session_module()
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps({"sess-1": {"type": "retry", "attempt": 1}}).encode("utf-8")
        mock_urlopen.return_value = mock_resp

        status = module.get_session_status("http://localhost:8080", "sess-1", None, None)

        assert status == "retry"

    @patch("urllib.request.urlopen")
    def test_get_session_status_missing_entry_is_idle(self, mock_urlopen):
        module = _load_session_module()
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps({}).encode("utf-8")
        mock_urlopen.return_value = mock_resp

        status = module.get_session_status("http://localhost:8080", "sess-1", None, None)

        assert status == "idle"

    @patch("urllib.request.urlopen")
    def test_get_session_status_request_failure_is_unknown(self, mock_urlopen):
        module = _load_session_module()
        mock_urlopen.side_effect = OSError("server unavailable")

        status = module.get_session_status("http://localhost:8080", "sess-1", None, None)

        assert status is None
