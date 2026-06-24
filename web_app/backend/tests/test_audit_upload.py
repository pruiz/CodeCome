import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.api import audits
from app.config import settings
from app import schemas


class FakeUploadFile:
    filename = "target.zip"

    async def read(self):
        return b"zip-bytes"


def test_upload_zip_preserves_audit_settings(monkeypatch, tmp_path):
    captured = {}
    workspace = tmp_path / "workspace"

    monkeypatch.setattr(settings, "WORKSPACES_DIR", tmp_path)
    monkeypatch.setattr(audits.workspace_manager, "create_workspace", lambda audit_id: workspace)
    monkeypatch.setattr(audits.workspace_manager, "setup_source_from_zip", lambda path, zip_path: True)
    monkeypatch.setattr(audits.workspace_manager, "write_codecome_yml", lambda path, yml: captured.setdefault("yml", yml))
    monkeypatch.setattr(audits.crud, "get_worker", lambda db, worker_id: SimpleNamespace(id=worker_id))
    monkeypatch.setattr(audits.crud, "get_user", lambda db, user_id: SimpleNamespace(id=user_id))

    def fake_create_audit(db, audit_data):
        captured["audit"] = audit_data
        return SimpleNamespace(id="audit-1")

    monkeypatch.setattr(audits.crud, "create_audit", fake_create_audit)
    monkeypatch.setattr(audits, "start_created_audit_if_requested", lambda db, audit: None)

    result = asyncio.run(audits.upload_zip(
        name="Zip Audit",
        file=FakeUploadFile(),
        codecome_yml="project: demo",
        worker_id=2,
        question_owner_user_id=7,
        ai_review_enabled=True,
        auto_continue=True,
        db=object(),
    ))

    assert result.id == "audit-1"
    assert captured["yml"] == "project: demo"
    assert captured["audit"].name == "Zip Audit"
    assert captured["audit"].worker_id == 2
    assert captured["audit"].question_owner_user_id == 7
    assert captured["audit"].ai_review_enabled is True
    assert captured["audit"].auto_continue is True
    assert not any(Path(tmp_path / "uploads").glob("*target.zip"))


def test_upload_zip_uses_default_question_owner(monkeypatch, tmp_path):
    captured = {}
    workspace = tmp_path / "workspace"
    owner = SimpleNamespace(id=9)

    monkeypatch.setattr(settings, "WORKSPACES_DIR", tmp_path)
    monkeypatch.setattr(audits.workspace_manager, "create_workspace", lambda audit_id: workspace)
    monkeypatch.setattr(audits.workspace_manager, "setup_source_from_zip", lambda path, zip_path: True)
    monkeypatch.setattr(audits.workspace_manager, "write_codecome_yml", lambda path, yml: None)
    monkeypatch.setattr(audits.crud, "default_question_owner", lambda db: owner)
    monkeypatch.setattr(audits.crud, "create_audit", lambda db, audit_data: captured.setdefault("audit", audit_data) or SimpleNamespace(id="audit-1"))

    asyncio.run(audits.upload_zip(
        name="Zip Audit",
        file=FakeUploadFile(),
        codecome_yml="project: demo",
        worker_id=None,
        question_owner_user_id=None,
        ai_review_enabled=False,
        auto_continue=False,
        db=object(),
    ))

    assert captured["audit"].question_owner_user_id == 9


def test_create_audit_auto_continue_queues_first_phase(monkeypatch, tmp_path):
    captured = {}
    workspace = tmp_path / "workspace"

    monkeypatch.setattr(audits.workspace_manager, "create_workspace", lambda audit_id: workspace)
    monkeypatch.setattr(audits.workspace_manager, "setup_source_from_local", lambda path, source: True)
    monkeypatch.setattr(audits.workspace_manager, "write_codecome_yml", lambda path, yml: None)
    monkeypatch.setattr(audits.crud, "get_worker", lambda db, worker_id: SimpleNamespace(id=worker_id))
    monkeypatch.setattr(audits.crud, "default_question_owner", lambda db: None)
    monkeypatch.setattr(audits.crud, "select_available_worker", lambda db, worker_id: SimpleNamespace(id=worker_id or 4, name="local"))
    monkeypatch.setattr(audits.run_phase_task, "delay", lambda *args: captured.setdefault("delay", args))

    def fake_create_audit(db, audit_data):
        return SimpleNamespace(
            id="audit-1",
            auto_continue=audit_data.auto_continue,
            model_settings=audit_data.model_settings,
            workspace_path=str(workspace),
            assigned_worker_id=audit_data.worker_id,
            current_phase=None,
            status="initializing",
        )

    monkeypatch.setattr(audits.crud, "create_audit", fake_create_audit)
    db = SimpleNamespace(commits=0, commit=lambda: setattr(db, "commits", db.commits + 1))

    result = audits.create_audit(schemas.AuditCreate(
        name="Auto Audit",
        source_type="local",
        source_location=str(tmp_path / "src"),
        codecome_yml="project: demo",
        worker_id=4,
        auto_continue=True,
    ), db=db)

    assert result.current_phase == "make init"
    assert result.status == "initializing"
    assert captured["delay"][:3] == ("audit-1", "make init", None)
    assert captured["delay"][6] == 4


def test_upload_zip_auto_continue_queues_first_phase(monkeypatch, tmp_path):
    captured = {}
    workspace = tmp_path / "workspace"

    monkeypatch.setattr(settings, "WORKSPACES_DIR", tmp_path)
    monkeypatch.setattr(audits.workspace_manager, "create_workspace", lambda audit_id: workspace)
    monkeypatch.setattr(audits.workspace_manager, "setup_source_from_zip", lambda path, zip_path: True)
    monkeypatch.setattr(audits.workspace_manager, "write_codecome_yml", lambda path, yml: None)
    monkeypatch.setattr(audits.crud, "default_question_owner", lambda db: None)
    monkeypatch.setattr(audits.crud, "select_available_worker", lambda db, worker_id: SimpleNamespace(id=worker_id or 5, name="local"))
    monkeypatch.setattr(audits.run_phase_task, "delay", lambda *args: captured.setdefault("delay", args))

    def fake_create_audit(db, audit_data):
        return SimpleNamespace(
            id="audit-zip",
            auto_continue=audit_data.auto_continue,
            model_settings=audit_data.model_settings,
            workspace_path=str(workspace),
            assigned_worker_id=audit_data.worker_id,
            current_phase=None,
            status="initializing",
        )

    monkeypatch.setattr(audits.crud, "create_audit", fake_create_audit)
    db = SimpleNamespace(commits=0, commit=lambda: setattr(db, "commits", db.commits + 1))

    result = asyncio.run(audits.upload_zip(
        name="Zip Audit",
        file=FakeUploadFile(),
        codecome_yml="project: demo",
        worker_id=None,
        question_owner_user_id=None,
        ai_review_enabled=False,
        auto_continue=True,
        db=db,
    ))

    assert result.current_phase == "make init"
    assert result.status == "initializing"
    assert captured["delay"][:3] == ("audit-zip", "make init", None)
    assert captured["delay"][6] == 5
