import re

with open("tools/events/sse_client.py", "r") as f:
    content = f.read()

# Replace _build_sse_request
new_build = """import base64

def _build_sse_request(base_url: str, auth_token: str | None = None, workspace_dir: str | None = None) -> urllib.request.Request:
    \"\"\"Return a GET /event request with SSE headers.\"\"\"
    headers = {
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
    }
    if auth_token:
        encoded = base64.b64encode(f"opencode:{auth_token}".encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {encoded}"
    if workspace_dir:
        headers["x-opencode-directory"] = workspace_dir

    return urllib.request.Request(
        f"{base_url}/event",
        headers=headers,
        method="GET",
    )"""

content = re.sub(r'def _build_sse_request.*?method="GET",\n    \)', new_build, content, flags=re.DOTALL)

# Replace __init__
new_init = """    def __init__(
        self,
        base_url: str,
        *,
        auth_token: str | None = None,
        workspace_dir: str | None = None,
        reconnect: bool = True,
        max_reconnects: int = 10,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.workspace_dir = workspace_dir
        self.reconnect = reconnect
        self.max_reconnects = max_reconnects"""

content = re.sub(r'    def __init__\(\s*self,\s*base_url: str,\s*\*,.*?self.max_reconnects = max_reconnects', new_init, content, flags=re.DOTALL)

# Replace _open_stream
new_open_stream = """    def _open_stream(self) -> Iterator[dict]:
        \"\"\" Open the SSE connection and yield parsed events. \"\"\"
        req = _build_sse_request(self.base_url, self.auth_token, self.workspace_dir)"""

content = re.sub(r'    def _open_stream\(self\) -> Iterator\[dict\]:\s*\"\"\" Open the SSE connection and yield parsed events. \"\"\"\s*req = _build_sse_request\(self.base_url\)', new_open_stream, content, flags=re.DOTALL)

with open("tools/events/sse_client.py", "w") as f:
    f.write(content)
