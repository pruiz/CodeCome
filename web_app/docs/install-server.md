# Install CodeCome Web On A Server

This guide installs the CodeCome Web control plane on an Ubuntu/Debian server.

## What Runs Where

- PostgreSQL and Redis run in Docker.
- FastAPI backend, Celery worker, React/Vite frontend, CodeCome CLI, and optional `code-server` run natively on the server.
- Audit worker phases run on the selected worker. A local worker is the same server; SSH workers run remotely.

## Ports

- Frontend: `3000`
- Backend/API: `8000`
- PostgreSQL container mapping: `15432`
- Redis: `6379`
- VS Code/code-server: random per audit session port

Open/firewall only what you need. For LAN code-server access, expose the random code-server ports only on trusted networks.

## Quick Install

Copy the project to the server, then run:

```bash
cd /path/to/CodeCome_WEB/web_app
./scripts/install-server.sh
./start-services.sh
```

If the web server should expose code-server to other machines on your LAN:

```bash
cd /path/to/CodeCome_WEB/web_app
CODE_SERVER_BIND_ADDR=0.0.0.0 \
CODE_SERVER_PUBLIC_BASE_URL=http://SERVER_IP_OR_DNS \
  ./scripts/install-server.sh
```

You can also configure these later in the web UI under `Config`.

## Manual Install Steps

Install packages:

```bash
sudo apt-get update
sudo apt-get install -y \
  ca-certificates curl docker.io docker-compose-v2 git jq make \
  nodejs npm python3 python3-pip python3-venv rsync unzip
```

Optional tools:

```bash
curl -fsSL https://code-server.dev/install.sh | sh
python3 -m pip install --user --upgrade semgrep
```

Create backend virtualenv:

```bash
cd /path/to/CodeCome_WEB/web_app/backend
python3 -m venv venv
venv/bin/python3 -m pip install --upgrade pip
venv/bin/python3 -m pip install -r requirements.txt
```

Install frontend packages:

```bash
cd /path/to/CodeCome_WEB/web_app/frontend
npm install
```

Create `.env`:

```bash
cd /path/to/CodeCome_WEB/web_app/backend
cp .env.example .env
```

Edit at least:

```env
WORKSPACES_DIR=/path/to/CodeCome_WEB/workspaces
CODECOME_ROOT=/path/to/CodeCome_WEB
SECRET_KEY=replace-with-a-random-secret
```

For code-server LAN access:

```env
CODE_SERVER_BIND_ADDR=0.0.0.0
CODE_SERVER_PUBLIC_BASE_URL=http://SERVER_IP_OR_DNS
```

Start databases and services:

```bash
cd /path/to/CodeCome_WEB/web_app
docker compose up -d
./start-services.sh
```

## First Login

Open:

```text
http://SERVER_IP_OR_DNS:3000
```

If no human user exists, the UI will show first-user bootstrap.

## Code-Server Configuration

In the web UI, open `Config`.

- `Bind address`: `127.0.0.1` for browser on same server, `0.0.0.0` for LAN access.
- `Public base URL`: server URL without port, for example `http://192.168.20.18`.

Existing VS Code sessions should be stopped and restarted after changing these settings.

## Semgrep

Phase 1 Semgrep enrichment needs `semgrep` on the worker where the enrichment phase runs.

- For local-worker server installs, install Semgrep on the web server.
- For SSH workers, use the worker bootstrap script; it installs and reports Semgrep.

## Remote Workers

From the worker machine:

```bash
curl -fsSL http://SERVER_IP_OR_DNS:8000/api/workers/bootstrap-script -o worker-bootstrap.sh
sudo CODECOME_WEB_URL=http://SERVER_IP_OR_DNS:8000 bash worker-bootstrap.sh
```

If worker registration tokens are enabled, include `CODECOME_WORKER_REGISTRATION_TOKEN`.

## Stop Services

```bash
cd /path/to/CodeCome_WEB/web_app
./stop.sh
docker compose down
```

## Local Checks

```bash
cd /path/to/CodeCome_WEB/web_app
./run-checks.sh
```
