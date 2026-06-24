from types import SimpleNamespace

from app.utils.ssh_executor import SSHCodeComeExecutor


def test_ssh_executor_reads_worker_config_without_connecting():
    worker = SimpleNamespace(
        host="192.0.2.10",
        port=2222,
        username="codecome",
        workspace_base_path="/srv/codecome/workspaces",
        config={"ssh_auth": {"method": "password", "password": "secret"}},
    )

    executor = SSHCodeComeExecutor(worker)

    assert executor.config.host == "192.0.2.10"
    assert executor.config.port == 2222
    assert executor.config.username == "codecome"
    assert executor.config.auth_method == "password"
    assert executor.config.password == "secret"
    assert executor.remote_workspace_path("audit-id") == "/srv/codecome/workspaces/audit-audit-id"


def test_phase_script_contains_env_and_exit_code_file():
    worker = SimpleNamespace(
        host="192.0.2.10",
        port=22,
        username="codecome",
        workspace_base_path="/srv/workspaces",
        config={"ssh_auth": {"method": "password", "password": "secret"}},
    )
    executor = SSHCodeComeExecutor(worker)

    script = executor._phase_script(
        remote_workspace="/srv/workspaces/audit-1",
        job_dir="/srv/workspaces/audit-1/.codecome-web/jobs/phase-1-1",
        phase="phase-1",
        model="model/id",
        variant="high",
        finding_id=None,
        thinking=True,
        env_overrides={"PROMPT_EXTRA": "focus auth"},
    )

    assert "export CODECOME_MODEL=model/id" in script
    assert "export CODECOME_MODEL_VARIANT=high" in script
    assert "export CODECOME_THINKING=1" in script
    assert "export PROMPT_EXTRA='focus auth'" in script
    assert "make phase-1" in script
    assert "exit_code" in script
