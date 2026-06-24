from types import SimpleNamespace

from app import crud, schemas
from app.api.audits import next_audit_step
from app.utils.codecome_wrapper import CodeComeExecutor
from app.api import logs, workers
from app.workers.phase_tasks import build_command_line, status_phase
from app.workers.phase_tasks import merged_phase_env


class FakeScalarQuery:
    def __init__(self, value=0):
        self.value = value
        self.filters = []

    def filter(self, *args):
        self.filters.extend(args)
        return self

    def scalar(self):
        return self.value


class FakeListQuery:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.filters = []
        self.offset_value = None
        self.limit_value = None

    def filter(self, *args):
        self.filters.extend(args)
        return self

    def order_by(self, *args):
        return self

    def offset(self, value):
        self.offset_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class FakeDb:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.refreshed = []

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = "demo"
        self.refreshed.append(obj)


def test_create_audit_sets_worker_and_workspace():
    db = FakeDb()
    data = schemas.AuditCreate(
        name="demo",
        source_type="local",
        source_location="/src.zip",
        workspace_path="/workspaces/audit-demo",
        worker_id=7,
        question_owner_user_id=3,
        auto_continue=False,
    )

    audit = crud.create_audit(db, data)

    assert audit.name == "demo"
    assert audit.workspace_path.endswith("/audit-demo")
    assert audit.assigned_worker_id == 7
    assert audit.question_owner_user_id == 3
    assert audit.auto_continue is False
    assert audit.status == "initializing"
    assert db.added == [audit]
    assert db.commits >= 1


def test_worker_response_redacts_ssh_secrets():
    worker = SimpleNamespace(
        id=1,
        name="runner",
        type="ssh",
        status="idle",
        host="10.0.0.1",
        port=22,
        username="codecome",
        workspace_base_path="/srv/workspaces",
        max_concurrent_jobs=1,
        current_jobs=0,
        capabilities={},
        config={"ssh_auth": {"method": "password", "password": "secret", "private_key": "key", "passphrase": "phrase"}},
        last_seen=None,
        created_at=None,
        updated_at=None,
    )

    response = workers.worker_response(worker)

    assert response["config"]["ssh_auth"] == {
        "method": "password",
        "has_password": True,
        "has_private_key": True,
        "has_passphrase": True,
    }
    assert "secret" not in str(response)
    assert "private_key" not in response["config"]["ssh_auth"]


def test_local_worker_capacity_is_forced_to_one_job():
    worker = SimpleNamespace(type="local", status="running", current_jobs=1, max_concurrent_jobs=8)

    assert crud.worker_capacity_available(worker) is False


def test_remote_worker_respects_configured_capacity():
    worker = SimpleNamespace(type="ssh", status="running", current_jobs=1, max_concurrent_jobs=2)

    assert crud.worker_capacity_available(worker) is True


def test_phase_command_line_includes_env_and_target():
    command = build_command_line(
        "phase-1",
        model="test/model",
        variant="high",
        worker_type="local",
        env_overrides={"PROMPT_EXTRA": "focus auth", "CODECOME_THINKING": "1"},
    )

    assert "PROMPT_EXTRA='focus auth'" in command
    assert "CODECOME_THINKING=1" in command
    assert "CODECOME_MODEL=test/model" in command
    assert "CODECOME_MODEL_VARIANT=high" in command
    assert command.endswith("make phase-1")


def test_merged_phase_env_phase_overrides_audit_defaults():
    settings = {
        "__audit_env": {"env": {"PROMPT_EXTRA": "audit prompt", "CODECOME_THINKING": "0"}},
        "phase-1": {"env": {"PROMPT_EXTRA": "phase prompt"}},
    }

    assert merged_phase_env(settings, "phase-1") == {
        "PROMPT_EXTRA": "phase prompt",
        "CODECOME_THINKING": "0",
    }


def test_status_phase_normalizes_make_and_phase_names():
    assert status_phase("make init") == "make_init"
    assert status_phase("phase-1") == "phase_1"


def test_next_audit_step_skips_optional_sweep():
    executions = [
        SimpleNamespace(phase="make init", status="success"),
        SimpleNamespace(phase="make check", status="success"),
        SimpleNamespace(phase="phase-1", status="success"),
        SimpleNamespace(phase="phase-2", status="success"),
    ]

    assert next_audit_step(executions) == "phase-3"


def test_next_audit_step_includes_optional_sweep_when_enabled():
    executions = [
        SimpleNamespace(phase="make init", status="success"),
        SimpleNamespace(phase="make check", status="success"),
        SimpleNamespace(phase="phase-1", status="success"),
        SimpleNamespace(phase="phase-2", status="success"),
    ]

    assert next_audit_step(executions, {"__audit_options": {"run_sweep_auto": True}}) == "make sweep"

    executions.append(SimpleNamespace(phase="make sweep", status="success"))
    assert next_audit_step(executions, {"__audit_options": {"run_sweep_auto": True}}) == "phase-3"


def test_next_audit_step_uses_batch_validation_and_exploitation():
    executions = [
        SimpleNamespace(phase="make init", status="success"),
        SimpleNamespace(phase="make check", status="success"),
        SimpleNamespace(phase="phase-1", status="success"),
        SimpleNamespace(phase="phase-2", status="success"),
        SimpleNamespace(phase="phase-3", status="success"),
    ]

    assert next_audit_step(executions) == "make validate-all"

    executions.append(SimpleNamespace(phase="make validate-all", status="success"))
    assert next_audit_step(executions) == "make exploit-all"


def test_next_audit_step_maps_legacy_phase_4_to_validate_all():
    executions = [
        SimpleNamespace(phase="make init", status="success"),
        SimpleNamespace(phase="make check", status="success"),
        SimpleNamespace(phase="phase-1", status="success"),
        SimpleNamespace(phase="phase-2", status="success"),
        SimpleNamespace(phase="phase-3", status="success"),
        SimpleNamespace(phase="phase-4", status="failed"),
    ]

    assert next_audit_step(executions) == "make validate-all"


def test_log_cleaning_removes_ansi_sequences():
    assert logs.clean_terminal_text("\x1b[1m\x1b[32mSetup complete.\x1b[0m") == "Setup complete."


def test_token_summary_parses_per_turn_usage():
    rows = [
        SimpleNamespace(message="> Assistant · local/qwen3.6-27b (↑100 ↓20)"),
        SimpleNamespace(message="step finished: tool-calls (input=100, output=20, reasoning=5, total=125)"),
        SimpleNamespace(message="step finished: message (input=200, output=30, reasoning=0, total=230)"),
    ]

    summary = logs.summarize_token_logs(rows)

    assert summary["turns"] == 2
    assert summary["input_tokens"] == 300
    assert summary["output_tokens"] == 50
    assert summary["reasoning_tokens"] == 5
    assert summary["total_tokens"] == 355
    assert summary["models"]["local/qwen3.6-27b"]["turns"] == 1
    assert summary["steps"]["tool-calls"]["total_tokens"] == 125


def test_terminate_process_group_sends_sigterm(monkeypatch):
    calls = []
    monkeypatch.setattr("os.getpgid", lambda pid: 999)
    monkeypatch.setattr("os.killpg", lambda pgid, sig: calls.append((pgid, sig)))

    CodeComeExecutor.terminate_process_group(123)

    assert calls
    assert calls[0][0] == 999


def test_apply_finding_update_appends_review_history():
    finding = SimpleNamespace(
        status="PENDING",
        severity="LOW",
        confidence="LOW",
        category="Info",
        frontmatter={"review_history": [{"note": "old"}]},
    )

    crud.apply_finding_update(finding, schemas.FindingUpdate(status="REJECTED", reviewer_note="not exploitable"))

    assert finding.status == "REJECTED"
    assert finding.frontmatter["review_history"][0] == {"note": "old"}
    assert finding.frontmatter["review_history"][1]["note"] == "not exploitable"
    assert "timestamp" in finding.frontmatter["review_history"][1]
