from types import SimpleNamespace
from datetime import datetime
from uuid import uuid4

from app import crud, schemas
from app.api.audits import audit_response, next_audit_step, sandbox_runtime_env, sandbox_start_command
from app.api.workers import model_options_from_worker, registered_worker_config, validate_worker_registration_token
from app.utils.codecome_wrapper import CodeComeExecutor
from app.api import logs, workers
from app.workers.phase_tasks import build_command_line, status_phase
from app.workers.phase_tasks import audit_sandbox_project_name, audit_sandbox_runtime_port, merged_phase_env, prepare_audit_sandbox_runtime, rewrite_sandbox_compose_host_ports


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


def test_audit_list_response_omits_heavy_config(monkeypatch):
    audit = SimpleNamespace(
        id=uuid4(),
        name="demo",
        status="ready",
        current_phase=None,
        assigned_worker_id=None,
        question_owner_user_id=None,
        workspace_path="/work/audit-1",
        source_type="local",
        source_location="/src.zip",
        codecome_yml="large yml body",
        model_settings={"secret": "large settings"},
        ai_review_enabled=False,
        auto_continue=True,
        total_findings=0,
        findings_by_status={},
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    monkeypatch.setattr(crud, "question_counts_for_audit", lambda db, audit_id: {"open_questions": 0, "blocking_questions": 0})
    monkeypatch.setattr(crud, "get_user", lambda db, user_id: None)

    response = audit_response(audit, object(), include_config=False)

    assert response.has_codecome_yml is True
    assert response.codecome_yml is None
    assert response.model_settings == {}


def test_audit_response_includes_question_owner_name(monkeypatch):
    audit = SimpleNamespace(
        id=uuid4(),
        name="demo",
        status="ready",
        current_phase=None,
        assigned_worker_id=None,
        question_owner_user_id=7,
        workspace_path="/work/audit-1",
        source_type="local",
        source_location="/src.zip",
        codecome_yml=None,
        model_settings={},
        ai_review_enabled=False,
        auto_continue=True,
        total_findings=0,
        findings_by_status={},
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    owner = SimpleNamespace(display_name="AI Owner", is_llm_user=True)
    monkeypatch.setattr(crud, "question_counts_for_audit", lambda db, audit_id: {"open_questions": 0, "blocking_questions": 0})
    monkeypatch.setattr(crud, "get_user", lambda db, user_id: owner if user_id == 7 else None)

    response = audit_response(audit, object())

    assert response.question_owner_name == "AI Owner"
    assert response.question_owner_is_llm is True


def test_sandbox_start_command_reads_codecome_yml():
    audit = SimpleNamespace(codecome_yml="environment:\n  startup_command: ./sandbox/scripts/up.sh\n")

    assert sandbox_start_command(audit) == "./sandbox/scripts/up.sh"


def test_sandbox_start_command_defaults_when_missing():
    audit = SimpleNamespace(codecome_yml="project:\n  name: demo\n")

    assert sandbox_start_command(audit) == "./sandbox/scripts/up.sh"


def test_sandbox_runtime_env_is_audit_specific(tmp_path):
    audit = SimpleNamespace(id="11111111-2222-3333-4444-555555555555")

    env = sandbox_runtime_env(audit, tmp_path)

    assert env["COMPOSE_PROJECT_NAME"] == "codecome_11111111222233334444555555555555"
    assert env["CODECOME_AUDIT_ID"] == str(audit.id)
    assert env["CODECOME_WORKSPACE"] == str(tmp_path)


def test_phase_sandbox_runtime_rewrites_host_port_and_prompt(tmp_path):
    workspace = tmp_path / "workspace"
    sandbox = workspace / "sandbox"
    sandbox.mkdir(parents=True)
    (sandbox / "docker-compose.yml").write_text('services:\n  app:\n    ports:\n      - "8080:8080"\n')
    audit = SimpleNamespace(id="13555161-ddba-422d-bff8-47b149bac988")

    env = prepare_audit_sandbox_runtime(audit, workspace, {"PROMPT_EXTRA": "existing context"})
    host_port = audit_sandbox_runtime_port(str(audit.id), workspace)

    assert env["COMPOSE_PROJECT_NAME"] == audit_sandbox_project_name(str(audit.id))
    assert env["CODECOME_SANDBOX_URL"] == f"http://localhost:{host_port}"
    assert "existing context" in env["PROMPT_EXTRA"]
    assert "CODECOME_SANDBOX_URL" in env["PROMPT_EXTRA"]
    assert f'"{host_port}:8080"' in (sandbox / "docker-compose.yml").read_text()
    assert f"CODECOME_SANDBOX_HOST_PORT={host_port}" in (sandbox / ".env").read_text()


def test_phase_sandbox_runtime_reuses_persisted_port(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    sandbox = workspace / "sandbox"
    sandbox.mkdir(parents=True)
    (sandbox / ".env").write_text("CODECOME_SANDBOX_HOST_PORT=19081\n")
    audit = SimpleNamespace(id="22222222-2222-2222-2222-222222222222")
    monkeypatch.setattr("app.workers.phase_tasks.host_port_available", lambda port: False)

    env = prepare_audit_sandbox_runtime(audit, workspace)

    assert env["CODECOME_SANDBOX_HOST_PORT"] == "19081"
    assert env["CODECOME_SANDBOX_URL"] == "http://localhost:19081"


def test_rewrite_sandbox_compose_host_ports_leaves_non_app_ports(tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    compose = sandbox / "docker-compose.yml"
    compose.write_text('services:\n  app:\n    container_name: fixed-name\n    ports:\n      - "8080:8080"\n      - "5432:5432"\n')

    changed = rewrite_sandbox_compose_host_ports(tmp_path, 19001)

    assert changed is True
    text = compose.read_text()
    assert '"19001:8080"' in text
    assert '"5432:5432"' in text
    assert "container_name" not in text


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


def test_worker_job_state_reconciliation_releases_stale_local_worker():
    worker = SimpleNamespace(type="local", status="running", current_jobs=1, max_concurrent_jobs=1)

    changed = crud.sync_worker_job_state(worker, running_jobs=0)

    assert changed is True
    assert worker.current_jobs == 0
    assert worker.status == "idle"
    assert crud.worker_capacity_available(worker) is True


def test_worker_job_state_reconciliation_preserves_disabled_status():
    worker = SimpleNamespace(type="ssh", status="disabled", current_jobs=1, max_concurrent_jobs=2)

    crud.sync_worker_job_state(worker, running_jobs=0)

    assert worker.current_jobs == 0
    assert worker.status == "disabled"
    assert crud.worker_capacity_available(worker) is False


def test_remote_worker_model_options_from_config():
    worker = SimpleNamespace(type="ssh", config={"opencode_models": ["remote/model-a", {"id": "remote/model-b"}]})

    assert model_options_from_worker(worker) == [
        {"id": "remote/model-a", "provider": "remote", "model": "model-a"},
        {"id": "remote/model-b", "provider": "remote", "model": "model-b"},
    ]


def test_remote_worker_model_options_reads_live_ssh_config(monkeypatch):
    worker = SimpleNamespace(type="ssh", config={"opencode_models": ["stale/model"]})

    class FakeExecutor:
        def __init__(self, worker_arg):
            assert worker_arg is worker

        def read_opencode_config(self):
            return '{"provider":{"remote":{"models":{"live-model":{}}}}}'

    monkeypatch.setattr(workers, "SSHCodeComeExecutor", FakeExecutor)

    assert model_options_from_worker(worker) == [
        {"id": "remote/live-model", "provider": "remote", "model": "live-model"},
    ]


def test_remote_worker_model_options_falls_back_to_bootstrap_metadata(monkeypatch):
    worker = SimpleNamespace(type="ssh", config={"opencode_models": ["bootstrap/model"]})

    class FailingExecutor:
        def __init__(self, worker_arg):
            pass

        def read_opencode_config(self):
            raise RuntimeError("offline")

    monkeypatch.setattr(workers, "SSHCodeComeExecutor", FailingExecutor)

    assert model_options_from_worker(worker) == [
        {"id": "bootstrap/model", "provider": "bootstrap", "model": "model"},
    ]


def test_worker_registration_token_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(workers.settings, "WORKER_REGISTRATION_TOKEN", "secret")

    try:
        validate_worker_registration_token("wrong", None)
        raised = False
    except Exception as exc:
        raised = True
        assert getattr(exc, "status_code") == 401

    assert raised is True


def test_worker_registration_token_requires_configuration_when_not_debug(monkeypatch):
    monkeypatch.setattr(workers.settings, "WORKER_REGISTRATION_TOKEN", "")
    monkeypatch.setattr(workers.settings, "DEBUG", False)

    try:
        validate_worker_registration_token(None, None)
        raised = False
    except Exception as exc:
        raised = True
        assert getattr(exc, "status_code") == 503

    assert raised is True


def test_registered_worker_config_stores_bootstrap_metadata():
    registration = schemas.WorkerSelfRegister(
        name="runner-01",
        username="codecome",
        workspace_base_path="/opt/codecome/workspaces",
        config={"ssh_auth": {"method": "key", "private_key": "secret-key"}},
        requirements=[{"key": "docker", "label": "Docker", "required": True, "ok": True, "detail": "ok"}],
        opencode_models=["remote/model-a"],
    )

    config = registered_worker_config(registration)

    assert config["registered_by_bootstrap"] is True
    assert config["requirements"][0]["key"] == "docker"
    assert config["opencode_models"] == ["remote/model-a"]
    assert config["ssh_auth"]["private_key"] == "secret-key"


def test_register_worker_creates_remote_worker(monkeypatch):
    captured = {}
    db = FakeDb()
    registration = schemas.WorkerSelfRegister(
        name="runner-01",
        type="proxmox-vm",
        username="codecome",
        workspace_base_path="/opt/codecome/workspaces",
        requirements=[{"key": "docker", "label": "Docker", "required": True, "ok": True, "detail": "ok"}],
    )

    def fake_create_worker(db_arg, worker_data):
        captured["worker_data"] = worker_data
        return SimpleNamespace(
            id=12,
            name=worker_data.name,
            type=worker_data.type,
            status="idle",
            host=worker_data.host,
            port=worker_data.port,
            username=worker_data.username,
            workspace_base_path=worker_data.workspace_base_path,
            max_concurrent_jobs=worker_data.max_concurrent_jobs,
            current_jobs=0,
            capabilities=worker_data.capabilities,
            config=worker_data.config,
            last_seen=None,
            created_at=None,
            updated_at=None,
        )

    monkeypatch.setattr(workers.settings, "WORKER_REGISTRATION_TOKEN", "secret")
    monkeypatch.setattr(workers.crud, "get_worker_by_name", lambda db_arg, name: None)
    monkeypatch.setattr(workers.crud, "create_worker", fake_create_worker)

    response = workers.register_worker(
        registration,
        request=SimpleNamespace(client=SimpleNamespace(host="10.0.0.5")),
        x_codecome_worker_token="secret",
        db=db,
    )

    assert response["name"] == "runner-01"
    assert response["type"] == "proxmox-vm"
    assert response["host"] == "10.0.0.5"
    assert captured["worker_data"].config["registered_by_bootstrap"] is True


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


def test_phase_command_line_shows_env_overrides_after_model_defaults():
    command = build_command_line(
        "phase-1",
        model="worker/default",
        worker_type="local",
        env_overrides={"CODECOME_MODEL": "audit/override"},
    )

    assert command.index("CODECOME_MODEL=worker/default") < command.index("CODECOME_MODEL=audit/override")


def test_merged_phase_env_phase_overrides_audit_defaults():
    settings = {
        "__audit_options": {"worker_model": "worker/default"},
        "__audit_env": {"env": {"PROMPT_EXTRA": "audit prompt", "CODECOME_THINKING": "0", "CODECOME_MODEL": "audit/model"}},
        "phase-1": {"env": {"PROMPT_EXTRA": "phase prompt", "CODECOME_MODEL": "phase/model"}},
    }

    assert merged_phase_env(settings, "phase-1") == {
        "PROMPT_EXTRA": "phase prompt",
        "CODECOME_THINKING": "0",
        "CODECOME_MODEL": "phase/model",
    }


def test_merged_phase_env_uses_worker_model_as_lowest_priority_default():
    settings = {"__audit_options": {"worker_model": "worker/default"}}

    assert merged_phase_env(settings, "phase-1")["CODECOME_MODEL"] == "worker/default"


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
