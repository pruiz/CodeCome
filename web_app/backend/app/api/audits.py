from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional, List
from uuid import UUID
from pathlib import Path
from fastapi.responses import FileResponse, StreamingResponse
import io
from datetime import datetime

from app.database import get_db
from app import crud, models, schemas
from app.services.workspace import workspace_manager
from app.workers.phase_tasks import ALL_PHASES, PHASE_ORDER, merged_phase_env, phase_order_for_settings, run_phase_task, run_sequential_workflow
from app.workers.question_answering import write_user_answers_context, with_user_answers_env
from app.utils.codecome_wrapper import CodeComeExecutor, codecome_executor
from app.utils.ssh_executor import SSHCodeComeExecutor
from app.config import settings
import shutil
import zipfile

router = APIRouter()


def next_audit_step(phase_executions, model_settings: dict | None = None) -> str:
    by_phase = {execution.phase: execution for execution in phase_executions}
    legacy_aliases = {
        "make validate-all": "phase-4",
        "make exploit-all": "phase-5",
    }
    for phase in phase_order_for_settings(model_settings):
        execution = by_phase.get(phase)
        if not execution and phase in legacy_aliases:
            execution = by_phase.get(legacy_aliases[phase])
        if not execution:
            return phase
        if execution.status in ("failed", "cancelled"):
            return phase
        if execution.status == "running":
            return phase
    return "phase-6"


def queue_audit_phase(db: Session, audit, phase: str):
    if phase not in ALL_PHASES:
        raise HTTPException(status_code=400, detail="Unsupported phase")
    if "running" in audit.status:
        raise HTTPException(status_code=409, detail="Audit is already running")

    worker = crud.select_available_worker(db, audit.assigned_worker_id)
    if not worker:
        raise HTTPException(status_code=409, detail="No available worker")
    audit.assigned_worker_id = worker.id

    model_settings = audit.model_settings or {}
    phase_config = model_settings.get(phase, {})
    model = phase_config.get("model")
    variant = phase_config.get("variant")
    env_overrides = with_user_answers_env(Path(audit.workspace_path), merged_phase_env(model_settings, phase))

    audit.current_phase = phase
    db.commit()
    run_phase_task.delay(str(audit.id), phase, model, variant, None, 1, worker.id, env_overrides)
    return worker


@router.post("/", response_model=schemas.AuditResponse, status_code=201)
def create_audit(audit_data: schemas.AuditCreate, db: Session = Depends(get_db)):
    """Create a new audit from source code."""
    from uuid import uuid4
    
    audit_id = uuid4()
    workspace_path = workspace_manager.create_workspace(str(audit_id))
    
    # Setup source code
    success = False
    if audit_data.source_type == "git":
        success = workspace_manager.setup_source_from_git(workspace_path, audit_data.source_location)
    elif audit_data.source_type == "zip":
        success = workspace_manager.setup_source_from_zip(workspace_path, audit_data.source_location)
    elif audit_data.source_type == "local":
        # For local type, check if it's a ZIP file first
        import os
        if audit_data.source_location.endswith('.zip'):
            success = workspace_manager.setup_source_from_zip(workspace_path, audit_data.source_location)
        else:
            success = workspace_manager.setup_source_from_local(workspace_path, audit_data.source_location)
    
    if not success:
        workspace_manager.cleanup_workspace(workspace_path)
        raise HTTPException(status_code=400, detail="Failed to setup source code")
    
    # Write codecome.yml
    yml_content = audit_data.codecome_yml
    if not yml_content:
        # Use default from CodeCome root
        default_yml = settings.CODECOME_ROOT / "codecome.yml"
        if default_yml.exists():
            yml_content = default_yml.read_text()
        else:
            yml_content = f"project:\n  name: \"{audit_data.name}\"\n  source_path: \"./src\"\n"
    
    workspace_manager.write_codecome_yml(workspace_path, yml_content)
    
    # Create audit record
    worker = crud.get_worker(db, audit_data.worker_id) if audit_data.worker_id else None
    if audit_data.worker_id and not worker:
        workspace_manager.cleanup_workspace(workspace_path)
        raise HTTPException(status_code=404, detail="Worker not found")
    if audit_data.question_owner_user_id and not crud.get_user(db, audit_data.question_owner_user_id):
        workspace_manager.cleanup_workspace(workspace_path)
        raise HTTPException(status_code=404, detail="Question owner user not found")

    db_audit = crud.create_audit(db, schemas.AuditCreate(
        name=audit_data.name,
        source_type=audit_data.source_type,
        source_location=audit_data.source_location,
        codecome_yml=yml_content,
        model_settings=audit_data.model_settings,
        ai_review_enabled=audit_data.ai_review_enabled,
        auto_continue=audit_data.auto_continue,
        worker_id=audit_data.worker_id,
        question_owner_user_id=audit_data.question_owner_user_id,
        workspace_path=str(workspace_path),
    ))
    
    return db_audit


@router.get("/", response_model=schemas.AuditListResponse)
def list_audits(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """List all audits with pagination and status filtering."""
    total, audits = crud.get_audits(db, skip, limit, status)
    return schemas.AuditListResponse(total=total, audits=audits)


@router.get("/{audit_id}", response_model=schemas.AuditResponse)
def get_audit(audit_id: UUID, db: Session = Depends(get_db)):
    """Get audit details including phase executions."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    phase_execs = crud.get_phase_executions(db, audit_id)
    
    return schemas.AuditResponse(
        id=audit.id,
        name=audit.name,
        status=audit.status,
        current_phase=audit.current_phase,
        assigned_worker_id=audit.assigned_worker_id,
        question_owner_user_id=audit.question_owner_user_id,
        workspace_path=audit.workspace_path,
        source_type=audit.source_type,
        source_location=audit.source_location,
        has_codecome_yml=bool(audit.codecome_yml),
        codecome_yml=audit.codecome_yml,
        model_settings=audit.model_settings or {},
        ai_review_enabled=audit.ai_review_enabled,
        auto_continue=audit.auto_continue,
        total_findings=audit.total_findings,
        findings_by_status=audit.findings_by_status or {},
        created_at=audit.created_at,
        updated_at=audit.updated_at,
        phase_executions=phase_execs
    )


@router.patch("/{audit_id}", response_model=schemas.AuditResponse)
def update_audit(audit_id: UUID, audit_data: schemas.AuditUpdate, db: Session = Depends(get_db)):
    """Update audit configuration."""
    update_payload = audit_data.model_dump(exclude_unset=True)
    if update_payload.get("question_owner_user_id") and not crud.get_user(db, update_payload["question_owner_user_id"]):
        raise HTTPException(status_code=404, detail="Question owner user not found")
    audit = crud.update_audit(db, audit_id, audit_data)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    return audit


@router.delete("/{audit_id}", status_code=204)
def delete_audit(audit_id: UUID, db: Session = Depends(get_db)):
    """Delete audit and its workspace."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    
    # Cleanup workspace
    workspace_manager.cleanup_workspace(Path(audit.workspace_path))
    
    # Delete from database
    crud.delete_audit(db, audit_id)


@router.post("/{audit_id}/start")
def start_audit(audit_id: UUID, db: Session = Depends(get_db)):
    """Start or resume audit workflow."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    if crud.audit_has_open_blocking_questions(db, audit_id):
        raise HTTPException(status_code=409, detail="Audit has open blocking questions")

    phase_executions = crud.get_phase_executions(db, audit_id)
    starting_phase = next_audit_step(phase_executions, audit.model_settings)
    worker = queue_audit_phase(db, audit, starting_phase)
    
    return {
        "audit_id": str(audit_id),
        "status": f"{starting_phase.replace('-', '_')}_running",
        "worker_id": worker.id,
        "worker_name": worker.name,
        "message": "Audit workflow started",
    }


@router.post("/{audit_id}/run-phase")
def run_audit_phase(audit_id: UUID, phase: str = Query(...), db: Session = Depends(get_db)):
    """Run a specific phase, including optional phases such as make sweep."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    if crud.audit_has_open_blocking_questions(db, audit_id):
        raise HTTPException(status_code=409, detail="Audit has open blocking questions")
    worker = queue_audit_phase(db, audit, phase)
    return {
        "audit_id": str(audit_id),
        "status": f"{phase.replace('-', '_').replace(' ', '_')}_running",
        "phase": phase,
        "worker_id": worker.id,
        "worker_name": worker.name,
        "message": "Audit phase queued",
    }


@router.post("/{audit_id}/continue-after-questions")
def continue_after_questions(audit_id: UUID, db: Session = Depends(get_db)):
    """Continue an audit once all blocking questions are answered or dismissed."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    if crud.audit_has_open_blocking_questions(db, audit_id):
        raise HTTPException(status_code=409, detail="Audit has open blocking questions")
    write_user_answers_context(db, audit, Path(audit.workspace_path))
    phase_executions = crud.get_phase_executions(db, audit_id)
    starting_phase = next_audit_step(phase_executions, audit.model_settings)
    worker = queue_audit_phase(db, audit, starting_phase)
    return {
        "audit_id": str(audit_id),
        "phase": starting_phase,
        "worker_id": worker.id,
        "worker_name": worker.name,
        "message": "Audit continued after questions",
    }


@router.post("/{audit_id}/pause")
def pause_audit(audit_id: UUID, db: Session = Depends(get_db)):
    """Pause audit workflow after current phase."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    running_execution = db.query(models.PhaseExecution).filter(
        models.PhaseExecution.audit_id == audit_id,
        models.PhaseExecution.status == "running",
    ).order_by(models.PhaseExecution.started_at.desc()).first()

    if running_execution:
        worker = crud.get_worker(db, running_execution.worker_id) if running_execution.worker_id else None
        if worker and worker.type == "local" and running_execution.local_pid:
            try:
                CodeComeExecutor.terminate_process_group(running_execution.local_pid)
                crud.create_audit_log(db, audit_id, "WARN", f"Sent SIGTERM to local process group {running_execution.local_pid}", phase=running_execution.phase, source="system")
            except ProcessLookupError:
                crud.create_audit_log(db, audit_id, "WARN", f"Local process {running_execution.local_pid} was already gone", phase=running_execution.phase, source="system")
            except Exception as exc:
                crud.create_audit_log(db, audit_id, "ERROR", f"Failed to stop local process {running_execution.local_pid}: {exc}", phase=running_execution.phase, source="system")
        elif worker and worker.type in ("ssh", "proxmox-vm", "proxmox-lxc") and running_execution.remote_pid:
            try:
                SSHCodeComeExecutor(worker).cancel_remote_pid(running_execution.remote_pid)
                crud.create_audit_log(db, audit_id, "WARN", f"Sent SIGTERM to remote process {running_execution.remote_pid}", phase=running_execution.phase, source="system")
            except Exception as exc:
                crud.create_audit_log(db, audit_id, "ERROR", f"Failed to stop remote process {running_execution.remote_pid}: {exc}", phase=running_execution.phase, source="system")

        crud.update_phase_execution(db, running_execution.id, {
            "status": "cancelled",
            "completed_at": datetime.now(),
            "error_message": "Cancelled by user pause request",
        })

    crud.update_audit_status(db, audit_id, "paused")

    return {
        "audit_id": str(audit_id),
        "status": "paused",
        "cancelled_execution_id": running_execution.id if running_execution else None,
        "message": "Audit paused",
    }


@router.post("/upload-zip", response_model=schemas.AuditResponse)
async def upload_zip(
    name: str,
    file: UploadFile = File(...),
    codecome_yml: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Upload ZIP file and create audit."""
    from uuid import uuid4
    
    # Save uploaded file
    temp_dir = settings.WORKSPACES_DIR / "uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = temp_dir / f"{uuid4().hex}_{file.filename}"
    
    content = await file.read()
    file_path.write_bytes(content)
    
    # Create workspace
    audit_id = uuid4()
    workspace_path = workspace_manager.create_workspace(str(audit_id))
    
    # Extract source
    success = workspace_manager.setup_source_from_zip(workspace_path, str(file_path))
    
    # Cleanup uploaded file
    file_path.unlink(missing_ok=True)
    
    if not success:
        workspace_manager.cleanup_workspace(workspace_path)
        raise HTTPException(status_code=400, detail="Failed to extract ZIP file")
    
    # Write codecome.yml
    yml_content = codecome_yml
    if not yml_content:
        default_yml = settings.CODECOME_ROOT / "codecome.yml"
        if default_yml.exists():
            yml_content = default_yml.read_text()
    
    workspace_manager.write_codecome_yml(workspace_path, yml_content)
    
    # Create audit record
    db_audit = crud.create_audit(db, schemas.AuditCreate(
        name=name,
        source_type="zip",
        source_location=file.filename,
        codecome_yml=yml_content,
        workspace_path=str(workspace_path),
    ))
    
    return db_audit
