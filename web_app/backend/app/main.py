from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime
import logging
import os
from sqlalchemy import text

from app.database import engine, Base
from app.api import audits, phases, findings, logs, preview, websockets, workers, users, questions, auth
from app.auth import verify_access_token
from app.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.DEBUG else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def ensure_runtime_schema():
    """Apply lightweight schema additions when running without Alembic."""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE audits ADD COLUMN IF NOT EXISTS assigned_worker_id INTEGER"))
        conn.execute(text("ALTER TABLE audits ADD COLUMN IF NOT EXISTS question_owner_user_id INTEGER"))
        conn.execute(text("ALTER TABLE phase_executions ADD COLUMN IF NOT EXISTS worker_id INTEGER"))
        conn.execute(text("ALTER TABLE phase_executions ADD COLUMN IF NOT EXISTS command_line TEXT"))
        conn.execute(text("ALTER TABLE phase_executions ADD COLUMN IF NOT EXISTS remote_job_dir TEXT"))
        conn.execute(text("ALTER TABLE phase_executions ADD COLUMN IF NOT EXISTS remote_pid VARCHAR(64)"))
        conn.execute(text("ALTER TABLE phase_executions ADD COLUMN IF NOT EXISTS local_pid INTEGER"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audits_worker ON audits(assigned_worker_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audits_question_owner ON audits(question_owner_user_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_phase_executions_worker ON phase_executions(worker_id)"))


def enqueue_remote_recoveries():
    from app.database import SessionLocal
    from app.models import PhaseExecution, Worker
    from app.workers.phase_tasks import recover_remote_phase_task

    db = SessionLocal()
    try:
        rows = db.query(PhaseExecution).join(Worker, PhaseExecution.worker_id == Worker.id).filter(
            PhaseExecution.status == "running",
            PhaseExecution.remote_job_dir.isnot(None),
            Worker.type.in_(["ssh", "proxmox-vm", "proxmox-lxc"]),
        ).all()
        for row in rows:
            recover_remote_phase_task.delay(row.id)
            logger.info("Queued recovery for remote phase execution %s", row.id)
    finally:
        db.close()


def _pid_is_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _status_phase(phase: str) -> str:
    return phase.replace("-", "_").replace(" ", "_")


def reconcile_stale_local_phases():
    from app import crud
    from app.database import SessionLocal
    from app.models import Audit, PhaseExecution

    db = SessionLocal()
    try:
        rows = db.query(PhaseExecution).filter(
            PhaseExecution.status == "running",
            PhaseExecution.remote_job_dir.is_(None),
        ).all()
        for row in rows:
            if _pid_is_running(row.local_pid):
                continue
            message = "Marked failed during startup reconciliation because the recorded local process is no longer running."
            crud.update_phase_execution(db, row.id, {
                "status": "failed",
                "completed_at": datetime.now(),
                "exit_code": row.exit_code if row.exit_code is not None else -1,
                "error_message": message,
            })
            audit = db.query(Audit).filter(Audit.id == row.audit_id).first()
            if audit and audit.status == f"{_status_phase(row.phase)}_running":
                crud.update_audit_status(db, audit.id, f"{_status_phase(row.phase)}_failed")
            if row.worker_id:
                crud.mark_worker_job_finished(db, row.worker_id)
            crud.create_audit_log(db, str(row.audit_id), "WARN", message, phase=row.phase, source="system")
            logger.warning("Reconciled stale local phase execution %s", row.id)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
    reconcile_stale_local_phases()
    enqueue_remote_recoveries()
    logger.info("Database tables created")
    yield
    # Shutdown
    logger.info("Shutting down")


app = FastAPI(
    title="CodeCome Web API",
    description="API for CodeCome vulnerability research platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_api_auth(request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or path in ("/", "/health"):
        return await call_next(request)
    if not path.startswith("/api/"):
        return await call_next(request)
    if path in ("/api/auth/login", "/api/auth/bootstrap", "/api/auth/status"):
        return await call_next(request)
    auth_header = request.headers.get("authorization") or ""
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return JSONResponse(status_code=401, content={"detail": "Missing bearer token"})
    try:
        verify_access_token(token)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)

# Include routers
app.include_router(audits.router, prefix="/api/audits", tags=["audits"])
app.include_router(phases.router, prefix="/api/phases", tags=["phases"])
app.include_router(findings.router, prefix="/api/findings", tags=["findings"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
app.include_router(workers.router, prefix="/api/workers", tags=["workers"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(questions.router, prefix="/api/questions", tags=["questions"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(preview.router, prefix="/api/preview", tags=["preview"])
app.include_router(websockets.router, prefix="/ws", tags=["websockets"])


@app.get("/")
def root():
    return {"message": "CodeCome Web API", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "ok"}


# Exception handlers
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )
