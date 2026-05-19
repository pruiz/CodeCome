import re
import base64

with open("tools/opencode/serve.py", "r") as f:
    content = f.read()

# Update _try_fetch_json
new_try = """def _try_fetch_json(url: str, timeout: float, auth_token: str | None = None) -> dict | None:
    \"\"\" Best-effort GET returning parsed JSON, or None on any failure. \"\"\"
    try:
        headers = {}
        if auth_token:
            import base64
            encoded = base64.b64encode(f"opencode:{auth_token}".encode("utf-8")).decode("utf-8")
            headers["Authorization"] = f"Basic {encoded}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None"""

content = re.sub(r'def _try_fetch_json\([\s\S]*?return None', new_try, content, flags=re.DOTALL)

# Update the call in start()
content = content.replace("data = _try_fetch_json(health_url, timeout=2.0)", "data = _try_fetch_json(health_url, timeout=2.0, auth_token=password)")

with open("tools/opencode/serve.py", "w") as f:
    f.write(content)

