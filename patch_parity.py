import re

with open("tools/mock-llm-parity.py", "r") as f:
    content = f.read()

# Update _post_json
new_post_json = """def _post_json(url: str, payload: dict[str, Any], timeout: float = 30.0, auth_token: str | None = None, workspace_dir: str | None = None) -> Any:
    headers = {"Content-Type": "application/json"}
    if auth_token:
        import base64
        encoded = base64.b64encode(f"opencode:{auth_token}".encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {encoded}"
    if workspace_dir:
        headers["x-opencode-directory"] = workspace_dir
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else None"""

content = re.sub(r'def _post_json\([\s\S]*?return json.loads\(body\) if body else None', new_post_json, content, flags=re.DOTALL)

# Update run_serve
new_run_serve = """        created = _post_json(
            f"{base_url}/session",
            {
                "title": "MockLLM parity test",
                "agent": agent,
                "model": _create_model_payload(model, create=True),
            },
            timeout=10.0,
            auth_token=info.password,
            workspace_dir=str(ROOT),
        )
        session_id = str(created.get("id", ""))
        if not session_id:
            raise RuntimeError("session.create returned empty id")

        loop = EventLoop(base_url, session_id, None, "1", "recon", auth_token=info.password, workspace_dir=str(ROOT))

        # Start event consumer BEFORE sending prompt to avoid losing early SSE events.
        import threading

        event_result_box: dict[str, Any] = {}

        def _consume() -> None:
            try:
                event_result_box["result"] = loop.run(collect_render)
            except Exception as exc:
                event_result_box["error"] = exc

        consumer = threading.Thread(target=_consume, name=f"parity-events-{session_id}", daemon=True)
        consumer.start()

        body = {
            "parts": [{"type": "text", "text": prompt}],
            "agent": agent,
            "model": _create_model_payload(model, create=False),
        }
        _post_json(
            f"{base_url}/session/{session_id}/prompt_async",
            body,
            timeout=timeout,
            auth_token=info.password,
            workspace_dir=str(ROOT),
        )"""

content = re.sub(r'        created = _post_json\([\s\S]*?timeout=timeout,\n        \)', new_run_serve, content, flags=re.DOTALL)

with open("tools/mock-llm-parity.py", "w") as f:
    f.write(content)
