#!/bin/bash
# Start CodeCome Web services
set -e

cd "$(dirname "$0")"

BACKEND_DIR="./backend"
FRONTEND_DIR="./frontend"
BACKEND_LOG="./logs/backend.log"
CELERY_LOG="./logs/celery.log"
FRONTEND_LOG="./logs/frontend.log"
PID_FILE_BACKEND="./logs/backend.pid"
PID_FILE_CELERY="./logs/celery.pid"
PID_FILE_FRONTEND="./logs/frontend.pid"

mkdir -p ./logs

echo "=== CodeCome Web Application ==="
echo ""

# Check prerequisites
echo "[*] Checking prerequisites..."
if ! pg_isready -q 2>/dev/null; then
    echo "[!] PostgreSQL is not running. Start it first:"
    echo "    sudo systemctl start postgresql"
    exit 1
fi

if ! redis-cli ping > /dev/null 2>&1; then
    echo "[!] Redis is not running. Start it first:"
    echo "    sudo systemctl start redis-server"
    echo "    OR: docker run -d --name redis -p 6379:6379 redis:7-alpine"
    exit 1
fi

echo "[+] PostgreSQL: OK"
echo "[+] Redis: OK"
echo ""

# Setup backend venv if needed
if [ ! -d "$BACKEND_DIR/venv" ]; then
    echo "[*] Creating Python virtual environment..."
    cd "$BACKEND_DIR"
    python3 -m venv venv
    source venv/bin/activate
    pip install -q -r requirements.txt
    echo "[+] Virtual environment created"
    cd ..
fi

# Check .env
if [ ! -f "$BACKEND_DIR/.env" ]; then
    echo "[*] Creating .env from example..."
    cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
    echo "[+] .env created (edit it if needed)"
fi

echo "[*] Starting services..."
echo ""

# Start backend
echo "[*] Starting backend (FastAPI) on port 8000..."
$BACKEND_DIR/venv/bin/python3 -m uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 \
    --app-dir . \
    > "$BACKEND_LOG" 2>&1 &
echo $! > "$PID_FILE_BACKEND"
sleep 2

if kill -0 $(cat "$PID_FILE_BACKEND") 2>/dev/null; then
    echo "[+] Backend started (PID: $(cat $PID_FILE_BACKEND))"
else
    echo "[!] Backend failed to start. Check $BACKEND_LOG"
    cat "$BACKEND_LOG"
    exit 1
fi

# Start Celery worker
echo "[*] Starting Celery worker..."
$BACKEND_DIR/venv/bin/celery -A app.workers.celery_app worker \
    --loglevel=info \
    --logfile="$CELERY_LOG" &
echo $! > "$PID_FILE_CELERY"
sleep 2

if kill -0 $(cat "$PID_FILE_CELERY") 2>/dev/null; then
    echo "[+] Celery started (PID: $(cat $PID_FILE_CELERY))"
else
    echo "[!] Celery failed to start. Check $CELERY_LOG"
    cat "$CELERY_LOG"
    exit 1
fi

# Start frontend
if [ -f "$FRONTEND_DIR/package.json" ]; then
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        echo "[*] Installing frontend dependencies..."
        cd "$FRONTEND_DIR" && npm install --silent && cd ..
        echo "[+] Frontend dependencies installed"
    fi

    echo "[*] Starting frontend (Vite) on port 3000..."
    cd "$FRONTEND_DIR" && npm run dev > "../$FRONTEND_LOG" 2>&1 &
    echo $! > "../$PID_FILE_FRONTEND"
    cd ..
    sleep 3

    if kill -0 $(cat "$PID_FILE_FRONTEND") 2>/dev/null; then
        echo "[+] Frontend started (PID: $(cat $PID_FILE_FRONTEND))"
    else
        echo "[!] Frontend failed to start. Check $FRONTEND_LOG"
    fi
fi

echo ""
echo "=== Services Running ==="
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo "API Docs: http://localhost:8000/docs"
echo ""
echo "Logs:"
echo "  Backend:  $BACKEND_LOG"
echo "  Celery:   $CELERY_LOG"
echo "  Frontend: $FRONTEND_LOG"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for any process to exit
wait
