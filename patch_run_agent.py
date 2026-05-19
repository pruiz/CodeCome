import re

with open("tools/run-agent.py", "r") as f:
    content = f.read()

# Add get_headers helper
header_helper = """def _get_headers(auth_token: str | None, workspace_dir: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if auth_token:
        import base64
        encoded = base64.b64encode(f"opencode:{auth_token}".encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {encoded}"
    if workspace_dir:
        headers["x-opencode-directory"] = workspace_dir
    return headers

def _send_prompt_to_session("""

content = content.replace("def _send_prompt_to_session(", header_helper)


# Update _send_prompt_to_session
new_send_prompt = """def _send_prompt_to_session(
    base_url: str,
    session_id: str,
    prompt: str,
    agent: str,
    model: str | None,
    variant: str | None,
    auth_token: str | None,
    workspace_dir: str | None,
) -> None:
    \"\"\"Send a prompt text to a session via POST /session/{id}/prompt_async.\"\"\"
    url = f"{base_url}/session/{session_id}/prompt_async"
    payload: dict[str, Any] = {
        "parts": [{"type": "text", "text": prompt}],
        "agent": agent,
    }
    if model:
        parts = model.split("/", 1)
        if len(parts) == 2:
            payload["model"] = {"providerID": parts[0], "modelID": parts[1]}
        else:
            payload["model"] = {"modelID": model}
    if variant:
        payload["variant"] = variant
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers=_get_headers(auth_token, workspace_dir),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            pass  # 204 expected
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Failed to send prompt: HTTP {exc.code}") from exc"""

content = re.sub(r'def _send_prompt_to_session\([\s\S]*?raise RuntimeError\(f"Failed to send prompt: HTTP \{exc\.code\}"\) from exc', new_send_prompt, content, flags=re.DOTALL)


# Update _create_session
new_create_session = """def _create_session(base_url: str, phase: str, agent: str, model: str | None, auth_token: str | None, workspace_dir: str | None) -> str:
    \"\"\"Create a session via POST /session and return its ID.\"\"\"
    payload: dict[str, Any] = {"title": f"CodeCome Phase {phase}", "agent": agent}
    if model:
        parts = model.split("/", 1)
        if len(parts) == 2:
            payload["model"] = {"providerID": parts[0], "id": parts[1]}
        else:
            payload["model"] = {"id": model}
    req = urllib.request.Request(
        f"{base_url}/session",
        data=json.dumps(payload).encode("utf-8"),
        headers=_get_headers(auth_token, workspace_dir),
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=10.0)
    data = json.loads(resp.read().decode("utf-8"))
    sid = str(data.get("id", ""))
    if not sid:
        raise RuntimeError("Server returned empty session ID")
    return sid"""

content = re.sub(r'def _create_session\([\s\S]*?return sid', new_create_session, content, flags=re.DOTALL)


# Update _consume_events
new_consume = """def _consume_events(
    base_url: str,
    session_id: str,
    console: Any,
    phase: str,
    label: str,
    args: argparse.Namespace,
    transcript_fp: Any | None,
    thinking_on: bool,
    auth_token: str | None,
    workspace_dir: str | None,
) -> RunResult:
    \"\"\"Create an EventLoop, consume SSE until idle, and return RunResult.\"\"\"
    event_loop = EventLoop(
        base_url=base_url,
        session_id=session_id,
        console=console,
        phase=phase,
        label=label,
        auth_token=auth_token,
        workspace_dir=workspace_dir,
    )"""

content = re.sub(r'def _consume_events\([\s\S]*?label=label,\n    \)', new_consume, content, flags=re.DOTALL)


# Update _run_single_attempt signature and calls
new_run_single = """def _run_single_attempt(
    args: argparse.Namespace,
    console: Any,
    prompt: str,
    model: str | None,
    variant: str | None,
    thinking_on: bool,
    base_url: str,
    auth_token: str | None,
    workspace_dir: str | None,
    existing_session_id: str | None = None,
) -> tuple[int, str, RunResult, Path]:"""

content = content.replace("""def _run_single_attempt(
    args: argparse.Namespace,
    console: Any,
    prompt: str,
    model: str | None,
    variant: str | None,
    thinking_on: bool,
    base_url: str,
    existing_session_id: str | None = None,
) -> tuple[int, str, RunResult, Path]:""", new_run_single)

content = content.replace("session_id = _create_session(base_url, str(args.phase), args.agent, model)", "session_id = _create_session(base_url, str(args.phase), args.agent, model, auth_token, workspace_dir)")
content = content.replace("""                    thinking_on,
                )""", """                    thinking_on,
                    auth_token,
                    workspace_dir,
                )""")
content = content.replace("_send_prompt_to_session(base_url, session_id, prompt, args.agent, model, variant)", "_send_prompt_to_session(base_url, session_id, prompt, args.agent, model, variant, auth_token, workspace_dir)")


# Update main loop
new_main_call = """            returncode, session_id, run_result, transcript_path = _run_single_attempt(
                args, console, prompt, model, variant, thinking_on, base_url,
                server_info.password, str(ROOT),
                existing_session_id=last_session_id or None
            )"""

content = re.sub(r'            returncode, session_id, run_result, transcript_path = _run_single_attempt\([\s\S]*?existing_session_id=last_session_id or None\n            \)', new_main_call, content, flags=re.DOTALL)


with open("tools/run-agent.py", "w") as f:
    f.write(content)

