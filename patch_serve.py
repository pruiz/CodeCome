import re

with open("tools/opencode/serve.py", "r") as f:
    content = f.read()

start_def = """    def start(
        self,
        *,
        hostname: str = "127.0.0.1",
        port: int | None = None,
        log_level: str = "WARN",
        cwd: Optional[Path] = None,
    ) -> ServerInfo:
        \"\"\" Start opencode serve and return ServerInfo once healthy.

        Uses a free ephemeral port if port is None or 0.
        Server stdout/stderr is redirected to a log file in tmp/ to
        avoid the classic subprocess PIPE deadlock.

        Raises ServerRunnerError on startup failure.
        \"\"\"
        if self._info is not None:
            raise ServerRunnerError("Server already started")

        password = secrets.token_hex(16)
        log_path = _build_log_path()
        env = dict(os.environ)
        env["OPENCODE_SERVER_PASSWORD"] = password

        cmd = [
            "opencode", "serve",
            "--hostname", hostname,
            "--log-level", log_level,
        ]

        last_err: Optional[Exception] = None
        for attempt in range(3):
            actual_port = port
            if actual_port in (None, 0):
                actual_port = _find_free_port(hostname)

            attempt_cmd = cmd + ["--port", str(actual_port)]

            try:
                log_file = log_path.open("a")
                proc = subprocess.Popen(
                    attempt_cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    cwd=cwd or ROOT,
                    env=env,
                    start_new_session=True,
                )
            except FileNotFoundError:
                raise ServerRunnerError(
                    "opencode command not found. Is OpenCode installed and in PATH?"
                ) from None
            except OSError as exc:
                raise ServerRunnerError(
                    f"Failed to start opencode serve: {exc}"
                ) from exc

            base_url = f"http://{hostname}:{actual_port}"
            health_url = f"{base_url}/global/health"
            deadline = time.time() + _HEALTH_TIMEOUT_S

            health_ok = False

            while time.time() < deadline:
                if proc.poll() is not None:
                    last_err = ServerRunnerError(f"opencode serve exited early (exit code {proc.returncode}).")
                    break
                data = _try_fetch_json(health_url, timeout=2.0)
                if data and data.get("healthy") is True:
                    health_ok = True
                    break
                time.sleep(_HEALTH_INTERVAL_S)

            if health_ok:
                self._info = ServerInfo(
                    proc=proc,
                    pid=proc.pid,
                    base_url=base_url,
                    port=actual_port,
                    log_path=log_path,
                    password=password,
                )
                return self._info

            # If we reach here, this attempt failed. Kill and retry.
            self._kill(proc)

        log_tail = ""
        try:
            with open(log_path, "r") as f:
                lines = f.readlines()
                log_tail = "".join(lines[-30:])
        except OSError:
            pass

        raise ServerRunnerError(
            f"opencode serve failed to start after 3 attempts. Last error: {last_err}. "
            f"Log file: {log_path}\\n"
            f"Last lines:\\n{log_tail or '(empty)'}"
        )"""

# I need to replace from '    def start(' to '        return self._info' inclusive.
import re
new_content = re.sub(r'    def start\([\s\S]*?        return self._info', start_def, content)

with open("tools/opencode/serve.py", "w") as f:
    f.write(new_content)
