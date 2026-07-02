import asyncio
import subprocess
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


def test_github_tree_url_clones_repo_and_checks_out_ref(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manager = WorkspaceManager()

    ok = manager.setup_source_from_git(
        workspace,
        "https://github.com/phpipam/phpipam/tree/137141d89a44e9979eb0df52427ec0e676077f03",
    )

    assert ok is True
    assert calls[0][0] == ["git", "clone", "https://github.com/phpipam/phpipam.git", "."]
    assert calls[1][0] == ["git", "checkout", "137141d89a44e9979eb0df52427ec0e676077f03"]
    assert calls[0][1]["cwd"] == workspace / "src"


def test_plain_git_url_clones_without_checkout(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manager = WorkspaceManager()

    ok = manager.setup_source_from_git(workspace, "https://github.com/phpipam/phpipam.git")

    assert ok is True
    assert calls == [["git", "clone", "https://github.com/phpipam/phpipam.git", "."]]


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


def test_run_gap_scan_queues_manual_gap_phase(monkeypatch, tmp_path):
    captured = {}
    audit_id = "11111111-2222-3333-4444-555555555555"
    audit = SimpleNamespace(
        id=audit_id,
        status="completed",
        assigned_worker_id=4,
        model_settings={},
        workspace_path=str(tmp_path),
        current_phase=None,
    )
    worker = SimpleNamespace(id=4, name="local")
    db = SimpleNamespace(commits=0, commit=lambda: setattr(db, "commits", db.commits + 1))

    monkeypatch.setattr(audits.crud, "get_audit", lambda db_arg, candidate_id: audit)
    monkeypatch.setattr(audits.crud, "audit_has_open_blocking_questions", lambda db_arg, candidate_id: False)
    monkeypatch.setattr(audits.crud, "select_available_worker", lambda db_arg, worker_id: worker)
    monkeypatch.setattr(audits.run_phase_task, "delay", lambda *args: captured.setdefault("delay", args))

    response = audits.run_gap_scan(audit_id, db=db)

    assert response["phase"] == "gap-scan"
    assert response["message"] == "Gap scan queued"
    assert audit.current_phase == "gap-scan"
    assert captured["delay"][:3] == (audit_id, "gap-scan", None)
    assert captured["delay"][6] == 4


def test_gap_prompt_returns_custom_audit_prompt(monkeypatch, tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "phase-2-gap-sast.md").write_text("Default prompt", encoding="utf-8")
    audit = SimpleNamespace(id="audit-1", model_settings={"__audit_options": {"gap_scan_prompt": "Custom app context"}})

    monkeypatch.setattr(settings, "CODECOME_ROOT", tmp_path)
    monkeypatch.setattr(audits.crud, "get_audit", lambda db_arg, audit_id: audit)

    response = audits.get_gap_prompt("11111111-2222-3333-4444-555555555555", db=object())

    assert response["path"] == "prompts/phase-2-gap-sast.md"
    assert response["default_prompt"] == "Default prompt"
    assert response["prompt"] == "Custom app context"
    assert response["custom"] is True


def test_gap_prompt_prefers_audit_workspace_prompt(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "prompts").mkdir(parents=True)
    (workspace / "prompts" / "phase-2-gap-sast.md").write_text("Workspace prompt", encoding="utf-8")
    audit = SimpleNamespace(id="audit-1", assigned_worker_id=None, workspace_path=str(workspace), model_settings={})

    monkeypatch.setattr(audits.crud, "get_audit", lambda db_arg, audit_id: audit)

    response = audits.get_gap_prompt("11111111-2222-3333-4444-555555555555", db=object())

    assert response["path"] == str(workspace / "prompts" / "phase-2-gap-sast.md")
    assert response["prompt"] == "Workspace prompt"
    assert response["custom"] is False


def test_gap_prompt_prefers_remote_worker_prompt(monkeypatch, tmp_path):
    worker = SimpleNamespace(id=4, type="ssh")
    audit = SimpleNamespace(id="audit-1", assigned_worker_id=4, workspace_path=str(tmp_path), model_settings={})

    class FakeExecutor:
        def __init__(self, worker_arg):
            self.worker = worker_arg

        def _connect(self):
            return SimpleNamespace(close=lambda: None, open_sftp=lambda: object())

        def remote_workspace_path(self, audit_id):
            return f"/srv/workspaces/audit-{audit_id}"

        def _remote_exists(self, sftp, remote_path):
            return remote_path == "/srv/workspaces/audit-audit-1/prompts/phase-2-gap-sast.md"

        def _read_remote_file(self, sftp, remote_path):
            return "Remote worker prompt"

    monkeypatch.setattr(audits, "SSHCodeComeExecutor", FakeExecutor)
    monkeypatch.setattr(audits.crud, "get_audit", lambda db_arg, audit_id: audit)
    monkeypatch.setattr(audits.crud, "get_worker", lambda db_arg, worker_id: worker)

    response = audits.get_gap_prompt("11111111-2222-3333-4444-555555555555", db=object())

    assert response["path"] == "/srv/workspaces/audit-audit-1/prompts/phase-2-gap-sast.md"
    assert response["prompt"] == "Remote worker prompt"
    assert response["custom"] is False


def test_update_gap_prompt_saves_model_settings_and_workspace_file(monkeypatch, tmp_path):
    audit_id = "11111111-2222-3333-4444-555555555555"
    workspace = tmp_path / "workspace"
    (workspace / "prompts").mkdir(parents=True)
    (workspace / "prompts" / "phase-2-gap-sast.md").write_text("Workspace prompt", encoding="utf-8")
    audit = SimpleNamespace(id=audit_id, assigned_worker_id=None, workspace_path=str(workspace), model_settings={})
    db = SimpleNamespace(commits=0, refreshed=[], commit=lambda: setattr(db, "commits", db.commits + 1), refresh=lambda obj: db.refreshed.append(obj))

    monkeypatch.setattr(audits.crud, "get_audit", lambda db_arg, candidate_id: audit)

    response = audits.update_gap_prompt(audit_id, schemas.GapPromptUpdate(prompt="Custom audit focus"), db=db)

    assert audit.model_settings["__audit_options"]["gap_scan_prompt"] == "Custom audit focus"
    assert (workspace / "runs" / "gap-scan-prompt.md").read_text() == "Custom audit focus"
    assert response["prompt"] == "Custom audit focus"
    assert response["local_sync"].endswith("runs/gap-scan-prompt.md")


def test_run_gap_compare_queues_manual_gap_phase(monkeypatch, tmp_path):
    captured = {}
    audit_id = "11111111-2222-3333-4444-555555555555"
    audit = SimpleNamespace(
        id=audit_id,
        status="completed",
        assigned_worker_id=4,
        model_settings={},
        workspace_path=str(tmp_path),
        current_phase=None,
    )
    worker = SimpleNamespace(id=4, name="local")
    db = SimpleNamespace(commits=0, commit=lambda: setattr(db, "commits", db.commits + 1))

    monkeypatch.setattr(audits.crud, "get_audit", lambda db_arg, candidate_id: audit)
    monkeypatch.setattr(audits.crud, "audit_has_open_blocking_questions", lambda db_arg, candidate_id: False)
    monkeypatch.setattr(audits.crud, "select_available_worker", lambda db_arg, worker_id: worker)
    monkeypatch.setattr(audits.run_phase_task, "delay", lambda *args: captured.setdefault("delay", args))

    response = audits.run_gap_compare(audit_id, db=db)

    assert response["phase"] == "gap-compare"
    assert response["message"] == "Gap compare queued"
    assert audit.current_phase == "gap-compare"
    assert captured["delay"][:3] == (audit_id, "gap-compare", None)
    assert captured["delay"][6] == 4


def test_run_gap_sweep_queues_all_missing_candidates(monkeypatch, tmp_path):
    captured = {}
    audit_id = "11111111-2222-3333-4444-555555555555"
    audit = SimpleNamespace(
        id=audit_id,
        status="completed",
        assigned_worker_id=4,
        model_settings={},
        workspace_path=str(tmp_path),
        current_phase=None,
    )
    worker = SimpleNamespace(id=4, name="local")
    db = SimpleNamespace(commits=0, commit=lambda: setattr(db, "commits", db.commits + 1))

    monkeypatch.setattr(audits.crud, "get_audit", lambda db_arg, candidate_id: audit)
    monkeypatch.setattr(audits.crud, "audit_has_open_blocking_questions", lambda db_arg, candidate_id: False)
    monkeypatch.setattr(audits.crud, "select_available_worker", lambda db_arg, worker_id: worker)
    monkeypatch.setattr(audits.run_phase_task, "delay", lambda *args: captured.setdefault("delay", args))

    response = audits.run_gap_sweep(audit_id, db=db)

    assert response["phase"] == "gap-sweep"
    assert response["message"] == "Gap sweep queued"
    assert audit.current_phase == "gap-sweep"
    assert captured["delay"][:3] == (audit_id, "gap-sweep", None)
    assert captured["delay"][7] == {}


def test_run_gap_sweep_queues_selected_candidate(monkeypatch, tmp_path):
    captured = {}
    audit_id = "11111111-2222-3333-4444-555555555555"
    audit = SimpleNamespace(
        id=audit_id,
        status="completed",
        assigned_worker_id=4,
        model_settings={},
        workspace_path=str(tmp_path),
        current_phase=None,
    )
    worker = SimpleNamespace(id=4, name="local")
    db = SimpleNamespace(commits=0, commit=lambda: setattr(db, "commits", db.commits + 1))

    monkeypatch.setattr(audits.crud, "get_audit", lambda db_arg, candidate_id: audit)
    monkeypatch.setattr(audits.crud, "audit_has_open_blocking_questions", lambda db_arg, candidate_id: False)
    monkeypatch.setattr(audits.crud, "select_available_worker", lambda db_arg, worker_id: worker)
    monkeypatch.setattr(audits.run_phase_task, "delay", lambda *args: captured.setdefault("delay", args))

    response = audits.run_gap_sweep(audit_id, candidate="GAP-0007", db=db)

    assert response["phase"] == "gap-sweep"
    assert captured["delay"][:3] == (audit_id, "gap-sweep", None)
    assert captured["delay"][7] == {"ARGS": "--candidate GAP-0007"}


def test_run_gap_sweep_rejects_bad_candidate(tmp_path):
    try:
        audits.run_gap_sweep("11111111-2222-3333-4444-555555555555", candidate="bad", db=object())
    except Exception as exc:
        assert getattr(exc, "status_code") == 400
        assert "GAP-0001" in exc.detail
    else:
        raise AssertionError("Expected HTTPException")


def test_list_gap_candidates_returns_comparison_decisions(monkeypatch, tmp_path):
    audit_id = "11111111-2222-3333-4444-555555555555"
    audit = SimpleNamespace(id=audit_id, workspace_path=str(tmp_path))
    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (notes / "sast-gap-candidates.yml").write_text("""
candidates:
  - id: GAP-0001
    title: Stack trace disclosure
    category: Information Disclosure
    files: [src/EmployeeController.java]
    matched_notes: [itemdb/notes/attack-surface.md:66]
    sweep_files: [src/EmployeeController.java]
    safety: {source_backed: true}
""", encoding="utf-8")

    monkeypatch.setattr(audits.crud, "get_audit", lambda db_arg, candidate_id: audit)

    response = audits.list_gap_candidates(audit_id, db=object())

    assert response["total"] == 1
    candidate = response["candidates"][0]
    assert candidate["id"] == "GAP-0001"
    assert candidate["decision"] == "missing_sweep"
    assert candidate["action"] == "sweep"
    assert candidate["matched_notes"] == ["itemdb/notes/attack-surface.md:66"]


def test_list_gap_candidates_returns_empty_when_file_missing(monkeypatch, tmp_path):
    audit_id = "11111111-2222-3333-4444-555555555555"
    audit = SimpleNamespace(id=audit_id, workspace_path=str(tmp_path))
    monkeypatch.setattr(audits.crud, "get_audit", lambda db_arg, candidate_id: audit)

    response = audits.list_gap_candidates(audit_id, db=object())

    assert response == {"audit_id": audit_id, "total": 0, "candidates": []}


def test_mark_gap_candidate_persists_manual_decision(monkeypatch, tmp_path):
    audit_id = "11111111-2222-3333-4444-555555555555"
    audit = SimpleNamespace(id=audit_id, workspace_path=str(tmp_path))
    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (notes / "sast-gap-candidates.yml").write_text("""
candidates:
  - id: GAP-0001
    title: Stack trace disclosure
    category: Information Disclosure
    files: [src/EmployeeController.java]
    matched_notes: [itemdb/notes/attack-surface.md:66]
    sweep_files: [src/EmployeeController.java]
    safety: {source_backed: true}
""", encoding="utf-8")

    monkeypatch.setattr(audits.crud, "get_audit", lambda db_arg, candidate_id: audit)

    response = audits.mark_gap_candidate_decision(
        audit_id,
        "GAP-0001",
        schemas.GapCandidateMarkRequest(decision="ignored", note="Accepted risk."),
        db=object(),
    )

    assert response["message"] == "Gap candidate marked as ignored"
    listed = audits.list_gap_candidates(audit_id, db=object())
    candidate = listed["candidates"][0]
    assert candidate["manual_decision"]["decision"] == "ignored"
    assert candidate["decision"] == "defer_low_signal"
    assert candidate["action"] == "ignore"
    assert candidate["comparison_rationale"] == "Accepted risk."


def test_mark_gap_candidate_rejects_bad_candidate_id(tmp_path):
    try:
        audits.mark_gap_candidate(tmp_path, "bad", schemas.GapCandidateMarkRequest(decision="ignored"))
    except Exception as exc:
        assert getattr(exc, "status_code") == 400
    else:
        raise AssertionError("Expected HTTPException")
