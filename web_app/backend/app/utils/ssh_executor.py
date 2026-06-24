from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
from stat import S_ISDIR
from typing import Callable
import posixpath
import shlex
import socket
import time

import paramiko

from app.utils.codecome_wrapper import CodeComeExecutor, ExecutionResult


class SSHExecutionError(RuntimeError):
    pass


@dataclass
class SSHWorkerConfig:
    host: str
    port: int
    username: str
    workspace_base_path: str
    auth_method: str
    password: str | None = None
    private_key: str | None = None
    passphrase: str | None = None


class SSHCodeComeExecutor:
    """Execute CodeCome phases on a remote worker over SSH."""

    def __init__(self, worker):
        self.worker = worker
        self.config = self._config_from_worker(worker)
        self.parser = CodeComeExecutor()

    def execute_phase(
        self,
        audit_id: str,
        local_workspace_path: Path,
        phase: str,
        model: str | None = None,
        variant: str | None = None,
        finding_id: str | None = None,
        thinking: bool = False,
        env_overrides: dict | None = None,
        output_callback: Callable[[str, str], None] | None = None,
        job_callback: Callable[[dict[str, str]], None] | None = None,
    ) -> ExecutionResult:
        started_at = datetime.now()
        client = None
        try:
            client = self._connect()
            sftp = client.open_sftp()
            remote_workspace = self.remote_workspace_path(audit_id)

            self._mkdir_p(sftp, remote_workspace)
            self._upload_tree(sftp, local_workspace_path, remote_workspace)

            job = self._start_detached_phase_job(
                client,
                sftp,
                remote_workspace,
                phase,
                model,
                variant,
                finding_id,
                thinking,
                env_overrides or {},
            )
            if output_callback:
                output_callback("system", f"Remote job started: pid={job.get('pid')} dir={job.get('job_dir')}")
            if job_callback:
                job_callback(job)
            exit_code, stdout, stderr = self._wait_for_detached_job(client, sftp, job, timeout=7200, output_callback=output_callback)

            # Always pull back reviewable artifacts, even on failure.
            self._download_artifacts(sftp, remote_workspace, local_workspace_path)

            completed_at = datetime.now()
            return ExecutionResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration=(completed_at - started_at).total_seconds(),
                started_at=started_at,
                completed_at=completed_at,
                metadata={"remote_job_dir": job.get("job_dir"), "remote_pid": job.get("pid")},
            )
        except Exception as exc:
            completed_at = datetime.now()
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                duration=(completed_at - started_at).total_seconds(),
                started_at=started_at,
                completed_at=completed_at,
            )
        finally:
            if client:
                client.close()

    def recover_phase(
        self,
        local_workspace_path: Path,
        remote_workspace: str,
        remote_job_dir: str,
        remote_pid: str | None = None,
        output_callback: Callable[[str, str], None] | None = None,
        timeout: int = 7200,
    ) -> ExecutionResult:
        started_at = datetime.now()
        client = None
        try:
            client = self._connect()
            sftp = client.open_sftp()
            job = {
                "job_dir": remote_job_dir,
                "pid": remote_pid or "",
                "stdout_path": posixpath.join(remote_job_dir, "stdout.log"),
                "stderr_path": posixpath.join(remote_job_dir, "stderr.log"),
                "exit_path": posixpath.join(remote_job_dir, "exit_code"),
            }
            if output_callback:
                output_callback("system", f"Recovering remote job: pid={remote_pid or '-'} dir={remote_job_dir}")
            exit_code, stdout, stderr = self._wait_for_detached_job(client, sftp, job, timeout=timeout, output_callback=output_callback)
            self._download_artifacts(sftp, remote_workspace, local_workspace_path)
            completed_at = datetime.now()
            return ExecutionResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration=(completed_at - started_at).total_seconds(),
                started_at=started_at,
                completed_at=completed_at,
                metadata={"remote_job_dir": remote_job_dir, "remote_pid": remote_pid},
            )
        except Exception as exc:
            completed_at = datetime.now()
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                duration=(completed_at - started_at).total_seconds(),
                started_at=started_at,
                completed_at=completed_at,
                metadata={"remote_job_dir": remote_job_dir, "remote_pid": remote_pid},
            )
        finally:
            if client:
                client.close()

    def cancel_remote_pid(self, remote_pid: str | None) -> None:
        if not remote_pid:
            return
        client = None
        try:
            client = self._connect()
            quoted = shlex.quote(str(remote_pid))
            self._run(client, f"bash -lc {shlex.quote(f'kill -TERM -- -{quoted} 2>/dev/null || kill -TERM {quoted} 2>/dev/null || true')}", timeout=15)
        finally:
            if client:
                client.close()

    def read_opencode_config(self) -> str:
        client = None
        try:
            client = self._connect()
            command = "bash -lc 'for path in ~/.config/opencode/opencode.jsonc ~/.config/opencode/opencode.json; do if [ -f \"$path\" ]; then cat \"$path\"; exit 0; fi; done; exit 1'"
            exit_code, stdout, stderr = self._run(client, command, timeout=20)
            if exit_code != 0:
                raise SSHExecutionError(stderr or "Remote OpenCode config not found")
            return stdout
        finally:
            if client:
                client.close()

    def parse_findings(self, workspace_path: Path):
        return self.parser.parse_findings(workspace_path)

    def remote_workspace_path(self, audit_id: str) -> str:
        return posixpath.join(self.config.workspace_base_path, f"audit-{audit_id}")

    def _config_from_worker(self, worker) -> SSHWorkerConfig:
        config = worker.config or {}
        auth = config.get("ssh_auth") or {}
        host = worker.host
        username = worker.username
        if not host:
            raise SSHExecutionError("SSH worker host is not configured")
        if not username:
            raise SSHExecutionError("SSH worker username is not configured")

        return SSHWorkerConfig(
            host=host,
            port=worker.port or 22,
            username=username,
            workspace_base_path=worker.workspace_base_path or "/srv/codecome/workspaces",
            auth_method=auth.get("method") or "key",
            password=auth.get("password"),
            private_key=auth.get("private_key"),
            passphrase=auth.get("passphrase"),
        )

    def _connect(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": self.config.host,
            "port": self.config.port,
            "username": self.config.username,
            "timeout": 20,
            "banner_timeout": 20,
            "auth_timeout": 20,
        }

        if self.config.auth_method == "password":
            if not self.config.password:
                raise SSHExecutionError("SSH password auth selected but password is empty")
            connect_kwargs["password"] = self.config.password
        else:
            if self.config.private_key:
                connect_kwargs["pkey"] = self._load_private_key(self.config.private_key, self.config.passphrase)
            elif self.config.password:
                connect_kwargs["password"] = self.config.password
            else:
                raise SSHExecutionError("SSH key auth selected but private key is empty")

        client.connect(**connect_kwargs)
        return client

    def _load_private_key(self, private_key: str, passphrase: str | None):
        loaders = [
            paramiko.Ed25519Key.from_private_key,
            paramiko.RSAKey.from_private_key,
            paramiko.ECDSAKey.from_private_key,
            paramiko.DSSKey.from_private_key,
        ]
        errors = []
        for loader in loaders:
            try:
                return loader(StringIO(private_key), password=passphrase or None)
            except Exception as exc:
                errors.append(str(exc))
        raise SSHExecutionError(f"Could not parse SSH private key: {'; '.join(errors[:2])}")

    def _phase_script(
        self,
        remote_workspace: str,
        job_dir: str,
        phase: str,
        model: str | None,
        variant: str | None,
        finding_id: str | None,
        thinking: bool,
        env_overrides: dict,
    ) -> str:
        exports = []
        if model:
            exports.append(f"export CODECOME_MODEL={shlex.quote(model)}")
        if variant:
            exports.append(f"export CODECOME_MODEL_VARIANT={shlex.quote(variant)}")
        if thinking:
            exports.append("export CODECOME_THINKING=1")
        for key, value in (env_overrides or {}).items():
            exports.append(f"export {shlex.quote(str(key))}={shlex.quote(str(value))}")

        if phase.startswith("make "):
            make_cmd = ["make", shlex.quote(phase.split(" ", 1)[1])]
        else:
            make_cmd = ["make", shlex.quote(phase)]
        if finding_id and not phase.startswith("make "):
            make_cmd.append(f"FINDING={shlex.quote(finding_id)}")

        return "\n".join([
            "#!/usr/bin/env bash",
            "set -o pipefail",
            f"cd {shlex.quote(remote_workspace)}",
            *exports,
            "if [ ! -x .venv/bin/python3 ]; then make init; fi",
            " ".join(make_cmd),
            "code=$?",
            f"printf '%s\\n' \"$code\" > {shlex.quote(posixpath.join(job_dir, 'exit_code'))}",
            "exit $code",
            "",
        ])

    def _start_detached_phase_job(
        self,
        client: paramiko.SSHClient,
        sftp: paramiko.SFTPClient,
        remote_workspace: str,
        phase: str,
        model: str | None,
        variant: str | None,
        finding_id: str | None,
        thinking: bool,
        env_overrides: dict | None,
    ) -> dict[str, str]:
        timestamp = int(time.time())
        safe_phase = phase.replace("/", "_")
        job_dir = posixpath.join(remote_workspace, ".codecome-web", "jobs", f"{safe_phase}-{timestamp}")
        self._mkdir_p(sftp, job_dir)

        script_path = posixpath.join(job_dir, "run.sh")
        stdout_path = posixpath.join(job_dir, "stdout.log")
        stderr_path = posixpath.join(job_dir, "stderr.log")
        exit_path = posixpath.join(job_dir, "exit_code")
        pid_path = posixpath.join(job_dir, "pid")

        script = self._phase_script(remote_workspace, job_dir, phase, model, variant, finding_id, thinking, env_overrides or {})
        with sftp.open(script_path, "w") as handle:
            handle.write(script)
        sftp.chmod(script_path, 0o755)

        start_command = (
            f"bash -lc {shlex.quote(f'nohup setsid bash {shlex.quote(script_path)} > {shlex.quote(stdout_path)} 2> {shlex.quote(stderr_path)} < /dev/null & echo $! > {shlex.quote(pid_path)}')}"
        )
        start_exit, start_stdout, start_stderr = self._run(client, start_command, timeout=30)
        if start_exit != 0:
            raise SSHExecutionError(f"Failed to start remote job: {start_stderr or start_stdout}")

        pid = self._read_remote_file(sftp, pid_path).strip()
        return {
            "job_dir": job_dir,
            "pid": pid,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "exit_path": exit_path,
        }

    def _wait_for_detached_job(
        self,
        client: paramiko.SSHClient,
        sftp: paramiko.SFTPClient,
        job: dict[str, str],
        timeout: int,
        output_callback: Callable[[str, str], None] | None = None,
    ) -> tuple[int, str, str]:
        deadline = time.time() + timeout
        transport = client.get_transport()
        sent_stdout = 0
        sent_stderr = 0
        while time.time() < deadline:
            if transport and transport.is_active():
                try:
                    transport.send_ignore()
                except Exception:
                    pass

            if output_callback:
                stdout_now = self._read_remote_file(sftp, job["stdout_path"]) if self._remote_exists(sftp, job["stdout_path"]) else ""
                stderr_now = self._read_remote_file(sftp, job["stderr_path"]) if self._remote_exists(sftp, job["stderr_path"]) else ""
                for line in stdout_now[sent_stdout:].splitlines():
                    if line.strip():
                        output_callback("stdout", line)
                for line in stderr_now[sent_stderr:].splitlines():
                    if line.strip():
                        output_callback("stderr", line)
                sent_stdout = len(stdout_now)
                sent_stderr = len(stderr_now)

            if self._remote_exists(sftp, job["exit_path"]):
                exit_text = self._read_remote_file(sftp, job["exit_path"]).strip()
                try:
                    exit_code = int(exit_text)
                except ValueError:
                    exit_code = -1
                stdout = self._read_remote_file(sftp, job["stdout_path"])
                stderr = self._read_remote_file(sftp, job["stderr_path"])
                return exit_code, stdout, stderr

            time.sleep(5)

        pid = job.get("pid")
        if pid:
            self._run(client, f"bash -lc {shlex.quote(f'kill {shlex.quote(pid)} 2>/dev/null || true')}", timeout=10)
        stdout = self._read_remote_file(sftp, job["stdout_path"]) if self._remote_exists(sftp, job["stdout_path"]) else ""
        stderr = self._read_remote_file(sftp, job["stderr_path"]) if self._remote_exists(sftp, job["stderr_path"]) else ""
        return -1, stdout, stderr + "\nDetached SSH job timed out"

    def _run(self, client: paramiko.SSHClient, command: str, timeout: int) -> tuple[int, str, str]:
        transport = client.get_transport()
        if not transport:
            raise SSHExecutionError("SSH transport is not available")
        channel = transport.open_session()
        channel.settimeout(2)
        channel.exec_command(command)

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        deadline = time.time() + timeout

        while True:
            if channel.recv_ready():
                stdout_parts.append(channel.recv(65535).decode(errors="replace"))
            if channel.recv_stderr_ready():
                stderr_parts.append(channel.recv_stderr(65535).decode(errors="replace"))
            if channel.exit_status_ready():
                while channel.recv_ready():
                    stdout_parts.append(channel.recv(65535).decode(errors="replace"))
                while channel.recv_stderr_ready():
                    stderr_parts.append(channel.recv_stderr(65535).decode(errors="replace"))
                return channel.recv_exit_status(), "".join(stdout_parts), "".join(stderr_parts)
            if time.time() > deadline:
                channel.close()
                return -1, "".join(stdout_parts), "SSH command timed out"
            time.sleep(0.2)

    def _mkdir_p(self, sftp: paramiko.SFTPClient, remote_path: str) -> None:
        current = ""
        for part in remote_path.strip("/").split("/"):
            current = f"{current}/{part}"
            try:
                sftp.stat(current)
            except FileNotFoundError:
                sftp.mkdir(current)

    def _upload_tree(self, sftp: paramiko.SFTPClient, local_root: Path, remote_root: str) -> None:
        for local_path in local_root.rglob("*"):
            rel = local_path.relative_to(local_root)
            if self._skip_upload(rel):
                continue
            remote_path = posixpath.join(remote_root, *rel.parts)
            if local_path.is_dir():
                self._mkdir_p(sftp, remote_path)
            elif local_path.is_file():
                self._mkdir_p(sftp, posixpath.dirname(remote_path))
                sftp.put(str(local_path), remote_path)

    def _skip_upload(self, rel: Path) -> bool:
        parts = set(rel.parts)
        return bool(parts & {".venv", "node_modules", "__pycache__"})

    def _download_if_exists(self, sftp: paramiko.SFTPClient, remote_path: str, local_path: Path) -> None:
        try:
            sftp.stat(remote_path)
        except FileNotFoundError:
            return
        self._download_tree(sftp, remote_path, local_path)

    def _download_artifacts(self, sftp: paramiko.SFTPClient, remote_workspace: str, local_workspace_path: Path) -> None:
        self._download_if_exists(sftp, posixpath.join(remote_workspace, "itemdb"), local_workspace_path / "itemdb")
        self._download_if_exists(sftp, posixpath.join(remote_workspace, "runs"), local_workspace_path / "runs")

    def _remote_exists(self, sftp: paramiko.SFTPClient, remote_path: str) -> bool:
        try:
            sftp.stat(remote_path)
            return True
        except FileNotFoundError:
            return False

    def _read_remote_file(self, sftp: paramiko.SFTPClient, remote_path: str) -> str:
        try:
            with sftp.open(remote_path, "r") as handle:
                data = handle.read()
                if isinstance(data, bytes):
                    return data.decode(errors="replace")
                return str(data)
        except FileNotFoundError:
            return ""

    def _download_tree(self, sftp: paramiko.SFTPClient, remote_path: str, local_path: Path) -> None:
        local_path.mkdir(parents=True, exist_ok=True)
        for entry in sftp.listdir_attr(remote_path):
            remote_child = posixpath.join(remote_path, entry.filename)
            local_child = local_path / entry.filename
            if S_ISDIR(entry.st_mode):
                self._download_tree(sftp, remote_child, local_child)
            else:
                local_child.parent.mkdir(parents=True, exist_ok=True)
                sftp.get(remote_child, str(local_child))
