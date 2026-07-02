# CodeCome Web Application

Web interface for CodeCome vulnerability research platform.

**Deployment:** Databases in Docker (PostgreSQL + Redis), app runs natively.
CodeCome CLI also runs natively (needs host Docker for sandbox POCs).

## Architecture

```
┌───────────────── NATIVE ─────────────────┐
│  React (3000) ──→ FastAPI (8000)         │
│                 ↓ Celery Worker           │
│                 ↓ make phase-X (CodeCome) │
└───────────────────────────────────────────┘

┌───────────────── DOCKER ─────────────────┐
│  PostgreSQL (15432→5432)                 │
│  Redis (6379→6379)                       │
└───────────────────────────────────────────┘
```

## Worker Model

The web app is a control plane. Audits are assigned to workers/runners.

Supported worker records:

- `local`: runs CodeCome on the same host as the web backend.
- `ssh`: planned remote physical/VM worker over SSH.
- `proxmox-vm`: planned Proxmox VM worker.
- `proxmox-lxc`: planned Proxmox LXC worker.

Current implementation:

- Registers a built-in `local` worker automatically via `/api/workers/`.
- Lets audits choose a worker or auto-select one.
- Stores assigned worker on the audit and each phase execution.
- Tracks worker capacity with `current_jobs` and `max_concurrent_jobs`.

Next adapter to implement is SSH execution, then Proxmox provisioning.

Worker API:

```bash
curl http://localhost:8000/api/workers/
curl -X POST http://localhost:8000/api/workers/ \
  -H 'Content-Type: application/json' \
  -d '{"name":"runner-01","type":"ssh","host":"10.0.0.20","username":"codecome","workspace_base_path":"/opt/codecome-workspaces"}'
```

## Proxmox / Remote Worker Bootstrap

Create a Proxmox VM first for safest isolation. LXC can work, but Docker inside LXC often requires `nesting=1` and privileged container settings.

On the worker VM/LXC/physical machine:

```bash
curl -fsSL http://<CODECOME_WEB_HOST>:8000/api/workers/bootstrap-script -o worker-bootstrap.sh
sudo bash worker-bootstrap.sh
```

Recommended with explicit values:

```bash
sudo CODECOME_WORKER_NAME=runner-01 \
  CODECOME_WORKSPACE_BASE=/srv/codecome/workspaces \
  CODECOME_HOME=/srv/codecome \
  bash worker-bootstrap.sh
```

If your OpenCode custom providers/config are hosted somewhere reachable:

```bash
sudo OPENCODE_CONFIG_URL=http://<CODECOME_WEB_HOST>:8000/static/opencode.jsonc \
  bash worker-bootstrap.sh
```

If you prefer to pass the config directly:

```bash
export OPENCODE_CONFIG_B64="$(base64 -w0 ~/.config/opencode/opencode.jsonc)"
sudo OPENCODE_CONFIG_B64="$OPENCODE_CONFIG_B64" bash worker-bootstrap.sh
```

The script installs dependencies, Docker, creates the `codecome` user, creates the workspace folder, installs the OpenCode config if provided, and prints a `curl` command to register the worker in the web app.

After bootstrap, add the web host SSH public key to the worker:

```bash
sudo -u codecome mkdir -p /home/codecome/.ssh
sudo tee -a /home/codecome/.ssh/authorized_keys < web-host-id.pub
sudo chown -R codecome:codecome /home/codecome/.ssh
sudo chmod 700 /home/codecome/.ssh
sudo chmod 600 /home/codecome/.ssh/authorized_keys
```

Remote SSH execution is implemented for SSH/Proxmox VM/LXC worker records. The web app uploads the workspace, launches detached remote jobs for long phases, polls for completion, and syncs `itemdb/` and `runs/` back.

## Quick Start

```bash
cd web_app

# 1. Start databases (PostgreSQL + Redis in Docker)
docker compose up -d

# 2. Start all services (backend + Celery + frontend)
./start-services.sh
```

- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

## Server Install

For a clean Ubuntu/Debian server install, see:

```text
web_app/docs/install-server.md
```

The helper script is:

```bash
cd web_app
./scripts/install-server.sh
```

## Stopping

```bash
# Stop services
pkill -f uvicorn
pkill -f celery
pkill -f vite

# Stop databases
docker compose down
```

## Ports

| Service     | Port  |
|-------------|-------|
| Frontend    | 3000  |
| Backend     | 8000  |
| PostgreSQL  | 15432 |
| Redis       | 6379  |

## Prerequisites

- **Docker** (for PostgreSQL + Redis databases)
- **Python** 3.12+ (for backend)
- **Node.js** 20+ (for frontend)
- **Docker** (also required by CodeCome CLI for sandbox POCs)

## Development Checks

Run all local web-app checks before committing web changes:

```bash
cd web_app
./run-checks.sh
```

This runs:

- backend unit tests
- backend Python compile check
- frontend Vitest tests
- frontend production build

Focused commands:

```bash
cd web_app/backend
venv/bin/python3 -m pytest -q tests
venv/bin/python3 -m compileall -q app

cd ../frontend
npm test
npm run build
```

## License

GPL-3.0-or-later OR AGPL-3.0-or-later
