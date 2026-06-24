#!/bin/bash
# Stop CodeCome Web services

cd "$(dirname "$0")"
LOGS_DIR="./logs"

echo "=== Stopping CodeCome Web Services ==="
echo ""

# Stop background processes
for PID_FILE in $LOGS_DIR/*.pid; do
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        SERVICE=$(basename "$PID_FILE" .pid)
        if kill -0 "$PID" 2>/dev/null; then
            echo "Stopping $SERVICE (PID: $PID)..."
            kill "$PID" 2>/dev/null
            # Wait a moment
            sleep 1
            # Force kill if still running
            if kill -0 "$PID" 2>/dev/null; then
                kill -9 "$PID" 2>/dev/null
            fi
            echo "  [$SERVICE] Stopped"
        else
            echo "  [$SERVICE] Already stopped"
        fi
        rm -f "$PID_FILE"
    fi
done

# Also kill any remaining processes from this script
pkill -f "uvicorn app.main:app" 2>/dev/null && echo "[*] Killed remaining uvicorn processes"
pkill -f "python3 -m uvicorn app.main:app" 2>/dev/null && echo "[*] Killed remaining python uvicorn processes"
pkill -f "celery -A app.workers.celery_app" 2>/dev/null && echo "[*] Killed remaining celery processes"
pkill -f "npm run dev" 2>/dev/null && echo "[*] Killed remaining frontend processes"
pkill -f "node .*vite" 2>/dev/null && echo "[*] Killed remaining vite processes"

echo ""
echo "All services stopped."
