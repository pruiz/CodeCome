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
#   sudo CODECOME_WEB_URL=http://codecome-web:8000 CODECOME_WORKER_REGISTRATION_TOKEN=... bash worker-bootstrap.sh
#   sudo OPENCODE_CONFIG_URL=https://example.local/opencode.jsonc bash worker-bootstrap.sh
#   sudo OPENCODE_CONFIG_B64=$(base64 -w0 opencode.jsonc) bash worker-bootstrap.sh

set -euo pipefail

CODECOME_WORKER_NAME="${CODECOME_WORKER_NAME:-$(hostname -s)}"
CODECOME_WORKER_TYPE="${CODECOME_WORKER_TYPE:-ssh}"
CODECOME_WORKER_USER="${CODECOME_WORKER_USER:-codecome}"
CODECOME_HOME="${CODECOME_HOME:-/opt/codecome}"
CODECOME_WORKSPACE_BASE="${CODECOME_WORKSPACE_BASE:-/opt/codecome/workspaces}"
CODECOME_WEB_URL="${CODECOME_WEB_URL:-}"
CODECOME_WORKER_REGISTRATION_TOKEN="${CODECOME_WORKER_REGISTRATION_TOKEN:-}"
CODECOME_REGISTER="${CODECOME_REGISTER:-1}"
CODECOME_MAX_CONCURRENT_JOBS="${CODECOME_MAX_CONCURRENT_JOBS:-1}"
CODECOME_GENERATE_SSH_KEY="${CODECOME_GENERATE_SSH_KEY:-1}"
CODECOME_REPO_URL="${CODECOME_REPO_URL:-}"
CODECOME_REPO_REF="${CODECOME_REPO_REF:-}"
OPENCODE_CONFIG_URL="${OPENCODE_CONFIG_URL:-}"
OPENCODE_CONFIG_B64="${OPENCODE_CONFIG_B64:-}"
INSTALL_DOCKER="${INSTALL_DOCKER:-1}"
INSTALL_SEMGREP="${INSTALL_SEMGREP:-1}"
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

curl_with_worker_token() {
  if [ -n "$CODECOME_WORKER_REGISTRATION_TOKEN" ]; then
    curl -fsSL -H "X-CodeCome-Worker-Token: $CODECOME_WORKER_REGISTRATION_TOKEN" "$@"
  else
    curl -fsSL "$@"
  fi
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

install_semgrep() {
  if [ "$INSTALL_SEMGREP" != "1" ]; then
    log "Skipping Semgrep install (INSTALL_SEMGREP=$INSTALL_SEMGREP)."
    return
  fi

  if need_cmd semgrep; then
    log "Semgrep already installed."
    return
  fi

  log "Installing Semgrep with pip."
  if python3 -m pip install --upgrade semgrep --break-system-packages; then
    return
  fi

  log "System pip install failed; trying user-local Semgrep install."
  python3 -m pip install --user --upgrade semgrep
  if [ -x /root/.local/bin/semgrep ] && [ ! -e /usr/local/bin/semgrep ]; then
    ln -s /root/.local/bin/semgrep /usr/local/bin/semgrep
  fi
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

prepare_ssh_access() {
  if [ "$CODECOME_GENERATE_SSH_KEY" != "1" ]; then
    log "Skipping worker SSH key generation (CODECOME_GENERATE_SSH_KEY=$CODECOME_GENERATE_SSH_KEY)."
    return
  fi

  local user_home
  user_home="$(getent passwd "$CODECOME_WORKER_USER" | cut -d: -f6)"
  local ssh_dir="$user_home/.ssh"
  local key_path="$ssh_dir/codecome_worker_ed25519"
  local authorized_keys="$ssh_dir/authorized_keys"

  mkdir -p "$ssh_dir"
  chown "$CODECOME_WORKER_USER:$CODECOME_WORKER_USER" "$ssh_dir"
  chmod 700 "$ssh_dir"

  if [ ! -f "$key_path" ]; then
    log "Generating SSH key for CodeCome Web to reach this worker."
    sudo -u "$CODECOME_WORKER_USER" ssh-keygen -t ed25519 -N '' -f "$key_path" -C "codecome-worker-$CODECOME_WORKER_NAME" >/dev/null
  fi

  touch "$authorized_keys"
  if ! grep -qxF "$(cat "$key_path.pub")" "$authorized_keys"; then
    cat "$key_path.pub" >> "$authorized_keys"
  fi
  chown "$CODECOME_WORKER_USER:$CODECOME_WORKER_USER" "$authorized_keys"
  chmod 600 "$authorized_keys"
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
    curl_with_worker_token "$OPENCODE_CONFIG_URL" -o "$config_path"
  elif [ -n "$CODECOME_WEB_URL" ]; then
    local web_url="${CODECOME_WEB_URL%/}"
    log "Pulling OpenCode config from CodeCome Web: $web_url"
    if ! curl_with_worker_token "$web_url/api/workers/opencode-config/raw" -o "$config_path"; then
      log "No OpenCode config available from CodeCome Web. Leaving $config_path untouched."
      rm -f "$config_path"
    fi
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
  $(check_command semgrep_cli 'Semgrep CLI' false semgrep --version),
  $(check_command codeql_cli 'CodeQL CLI' false codeql --version),
  $(check_command asciinema 'asciinema' false asciinema --version),
  $(check_command agg 'agg' false agg --version),
  $(check_command ffmpeg 'ffmpeg' false ffmpeg -version),
  $xvfb_json
]
EOF
}

collect_opencode_models() {
  local user_home
  user_home="$(getent passwd "$CODECOME_WORKER_USER" | cut -d: -f6)"
  local config_path=""
  if [ -f "$user_home/.config/opencode/opencode.jsonc" ]; then
    config_path="$user_home/.config/opencode/opencode.jsonc"
  elif [ -f "$user_home/.config/opencode/opencode.json" ]; then
    config_path="$user_home/.config/opencode/opencode.json"
  fi
  if [ -z "$config_path" ]; then
    printf '[]\n'
    return
  fi
  python3 - "$config_path" <<'PY'
import json, re, sys
path = sys.argv[1]
text = open(path, encoding='utf-8').read()
text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
text = re.sub(r'(^|\s)//.*$', '', text, flags=re.M)
try:
    data = json.loads(text)
except Exception:
    print('[]')
    raise SystemExit(0)
items = []
for provider_id, provider in (data.get('provider') or {}).items():
    models = (provider or {}).get('models') or {}
    if isinstance(models, dict):
        for model_id in models:
            items.append(f'{provider_id}/{model_id}')
    elif isinstance(models, list):
        for model_id in models:
            items.append(f'{provider_id}/{model_id}')
print(json.dumps(sorted(set(items))))
PY
}

register_with_web() {
  local host_ip
  host_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [ -z "$host_ip" ]; then
    host_ip="$(hostname -f 2>/dev/null || hostname)"
  fi

  local requirements_json
  requirements_json="$(collect_requirements | jq -c .)"
  local models_json
  models_json="$(collect_opencode_models | jq -c .)"
  mkdir -p "$CODECOME_HOME"
  printf '%s\n' "$requirements_json" > "$CODECOME_HOME/worker-requirements.json"
  chown "$CODECOME_WORKER_USER:$CODECOME_WORKER_USER" "$CODECOME_HOME/worker-requirements.json" || true

  local private_key=""
  local user_home
  user_home="$(getent passwd "$CODECOME_WORKER_USER" | cut -d: -f6)"
  local key_path="$user_home/.ssh/codecome_worker_ed25519"
  if [ -f "$key_path" ]; then
    private_key="$(cat "$key_path")"
  fi

  if [ -n "$CODECOME_WEB_URL" ] && [ "$CODECOME_REGISTER" = "1" ]; then
    local web_url="${CODECOME_WEB_URL%/}"
    local payload_path="$CODECOME_HOME/worker-registration.json"
    jq -n \
      --arg name "$CODECOME_WORKER_NAME" \
      --arg type "$CODECOME_WORKER_TYPE" \
      --arg host "$host_ip" \
      --arg username "$CODECOME_WORKER_USER" \
      --arg workspace_base_path "$CODECOME_WORKSPACE_BASE" \
      --arg codecome_home "$CODECOME_HOME" \
      --arg private_key "$private_key" \
      --argjson port 22 \
      --argjson max_concurrent_jobs "$CODECOME_MAX_CONCURRENT_JOBS" \
      --argjson requirements "$requirements_json" \
      --argjson opencode_models "$models_json" \
      '{name: $name, type: $type, host: $host, port: $port, username: $username, workspace_base_path: $workspace_base_path, max_concurrent_jobs: $max_concurrent_jobs, capabilities: {docker: true, codecome: true}, requirements: $requirements, opencode_models: $opencode_models, config: ({codecome_home: $codecome_home} + (if $private_key != "" then {ssh_auth: {method: "key", private_key: $private_key}} else {} end))}' > "$payload_path"
    log "Registering worker with CodeCome Web: $web_url"
    curl_with_worker_token -X POST "$web_url/api/workers/register" -H 'Content-Type: application/json' --data-binary "@$payload_path" >/dev/null
    chown "$CODECOME_WORKER_USER:$CODECOME_WORKER_USER" "$payload_path" || true
    chmod 600 "$payload_path" || true
  fi

  cat <<EOF

Bootstrap complete.

Worker metadata was written to:
  $CODECOME_HOME/worker-requirements.json

If automatic registration was not enabled, register this worker in CodeCome Web:

curl -X POST http://<CODECOME_WEB_HOST>:8000/api/workers/ \\
  -H 'Content-Type: application/json' \\
  -d '{
    "name": "$CODECOME_WORKER_NAME",
    "type": "$CODECOME_WORKER_TYPE",
    "host": "$host_ip",
    "port": 22,
    "username": "$CODECOME_WORKER_USER",
    "workspace_base_path": "$CODECOME_WORKSPACE_BASE",
    "max_concurrent_jobs": $CODECOME_MAX_CONCURRENT_JOBS,
    "capabilities": {"docker": true, "codecome": true},
    "config": {"codecome_home": "$CODECOME_HOME", "requirements": $requirements_json}
  }'

Important:
- Set CODECOME_WEB_URL and CODECOME_WORKER_REGISTRATION_TOKEN to auto-register on future runs.
- If this is an LXC and Docker must run inside it, Proxmox nesting/privileged settings may be required.
- VMs are recommended for untrusted targets.
EOF
}

main() {
  log "Installing packages."
  install_packages
  log "Installing Docker runtime."
  install_docker
  log "Installing Semgrep static analysis CLI."
  install_semgrep
  log "Creating worker user."
  create_worker_user
  log "Preparing directories."
  prepare_directories
  log "Preparing SSH access."
  prepare_ssh_access
  log "Installing OpenCode config if provided."
  install_opencode_config
  log "Installing CodeCome repo if provided."
  install_codecome_repo
  write_profile
  register_with_web
}

main "$@"
