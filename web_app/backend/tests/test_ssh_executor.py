from types import SimpleNamespace

from app.utils.ssh_executor import SSHCodeComeExecutor


class FakeSftp:
    def __init__(self):
        self.dirs = set()
        self.puts = []

    def stat(self, path):
        if path not in self.dirs:
            raise FileNotFoundError(path)

    def mkdir(self, path):
        self.dirs.add(path)

    def put(self, local_path, remote_path):
        self.puts.append((local_path, remote_path))


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


def test_gap_sweep_phase_script_uses_make_target_and_args_env():
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
        job_dir="/srv/workspaces/audit-1/.codecome-web/jobs/gap-sweep-1",
        phase="gap-sweep",
        model=None,
        variant=None,
        finding_id=None,
        thinking=False,
        env_overrides={"ARGS": "--candidate GAP-0007"},
    )

    assert "export ARGS='--candidate GAP-0007'" in script
    assert "make gap-sweep" in script


def test_gap_scan_phase_script_exports_custom_prompt_file():
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
        job_dir="/srv/workspaces/audit-1/.codecome-web/jobs/gap-scan-1",
        phase="gap-scan",
        model=None,
        variant=None,
        finding_id=None,
        thinking=False,
        env_overrides={"CODECOME_GAP_PROMPT_FILE": "runs/gap-scan-prompt.md"},
    )

    assert "export CODECOME_GAP_PROMPT_FILE=runs/gap-scan-prompt.md" in script
    assert "make gap-scan" in script


def test_upload_tree_copies_workspace_source_to_remote_worker(tmp_path):
    worker = SimpleNamespace(
        host="192.0.2.10",
        port=22,
        username="codecome",
        workspace_base_path="/srv/workspaces",
        config={"ssh_auth": {"method": "password", "password": "secret"}},
    )
    workspace = tmp_path / "audit-1"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "app.py").write_text("print('copied')\n")
    (workspace / "Makefile").write_text("all:\n\ttrue\n")
    sftp = FakeSftp()
    executor = SSHCodeComeExecutor(worker)

    executor._mkdir_p(sftp, "/srv/workspaces/audit-1")
    executor._upload_tree(sftp, workspace, "/srv/workspaces/audit-1")

    remote_paths = {remote for _, remote in sftp.puts}
    assert "/srv/workspaces/audit-1/src/app.py" in remote_paths
    assert "/srv/workspaces/audit-1/Makefile" in remote_paths


def test_download_artifacts_pulls_itemdb_and_runs(tmp_path):
    worker = SimpleNamespace(
        host="192.0.2.10",
        port=22,
        username="codecome",
        workspace_base_path="/srv/workspaces",
        config={"ssh_auth": {"method": "password", "password": "secret"}},
    )
    executor = SSHCodeComeExecutor(worker)
    calls = []

    def fake_download_if_exists(sftp, remote_path, local_path):
        calls.append((remote_path, local_path))

    executor._download_if_exists = fake_download_if_exists

    executor._download_artifacts(object(), "/srv/workspaces/audit-1", tmp_path / "audit-1")

    assert calls == [
        ("/srv/workspaces/audit-1/itemdb", tmp_path / "audit-1" / "itemdb"),
        ("/srv/workspaces/audit-1/runs", tmp_path / "audit-1" / "runs"),
    ]


def test_read_opencode_config_uses_remote_worker(monkeypatch):
    worker = SimpleNamespace(
        host="192.0.2.10",
        port=22,
        username="codecome",
        workspace_base_path="/srv/workspaces",
        config={"ssh_auth": {"method": "password", "password": "secret"}},
    )
    executor = SSHCodeComeExecutor(worker)
    commands = []

    class FakeClient:
        def close(self):
            pass

    monkeypatch.setattr(executor, "_connect", lambda: FakeClient())

    def fake_run(client, command, timeout):
        commands.append(command)
        return 0, '{"provider":{"remote":{"models":{"live":{}}}}}', ""

    monkeypatch.setattr(executor, "_run", fake_run)

    assert executor.read_opencode_config() == '{"provider":{"remote":{"models":{"live":{}}}}}'
    assert "~/.config/opencode/opencode.jsonc" in commands[0]
