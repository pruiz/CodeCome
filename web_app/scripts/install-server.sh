#!/usr/bin/env bash
# Install CodeCome Web dependencies on an Ubuntu/Debian server.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
CODECOME_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
WORKSPACES_DIR="${WORKSPACES_DIR:-$CODECOME_ROOT/workspaces}"
CODE_SERVER_BIND_ADDR="${CODE_SERVER_BIND_ADDR:-127.0.0.1}"
CODE_SERVER_PUBLIC_BASE_URL="${CODE_SERVER_PUBLIC_BASE_URL:-}"
INSTALL_CODE_SERVER="${INSTALL_CODE_SERVER:-1}"
INSTALL_SEMGREP="${INSTALL_SEMGREP:-1}"
RUN_NPM_INSTALL="${RUN_NPM_INSTALL:-1}"

log() {
  printf '[codecome-web-install] %s\n' "$*"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

if ! need_cmd sudo; then
  echo "sudo is required." >&2
  exit 1
fi

log "Installing system packages."
sudo apt-get update
sudo apt-get install -y \
  ca-certificates \
  curl \
  docker.io \
  docker-compose-v2 \
  git \
  jq \
  make \
  nodejs \
  npm \
  python3 \
  python3-pip \
  python3-venv \
  rsync \
  unzip

sudo systemctl enable docker >/dev/null 2>&1 || true
sudo systemctl start docker >/dev/null 2>&1 || true
if ! groups "$USER" | grep -qw docker; then
  log "Adding $USER to docker group. Log out/in before running Docker without sudo."
  sudo usermod -aG docker "$USER" || true
fi

if [ "$INSTALL_CODE_SERVER" = "1" ] && ! need_cmd code-server; then
  log "Installing code-server."
  curl -fsSL https://code-server.dev/install.sh | sh
fi

if [ "$INSTALL_SEMGREP" = "1" ] && ! need_cmd semgrep; then
  log "Installing Semgrep."
  if ! python3 -m pip install --user --upgrade semgrep; then
    python3 -m pip install --upgrade semgrep --break-system-packages
  fi
fi

log "Creating backend virtualenv."
python3 -m venv "$BACKEND_DIR/venv"
"$BACKEND_DIR/venv/bin/python3" -m pip install --upgrade pip
"$BACKEND_DIR/venv/bin/python3" -m pip install -r "$BACKEND_DIR/requirements.txt"

if [ "$RUN_NPM_INSTALL" = "1" ]; then
  log "Installing frontend dependencies."
  (cd "$FRONTEND_DIR" && npm install)
fi

log "Writing backend .env."
cp -n "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
python3 - "$BACKEND_DIR/.env" "$CODECOME_ROOT" "$WORKSPACES_DIR" "$CODE_SERVER_BIND_ADDR" "$CODE_SERVER_PUBLIC_BASE_URL" <<'PY'
from pathlib import Path
import sys

env_path, root, workspaces, bind_addr, public_url = sys.argv[1:]
path = Path(env_path)
lines = path.read_text().splitlines()
updates = {
    "WORKSPACES_DIR": workspaces,
    "CODECOME_ROOT": root,
    "CODE_SERVER_BIND_ADDR": bind_addr,
    "CODE_SERVER_PUBLIC_BASE_URL": public_url,
}
seen = set()
out = []
for line in lines:
    key = line.split("=", 1)[0] if "=" in line and not line.lstrip().startswith("#") else None
    if key in updates:
        out.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n")
PY
chmod 600 "$BACKEND_DIR/.env"
mkdir -p "$WORKSPACES_DIR"

log "Starting PostgreSQL/Redis containers."
(cd "$ROOT_DIR" && docker compose up -d)

cat <<EOF

Install complete.

Start CodeCome Web:

  cd $ROOT_DIR
  ./start-services.sh

Frontend: http://<server>:3000
Backend:  http://<server>:8000

If you changed Docker group membership, log out/in before using Docker without sudo.
EOF
