import re
import base64

with open("tools/events/__init__.py", "r") as f:
    content = f.read()

# Update __init__ signature and body
new_init = """    def __init__(
        self,
        base_url: str,
        session_id: str,
        console: Any,
        phase: str,
        label: str,
        *,
        auth_token: str | None = None,
        workspace_dir: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session_id = session_id
        self.console = console
        self.phase = phase
        self.label = label
        self.auth_token = auth_token
        self.workspace_dir = workspace_dir"""

content = re.sub(r'    def __init__\([\s\S]*?self.label = label', new_init, content, flags=re.DOTALL)

# Update run to pass to SseClient
new_run = """        self._client = SseClient(
            self.base_url,
            auth_token=self.auth_token,
            workspace_dir=self.workspace_dir,
            reconnect=True,
            max_reconnects=10,
        )"""

content = re.sub(r'        self._client = SseClient\([\s\S]*?max_reconnects=10,\n        \)', new_run, content, flags=re.DOTALL)

# Add a helper method for headers
header_helper = """    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            import base64
            encoded = base64.b64encode(f"opencode:{self.auth_token}".encode("utf-8")).decode("utf-8")
            headers["Authorization"] = f"Basic {encoded}"
        if self.workspace_dir:
            headers["x-opencode-directory"] = self.workspace_dir
        return headers

    @staticmethod
    def _is_session_idle(event: dict[str, Any]) -> bool:"""

content = content.replace("    @staticmethod\n    def _is_session_idle(event: dict[str, Any]) -> bool:", header_helper)


# Update _handle_permission
new_handle_perm = """        req = urllib.request.Request(
            url,
            data=data,
            headers=self._get_headers(),
            method="POST",
        )"""
content = re.sub(r'        req = urllib.request.Request\([\s\S]*?method="POST",\n        \)', new_handle_perm, content, flags=re.DOTALL)

# Update _sync_session_messages
new_sync = """        try:
            req = urllib.request.Request(
                f"{self.base_url}/session/{self.session_id}/message",
                headers=self._get_headers(),
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10.0) as resp:"""
content = re.sub(r'        try:\n            req = urllib.request.Request\([\s\S]*?with urllib.request.urlopen\(req, timeout=10.0\) as resp:', new_sync, content, flags=re.DOTALL)

with open("tools/events/__init__.py", "w") as f:
    f.write(content)
