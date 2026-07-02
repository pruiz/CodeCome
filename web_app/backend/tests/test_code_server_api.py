from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import audits


class FakeProcess:
    pid = 1234

    def __init__(self):
        self.terminated = False

    def poll(self):
        return None if not self.terminated else 0

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.terminated = True


def test_code_server_start_status_and_stop(monkeypatch, tmp_path):
    audit = SimpleNamespace(id="audit-1", workspace_path=str(tmp_path))
    process = FakeProcess()
    monkeypatch.setattr(audits.crud, "get_audit", lambda db, audit_id: audit)
    monkeypatch.setattr(audits.shutil, "which", lambda cmd: "/usr/bin/code-server" if cmd == "code-server" else None)
    monkeypatch.setattr(audits, "free_local_port", lambda: 32123)
    monkeypatch.setattr(audits.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(audits.settings, "CODE_SERVER_BIND_ADDR", "127.0.0.1")
    monkeypatch.setattr(audits.settings, "CODE_SERVER_PUBLIC_BASE_URL", "")
    audits.CODE_SERVER_SESSIONS.clear()

    started = audits.start_code_server("audit-1", db=object())
    assert started["running"] is True
    assert started["url"] == "http://localhost:32123"
    assert started["bind_addr"] == "127.0.0.1"
    assert started["password"]
    assert started["workspace_path"] == str(tmp_path)

    status = audits.code_server_status("audit-1", db=object())
    assert status["running"] is True

    stopped = audits.stop_code_server("audit-1", db=object())
    assert stopped == {"audit_id": "audit-1", "running": False}
    assert process.terminated is True


def test_code_server_uses_public_base_url_for_lan_mode(monkeypatch, tmp_path):
    audit = SimpleNamespace(id="audit-1", workspace_path=str(tmp_path))
    process = FakeProcess()
    captured = {}
    monkeypatch.setattr(audits.crud, "get_audit", lambda db, audit_id: audit)
    monkeypatch.setattr(audits.shutil, "which", lambda cmd: "/usr/bin/code-server" if cmd == "code-server" else None)
    monkeypatch.setattr(audits, "free_local_port", lambda: 32123)
    monkeypatch.setattr(audits.settings, "CODE_SERVER_BIND_ADDR", "0.0.0.0")
    monkeypatch.setattr(audits.settings, "CODE_SERVER_PUBLIC_BASE_URL", "http://server.local")

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return process

    monkeypatch.setattr(audits.subprocess, "Popen", fake_popen)
    audits.CODE_SERVER_SESSIONS.clear()

    started = audits.start_code_server("audit-1", db=object())

    assert started["url"] == "http://server.local:32123"
    assert started["bind_addr"] == "0.0.0.0"
    assert "0.0.0.0:32123" in captured["cmd"]


def test_code_server_start_requires_binary(monkeypatch, tmp_path):
    audit = SimpleNamespace(id="audit-1", workspace_path=str(tmp_path))
    monkeypatch.setattr(audits.crud, "get_audit", lambda db, audit_id: audit)
    monkeypatch.setattr(audits.shutil, "which", lambda cmd: None)
    audits.CODE_SERVER_SESSIONS.clear()

    with pytest.raises(HTTPException) as exc:
        audits.start_code_server("audit-1", db=object())

    assert exc.value.status_code == 503
