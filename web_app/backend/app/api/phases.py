from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app import crud, schemas
from app.models import Finding, PhaseExecution, Audit
from app.workers.phase_tasks import _get_next_phase, merged_phase_env, run_phase_task, status_phase
from app.workers.ai_tasks import triage_failed_phase_task

router = APIRouter()


@router.get("/")
def list_phase_executions(
    audit_id: UUID = Query(...),
    db: Session = Depends(get_db)
):
    """List all phase executions for an audit."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    if "running" in audit.status:
        raise HTTPException(status_code=409, detail="Audit is already running")
    
    executions = crud.get_phase_executions(db, audit_id)
    
    return [{
        "id": e.id,
        "audit_id": str(e.audit_id),
        "phase": e.phase,
        "attempt": e.attempt,
        "status": e.status,
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        "duration_seconds": e.duration_seconds,
        "exit_code": e.exit_code,
        "command_line": e.command_line,
        "remote_job_dir": e.remote_job_dir,
        "remote_pid": e.remote_pid,
        "local_pid": e.local_pid,
        "model_used": e.model_used,
        "run_summary_path": e.run_summary_path
    } for e in executions]


def phase_execution_payload(e: PhaseExecution) -> dict:
    return {
        "id": e.id,
        "audit_id": str(e.audit_id),
        "worker_id": e.worker_id,
        "phase": e.phase,
        "attempt": e.attempt,
        "status": e.status,
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        "duration_seconds": e.duration_seconds,
        "exit_code": e.exit_code,
        "command_line": e.command_line,
        "remote_job_dir": e.remote_job_dir,
        "remote_pid": e.remote_pid,
        "local_pid": e.local_pid,
        "model_used": e.model_used,
        "variant_used": e.variant_used,
        "run_summary_path": e.run_summary_path,
        "stdout_log": e.stdout_log,
        "stderr_log": e.stderr_log,
        "error_message": e.error_message,
    }


def triage_payload(triage) -> dict:
    return {
        "id": triage.id,
        "audit_id": str(triage.audit_id),
        "phase_execution_id": triage.phase_execution_id,
        "phase": triage.phase,
        "status": triage.status,
        "decision": triage.decision,
        "confidence": triage.confidence,
        "reason": triage.reason,
        "recommended_env": triage.recommended_env or {},
        "evidence": triage.evidence or [],
        "raw_response": triage.raw_response,
        "report_path": triage.report_path,
        "decision_path": triage.decision_path,
        "error_message": triage.error_message,
        "applied_at": triage.applied_at.isoformat() if triage.applied_at else None,
        "created_at": triage.created_at.isoformat() if triage.created_at else None,
        "completed_at": triage.completed_at.isoformat() if triage.completed_at else None,
    }


@router.get("/{execution_id}")
def get_phase_execution(execution_id: int, db: Session = Depends(get_db)):
    """Get one phase execution including captured stdout/stderr."""
    phase_exec = db.query(PhaseExecution).filter(PhaseExecution.id == execution_id).first()
    if not phase_exec:
        raise HTTPException(status_code=404, detail="Phase execution not found")
    return phase_execution_payload(phase_exec)


@router.get("/{execution_id}/triages")
def get_phase_triages(execution_id: int, db: Session = Depends(get_db)):
    phase_exec = db.query(PhaseExecution).filter(PhaseExecution.id == execution_id).first()
    if not phase_exec:
        raise HTTPException(status_code=404, detail="Phase execution not found")
    triages = crud.get_phase_triages(db, execution_id)
    return {"phase_execution_id": execution_id, "total": len(triages), "triages": [triage_payload(item) for item in triages]}


@router.post("/{execution_id}/triage")
def run_phase_triage(execution_id: int, db: Session = Depends(get_db)):
    phase_exec = db.query(PhaseExecution).filter(PhaseExecution.id == execution_id).first()
    if not phase_exec:
        raise HTTPException(status_code=404, detail="Phase execution not found")
    if phase_exec.status == "running":
        raise HTTPException(status_code=409, detail="Cannot triage a running phase")
    triage_failed_phase_task.delay(execution_id)
    return {"message": "Failure triage queued", "phase_execution_id": execution_id}


@router.post("/triages/{triage_id}/apply")
def apply_phase_triage(
    triage_id: int,
    request: schemas.PhaseTriageApplyRequest = schemas.PhaseTriageApplyRequest(),
    db: Session = Depends(get_db),
):
    triage = crud.get_phase_triage(db, triage_id)
    if not triage:
        raise HTTPException(status_code=404, detail="Triage not found")
    if triage.status not in {"completed", "failed"}:
        raise HTTPException(status_code=409, detail="Triage is not ready to apply")

    phase_exec = db.query(PhaseExecution).filter(PhaseExecution.id == triage.phase_execution_id).first()
    audit = db.query(Audit).filter(Audit.id == triage.audit_id).first()
    if not phase_exec or not audit:
        raise HTTPException(status_code=404, detail="Related audit or phase execution not found")
    if "running" in audit.status:
        raise HTTPException(status_code=409, detail="Audit is already running")

    decision = triage.decision or "NEEDS_HUMAN"
    if decision == "NEEDS_HUMAN":
        raise HTTPException(status_code=409, detail="Triage decision requires human action and cannot be applied automatically")

    if decision == "ACCEPT_AS_COMPLETE":
        crud.update_phase_execution(db, phase_exec.id, {"status": "triaged_complete"})
        next_phase = _get_next_phase(phase_exec.phase, audit.model_settings)
        if audit.auto_continue and next_phase:
            crud.update_audit_status(db, audit.id, f"{status_phase(phase_exec.phase)}_complete")
            audit.current_phase = next_phase
            db.commit()
            next_env = merged_phase_env(audit.model_settings, next_phase)
            worker = crud.select_available_worker(db, audit.assigned_worker_id)
            if not worker:
                raise HTTPException(status_code=409, detail="No available worker for next phase")
            run_phase_task.delay(str(audit.id), next_phase, phase_exec.model_used, phase_exec.variant_used, None, 1, worker.id, next_env)
            action = f"accepted and queued {next_phase}"
        else:
            crud.update_audit_status(db, audit.id, f"{status_phase(phase_exec.phase)}_complete")
            action = "accepted as complete"
    elif decision in {"RERUN_SAME_OPTIONS", "RERUN_WITH_OPTIONS"}:
        model_settings = audit.model_settings or {}
        if decision == "RERUN_WITH_OPTIONS" and request.apply_env:
            phase_config = dict(model_settings.get(phase_exec.phase) or {})
            current_env = phase_config.get("env") or phase_config.get("env_overrides") or {}
            phase_config["env"] = {**(current_env or {}), **(triage.recommended_env or {})}
            model_settings[phase_exec.phase] = phase_config
            audit.model_settings = model_settings
            db.commit()

        worker = crud.select_available_worker(db, audit.assigned_worker_id)
        if not worker:
            raise HTTPException(status_code=409, detail="No available worker")
        phase_config = model_settings.get(phase_exec.phase, {})
        env_overrides = merged_phase_env(model_settings, phase_exec.phase)
        run_phase_task.delay(
            str(audit.id),
            phase_exec.phase,
            phase_config.get("model") or phase_exec.model_used,
            phase_config.get("variant") or phase_exec.variant_used,
            None,
            phase_exec.attempt + 1,
            worker.id,
            env_overrides,
        )
        audit.current_phase = phase_exec.phase
        db.commit()
        action = "phase rerun queued"
    else:
        raise HTTPException(status_code=409, detail=f"Unsupported triage decision: {decision}")

    crud.update_phase_triage(db, triage.id, {"status": "applied", "applied_at": datetime.now()})
    crud.create_audit_log(db, str(audit.id), "INFO", f"Applied triage #{triage.id}: {decision} ({action})", phase=phase_exec.phase, source="triage")
    return {"message": action, "decision": decision, "triage": triage_payload(crud.get_phase_triage(db, triage.id))}


@router.get("/{execution_id}/findings")
def get_phase_findings(execution_id: int, db: Session = Depends(get_db)):
    """Best-effort findings associated with a phase by creation timestamp."""
    phase_exec = db.query(PhaseExecution).filter(PhaseExecution.id == execution_id).first()
    if not phase_exec:
        raise HTTPException(status_code=404, detail="Phase execution not found")

    query = db.query(Finding).filter(Finding.audit_id == phase_exec.audit_id)
    if phase_exec.started_at:
        query = query.filter(Finding.created_at >= phase_exec.started_at)
    if phase_exec.completed_at:
        query = query.filter(Finding.created_at <= phase_exec.completed_at)

    findings = query.order_by(Finding.created_at.asc()).all()
    return {
        "phase_execution_id": phase_exec.id,
        "phase": phase_exec.phase,
        "total": len(findings),
        "inference": "created_at between phase start and completion",
        "findings": findings,
    }


@router.post("/{execution_id}/retry")
def retry_phase(execution_id: int, db: Session = Depends(get_db)):
    """Retry a failed phase execution."""
    phase_exec = db.query(PhaseExecution).filter(PhaseExecution.id == execution_id).first()
    if not phase_exec:
        raise HTTPException(status_code=404, detail="Phase execution not found")
    
    audit = db.query(Audit).filter(Audit.id == phase_exec.audit_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    
    model_settings = audit.model_settings or {}
    phase_config = model_settings.get(phase_exec.phase, {})
    
    model = phase_config.get("model")
    variant = phase_config.get("variant")
    env_overrides = merged_phase_env(model_settings, phase_exec.phase)
    
    # Queue retry
    worker = crud.select_available_worker(db, audit.assigned_worker_id)
    if not worker:
        raise HTTPException(status_code=409, detail="No available worker")

    run_phase_task.delay(
        str(phase_exec.audit_id),
        phase_exec.phase,
        model,
        variant,
        None,
        phase_exec.attempt + 1,
        worker.id,
        env_overrides,
    )
    audit.current_phase = phase_exec.phase
    db.commit()
    
    return JSONResponse(content={
        "message": "Phase retry queued",
        "new_execution_attempt": phase_exec.attempt + 1
    })
