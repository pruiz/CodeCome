#!/usr/bin/env bash
# Bootstrap a CodeCome worker on a VM, LXC, or physical machine.
#
# Intended worker model:
# - Databases/web control plane stay on the web host.
# - CodeCome CLI runs natively on this worker.
# - Docker runs on this worker for CodeCome sandbox/POCs.
#
# Usage examples:
#   sudo bash worker-bootstrap.sh
#   sudo CODECOME_WORKER_NAME=runner-01 CODECOME_WORKSPACE_BASE=/srv/codecome/workspaces bash worker-bootstrap.sh
#   sudo OPENCODE_CONFIG_URL=https://example.local/opencode.jsonc bash worker-bootstrap.sh
#   sudo OPENCODE_CONFIG_B64=$(base64 -w0 opencode.jsonc) bash worker-bootstrap.sh

set -euo pipefail

CODECOME_WORKER_NAME="${CODECOME_WORKER_NAME:-$(hostname -s)}"
CODECOME_WORKER_USER="${CODECOME_WORKER_USER:-codecome}"
CODECOME_HOME="${CODECOME_HOME:-/opt/codecome}"
CODECOME_WORKSPACE_BASE="${CODECOME_WORKSPACE_BASE:-/opt/codecome/workspaces}"
CODECOME_REPO_URL="${CODECOME_REPO_URL:-}"
CODECOME_REPO_REF="${CODECOME_REPO_REF:-}"
OPENCODE_CONFIG_URL="${OPENCODE_CONFIG_URL:-}"
OPENCODE_CONFIG_B64="${OPENCODE_CONFIG_B64:-}"
INSTALL_DOCKER="${INSTALL_DOCKER:-1}"
RUN_MAKE_INIT="${RUN_MAKE_INIT:-1}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root, for example: sudo bash worker-bootstrap.sh" >&2
  exit 1
fi

log() {
  printf '[codecome-worker] %s\n' "$*"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

install_packages() {
  if need_cmd apt-get; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y \
      ca-certificates \
      curl \
      git \
      jq \
      make \
      nodejs \
      npm \
      openssh-server \
      python3 \
      python3-pip \
      python3-venv \
      rsync \
      unzip
  elif need_cmd dnf; then
    dnf install -y ca-certificates curl git jq make nodejs npm openssh-server python3 python3-pip rsync unzip
  elif need_cmd yum; then
    yum install -y ca-certificates curl git jq make nodejs npm openssh-server python3 python3-pip rsync unzip
  else
    echo "Unsupported package manager. Install dependencies manually." >&2
    exit 1
  fi
}

install_docker() {
  if [ "$INSTALL_DOCKER" != "1" ]; then
    log "Skipping Docker install (INSTALL_DOCKER=$INSTALL_DOCKER)."
    return
  fi

  if need_cmd docker; then
    log "Docker already installed."
  elif need_cmd apt-get; then
    apt-get install -y docker.io
  else
    log "Installing Docker via get.docker.com."
    curl -fsSL https://get.docker.com | sh
  fi

  systemctl enable docker >/dev/null 2>&1 || true
  systemctl start docker >/dev/null 2>&1 || true
}

create_worker_user() {
  if ! id "$CODECOME_WORKER_USER" >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash "$CODECOME_WORKER_USER"
  fi

  usermod -aG docker "$CODECOME_WORKER_USER" >/dev/null 2>&1 || true
}

prepare_directories() {
  mkdir -p "$CODECOME_HOME" "$CODECOME_WORKSPACE_BASE"
  chown -R "$CODECOME_WORKER_USER:$CODECOME_WORKER_USER" "$CODECOME_HOME" "$CODECOME_WORKSPACE_BASE"
}

install_opencode_config() {
  local user_home
  user_home="$(getent passwd "$CODECOME_WORKER_USER" | cut -d: -f6)"
  local config_dir="$user_home/.config/opencode"
  local config_path="$config_dir/opencode.jsonc"

  mkdir -p "$config_dir"

  if [ -n "$OPENCODE_CONFIG_B64" ]; then
    log "Installing OpenCode config from OPENCODE_CONFIG_B64."
    printf '%s' "$OPENCODE_CONFIG_B64" | base64 -d > "$config_path"
  elif [ -n "$OPENCODE_CONFIG_URL" ]; then
    log "Installing OpenCode config from URL: $OPENCODE_CONFIG_URL"
    curl -fsSL "$OPENCODE_CONFIG_URL" -o "$config_path"
  else
    log "No OpenCode config provided. Leaving $config_path untouched."
  fi

  chown -R "$CODECOME_WORKER_USER:$CODECOME_WORKER_USER" "$config_dir"
  chmod 700 "$config_dir"
  [ ! -f "$config_path" ] || chmod 600 "$config_path"
}

install_codecome_repo() {
  if [ -z "$CODECOME_REPO_URL" ]; then
    log "CODECOME_REPO_URL not provided. Skipping repository clone."
    log "You can later sync CodeCome to: $CODECOME_HOME/CodeCome_WEB"
    return
  fi

  local target="$CODECOME_HOME/CodeCome_WEB"
  if [ ! -d "$target/.git" ]; then
    log "Cloning CodeCome repo to $target"
    sudo -u "$CODECOME_WORKER_USER" git clone "$CODECOME_REPO_URL" "$target"
  else
    log "CodeCome repo already exists at $target; pulling updates."
    sudo -u "$CODECOME_WORKER_USER" git -C "$target" pull --ff-only || true
  fi

  if [ -n "$CODECOME_REPO_REF" ]; then
    sudo -u "$CODECOME_WORKER_USER" git -C "$target" checkout "$CODECOME_REPO_REF"
  fi

  if [ "$RUN_MAKE_INIT" = "1" ] && [ -f "$target/Makefile" ]; then
    log "Running make init in $target"
    sudo -u "$CODECOME_WORKER_USER" bash -lc "cd '$target' && make init"
  fi
}

write_profile() {
  cat > /etc/profile.d/codecome-worker.sh <<EOF
export CODECOME_HOME="$CODECOME_HOME"
export CODECOME_WORKSPACE_BASE="$CODECOME_WORKSPACE_BASE"
EOF
  chmod 644 /etc/profile.d/codecome-worker.sh
}

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))'
}

check_command() {
  local key="$1"
  local label="$2"
  local required="$3"
  local command_name="$4"
  shift 4
  local ok=false
  local detail="not found"
  if command -v "$command_name" >/dev/null 2>&1; then
    if detail_out=$("$command_name" "$@" 2>&1 | head -n 1); then
      ok=true
      detail="$detail_out"
    else
      detail="$detail_out"
    fi
  fi
  printf '{"key":"%s","label":"%s","required":%s,"ok":%s,"detail":%s}' \
    "$key" "$label" "$required" "$ok" "$(printf '%s' "$detail" | json_escape)"
}

collect_requirements() {
  local user_home
  user_home="$(getent passwd "$CODECOME_WORKER_USER" | cut -d: -f6)"
  local opencode_config_ok=false
  local opencode_config_detail="No OpenCode config found"
  if [ -f "$user_home/.config/opencode/opencode.jsonc" ]; then
    opencode_config_ok=true
    opencode_config_detail="$user_home/.config/opencode/opencode.jsonc"
  elif [ -f "$user_home/.config/opencode/opencode.json" ]; then
    opencode_config_ok=true
    opencode_config_detail="$user_home/.config/opencode/opencode.json"
  fi

  local python_ok=false
  local python_detail="not found"
  if command -v python3 >/dev/null 2>&1; then
    python_detail="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
    if python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)'; then
      python_ok=true
    fi
  fi

  local docker_ok=false
  local docker_detail="not found"
  if command -v docker >/dev/null 2>&1; then
    docker_detail="$(docker --version 2>&1 | head -n 1)"
    if docker info >/dev/null 2>&1; then
      docker_ok=true
    else
      docker_detail="Docker installed but daemon unavailable for current context"
    fi
  fi

  local xvfb_json
  if command -v Xvfb >/dev/null 2>&1; then
    xvfb_json="$(check_command xvfb 'Xvfb / xvfb-run' false Xvfb -version)"
  else
    xvfb_json="$(check_command xvfb 'Xvfb / xvfb-run' false xvfb-run --help)"
  fi

  cat <<EOF
[
  $(check_command opencode_installed 'OpenCode installed' true opencode --version),
  {"key":"opencode_configured","label":"OpenCode provider configured","required":true,"ok":$opencode_config_ok,"detail":$(printf '%s' "$opencode_config_detail" | json_escape)},
  {"key":"python_310","label":"Python 3.10+","required":true,"ok":$python_ok,"detail":$(printf '%s' "$python_detail" | json_escape)},
  $(check_command gnu_make 'GNU Make' true make --version),
  {"key":"docker","label":"Docker CLI and daemon","required":true,"ok":$docker_ok,"detail":$(printf '%s' "$docker_detail" | json_escape)},
  $(check_command codeql_cli 'CodeQL CLI' false codeql --version),
  $(check_command asciinema 'asciinema' false asciinema --version),
  $(check_command agg 'agg' false agg --version),
  $(check_command ffmpeg 'ffmpeg' false ffmpeg -version),
  $xvfb_json
]
EOF
}

print_registration() {
  local host_ip
  host_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [ -z "$host_ip" ]; then
    host_ip="$(hostname -f 2>/dev/null || hostname)"
  fi

  local requirements_json
  requirements_json="$(collect_requirements | jq -c .)"
  mkdir -p "$CODECOME_HOME"
  printf '%s\n' "$requirements_json" > "$CODECOME_HOME/worker-requirements.json"
  chown "$CODECOME_WORKER_USER:$CODECOME_WORKER_USER" "$CODECOME_HOME/worker-requirements.json" || true

  cat <<EOF

Bootstrap complete.

Register this worker in CodeCome Web:

curl -X POST http://<CODECOME_WEB_HOST>:8000/api/workers/ \\
  -H 'Content-Type: application/json' \\
  -d '{
    "name": "$CODECOME_WORKER_NAME",
    "type": "ssh",
    "host": "$host_ip",
    "port": 22,
    "username": "$CODECOME_WORKER_USER",
    "workspace_base_path": "$CODECOME_WORKSPACE_BASE",
    "max_concurrent_jobs": 1,
    "capabilities": {"docker": true, "codecome": true},
    "config": {"codecome_home": "$CODECOME_HOME", "requirements": $requirements_json}
  }'

Requirement metadata was also written to:
  $CODECOME_HOME/worker-requirements.json

Important:
- Add your web host SSH public key to ~$CODECOME_WORKER_USER/.ssh/authorized_keys.
- If this is an LXC and Docker must run inside it, Proxmox nesting/privileged settings may be required.
- VMs are recommended for untrusted targets.
EOF
}

main() {
  log "Installing packages."
  install_packages
  log "Installing Docker runtime."
  install_docker
  log "Creating worker user."
  create_worker_user
  log "Preparing directories."
  prepare_directories
  log "Installing OpenCode config if provided."
  install_opencode_config
  log "Installing CodeCome repo if provided."
  install_codecome_repo
  write_profile
  print_registration
}

main "$@"
