from tools.opencode.serve import _try_fetch_json, _build_log_path, ServerRunner, _find_free_port
import os
import subprocess
import time
import secrets
import urllib.request

password = secrets.token_hex(16)
port = _find_free_port()
env = dict(os.environ)
env["OPENCODE_SERVER_PASSWORD"] = password
proc = subprocess.Popen(["opencode", "serve", "--port", str(port)], env=env)
time.sleep(2)
try:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/global/health", method="GET")
    with urllib.request.urlopen(req) as resp:
        print("Unauthenticated response:", resp.status)
except Exception as e:
    print("Unauthenticated error:", e)

import base64
try:
    encoded = base64.b64encode(f"opencode:{password}".encode("utf-8")).decode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/global/health",
        headers={"Authorization": f"Basic {encoded}"},
        method="GET"
    )
    with urllib.request.urlopen(req) as resp:
        print("Authenticated response:", resp.status)
except Exception as e:
    print("Authenticated error:", e)

proc.terminate()
