import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.api import audits
from app.config import settings
from app import schemas
from app.services.workspace import WorkspaceManager


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


def test_local_folder_audit_copies_source_into_workspace(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text("print('local source')\n")
    (source / "nested").mkdir()
    (source / "nested" / "config.yml").write_text("name: demo\n")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manager = WorkspaceManager()

    assert manager.setup_source_from_local(workspace, str(source)) is True

    assert (workspace / "src" / "app.py").read_text() == "print('local source')\n"
    assert (workspace / "src" / "nested" / "config.yml").read_text() == "name: demo\n"


def test_latest_report_path_prefers_newest_markdown(tmp_path):
    reports = tmp_path / "itemdb" / "reports"
    reports.mkdir(parents=True)
    older = reports / "old.txt"
    newer = reports / "report.md"
    older.write_text("old")
    newer.write_text("new")

    assert audits.latest_report_path(tmp_path) == newer


def test_download_latest_report_fetches_remote_reports_when_missing(monkeypatch, tmp_path):
    audit = SimpleNamespace(
        id="audit-remote",
        workspace_path=str(tmp_path),
        assigned_worker_id=3,
    )
    worker = SimpleNamespace(type="ssh")

    class FakeExecutor:
        def __init__(self, worker_arg):
            assert worker_arg is worker

        def download_reports(self, audit_id, local_workspace_path):
            assert audit_id == "audit-remote"
            report_dir = local_workspace_path / "itemdb" / "reports"
            report_dir.mkdir(parents=True)
            (report_dir / "remote-report.md").write_text("# Report\n")

    monkeypatch.setattr(audits.crud, "get_audit", lambda db, audit_id: audit)
    monkeypatch.setattr(audits.crud, "get_worker", lambda db, worker_id: worker)
    monkeypatch.setattr(audits, "SSHCodeComeExecutor", FakeExecutor)

    response = audits.download_latest_report("audit-remote", db=object())

    assert response.path.endswith("remote-report.md")


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
