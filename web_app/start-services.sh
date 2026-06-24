#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
LOG_DIR="$ROOT_DIR/logs"

mkdir -p "$LOG_DIR"

stop_matching() {
  local pattern="$1"
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    pkill -f "$pattern" || true
    sleep 1
  fi
}

echo "Stopping stale web processes..."
stop_matching "uvicorn app.main:app"
stop_matching "python3 -m uvicorn app.main:app"
stop_matching "celery -A app.workers.celery_app"
stop_matching "node .*vite"
stop_matching "sh -c vite"

echo "Checking Docker databases..."
docker compose -f "$ROOT_DIR/docker-compose.yml" up -d >/dev/null

echo "Starting backend..."
cd "$BACKEND_DIR"
nohup "$BACKEND_DIR/venv/bin/python3" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > "$LOG_DIR/backend.log" 2>&1 &
echo $! > "$LOG_DIR/backend.pid"

echo "Starting Celery worker..."
nohup "$BACKEND_DIR/venv/bin/celery" -A app.workers.celery_app worker --loglevel=info --concurrency=2 > "$LOG_DIR/celery.log" 2>&1 &
echo $! > "$LOG_DIR/celery.pid"

echo "Starting frontend..."
cd "$FRONTEND_DIR"
nohup npm run dev -- --host 0.0.0.0 > "$LOG_DIR/frontend.log" 2>&1 &
echo $! > "$LOG_DIR/frontend.pid"

echo "Status:"
backend_ready=0
for attempt in $(seq 1 30); do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    backend_ready=1
    break
  fi
  if ! kill -0 "$(cat "$LOG_DIR/backend.pid")" 2>/dev/null; then
    break
  fi
  sleep 1
done

if [ "$backend_ready" != "1" ]; then
  echo "Backend failed. Log:"
  tail -80 "$LOG_DIR/backend.log" || true
  exit 1
fi

curl -fsS http://localhost:8000/health
echo
echo "Frontend: http://localhost:3000"
echo "Backend:  http://localhost:8000"
echo "Logs:     $LOG_DIR"
