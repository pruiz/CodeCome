from sqlalchemy.orm import Session
from sqlalchemy import select, func, update, delete
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from app import models, schemas
from app.config import settings


# === Audit CRUD ===

def create_audit(db: Session, audit_data: schemas.AuditCreate) -> models.Audit:
    db_audit = models.Audit(
        name=audit_data.name,
        workspace_path=audit_data.workspace_path,
        source_type=audit_data.source_type,
        source_location=audit_data.source_location,
        codecome_yml=audit_data.codecome_yml,
        model_settings=audit_data.model_settings,
        assigned_worker_id=audit_data.worker_id,
        ai_review_enabled=audit_data.ai_review_enabled,
        auto_continue=audit_data.auto_continue,
        status="initializing",
        findings_by_status={"PENDING": 0, "CONFIRMED": 0, "EXPLOITED": 0, "REJECTED": 0, "DUPLICATE": 0}
    )
    db.add(db_audit)
    db.commit()
    db.refresh(db_audit)
    
    # Update workspace_path to match audit ID (in case it was different)
    if db_audit.workspace_path:
        # Extract the audit ID from the created record
        new_workspace_path = f"{settings.WORKSPACES_DIR}/audit-{db_audit.id}"
        if db_audit.workspace_path != new_workspace_path:
            from pathlib import Path
            old_path = Path(db_audit.workspace_path)
            new_path = Path(new_workspace_path)
            if old_path.exists():
                new_path.parent.mkdir(parents=True, exist_ok=True)
                # Rename directory
                import shutil
                if new_path.exists():
                    shutil.rmtree(new_path)
                shutil.move(str(old_path), str(new_path))
            db_audit.workspace_path = new_workspace_path
            db.commit()
            db.refresh(db_audit)
    
    return db_audit


# === Worker CRUD ===

def create_worker(db: Session, worker_data: schemas.WorkerCreate) -> models.Worker:
    db_worker = models.Worker(
        name=worker_data.name,
        type=worker_data.type,
        host=worker_data.host,
        port=worker_data.port,
        username=worker_data.username,
        workspace_base_path=worker_data.workspace_base_path,
        max_concurrent_jobs=worker_data.max_concurrent_jobs,
        capabilities=worker_data.capabilities or {},
        config=worker_data.config or {},
    )
    db.add(db_worker)
    db.commit()
    db.refresh(db_worker)
    return db_worker


def get_worker(db: Session, worker_id: int) -> Optional[models.Worker]:
    return db.query(models.Worker).filter(models.Worker.id == worker_id).first()


def get_worker_by_name(db: Session, name: str) -> Optional[models.Worker]:
    return db.query(models.Worker).filter(models.Worker.name == name).first()


def get_workers(db: Session, skip: int = 0, limit: int = 100, status_filter: Optional[str] = None) -> tuple[int, List[models.Worker]]:
    query = db.query(models.Worker)
    count_query = db.query(func.count(models.Worker.id))

    if status_filter:
        query = query.filter(models.Worker.status == status_filter)
        count_query = count_query.filter(models.Worker.status == status_filter)

    total = count_query.scalar()
    workers = query.order_by(models.Worker.name.asc()).offset(skip).limit(limit).all()
    return total, workers


def update_worker(db: Session, worker_id: int, worker_data: schemas.WorkerUpdate) -> Optional[models.Worker]:
    db_worker = get_worker(db, worker_id)
    if not db_worker:
        return None

    for key, value in worker_data.model_dump(exclude_unset=True).items():
        if key == "config" and isinstance(value, dict):
            merged = dict(db_worker.config or {})
            incoming = dict(value)
            if isinstance(incoming.get("ssh_auth"), dict):
                existing_auth = dict(merged.get("ssh_auth") or {})
                incoming_auth = {k: v for k, v in incoming["ssh_auth"].items() if v not in (None, "")}
                for redacted_key in ("has_password", "has_private_key", "has_passphrase"):
                    incoming_auth.pop(redacted_key, None)
                existing_auth.update(incoming_auth)
                incoming["ssh_auth"] = existing_auth
            merged.update(incoming)
            value = merged
        setattr(db_worker, key, value)

    db.commit()
    db.refresh(db_worker)
    return db_worker


def delete_worker(db: Session, worker_id: int) -> bool:
    db_worker = get_worker(db, worker_id)
    if not db_worker:
        return False
    db.delete(db_worker)
    db.commit()
    return True


def ensure_local_worker(db: Session) -> models.Worker:
    existing = get_worker_by_name(db, "local")
    if existing:
        return existing

    return create_worker(db, schemas.WorkerCreate(
        name="local",
        type="local",
        host="localhost",
        workspace_base_path=str(settings.WORKSPACES_DIR),
        max_concurrent_jobs=1,
        capabilities={"docker": True, "codecome": True},
        config={},
    ))


def select_available_worker(db: Session, preferred_worker_id: Optional[int] = None) -> Optional[models.Worker]:
    if preferred_worker_id:
        worker = get_worker(db, preferred_worker_id)
        if worker and worker.status not in ("offline", "disabled", "error") and worker.current_jobs < worker.max_concurrent_jobs:
            return worker

    worker = db.query(models.Worker).filter(
        models.Worker.status.in_(["idle", "running"]),
        models.Worker.current_jobs < models.Worker.max_concurrent_jobs,
    ).order_by(models.Worker.current_jobs.asc(), models.Worker.id.asc()).first()

    if worker:
        return worker

    return ensure_local_worker(db)


def mark_worker_job_started(db: Session, worker_id: int) -> Optional[models.Worker]:
    worker = get_worker(db, worker_id)
    if not worker:
        return None
    worker.current_jobs = (worker.current_jobs or 0) + 1
    worker.status = "running" if worker.current_jobs >= worker.max_concurrent_jobs else "idle"
    worker.last_seen = datetime.now()
    db.commit()
    db.refresh(worker)
    return worker


def mark_worker_job_finished(db: Session, worker_id: int) -> Optional[models.Worker]:
    worker = get_worker(db, worker_id)
    if not worker:
        return None
    worker.current_jobs = max((worker.current_jobs or 0) - 1, 0)
    worker.status = "idle" if worker.current_jobs == 0 else "running"
    worker.last_seen = datetime.now()
    db.commit()
    db.refresh(worker)
    return worker


def get_audit(db: Session, audit_id: UUID) -> Optional[models.Audit]:
    return db.query(models.Audit).filter(models.Audit.id == audit_id).first()


def get_audits(db: Session, skip: int = 0, limit: int = 20, status_filter: Optional[str] = None) -> tuple[int, List[models.Audit]]:
    query = db.query(models.Audit)
    count_query = db.query(func.count(models.Audit.id))
    
    if status_filter:
        query = query.filter(models.Audit.status == status_filter)
        count_query = count_query.filter(models.Audit.status == status_filter)
    
    total = count_query.scalar()
    audits = query.order_by(models.Audit.created_at.desc()).offset(skip).limit(limit).all()
    
    return total, audits


def update_audit(db: Session, audit_id: UUID, audit_data: schemas.AuditUpdate) -> Optional[models.Audit]:
    db_audit = get_audit(db, audit_id)
    if not db_audit:
        return None
    
    update_data = audit_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_audit, key, value)
    
    db.commit()
    db.refresh(db_audit)
    return db_audit


def create_phase_triage(db: Session, data: Dict[str, Any]) -> models.PhaseTriage:
    triage = models.PhaseTriage(**data)
    db.add(triage)
    db.commit()
    db.refresh(triage)
    return triage


def update_phase_triage(db: Session, triage_id: int, updates: Dict[str, Any]) -> Optional[models.PhaseTriage]:
    triage = db.query(models.PhaseTriage).filter(models.PhaseTriage.id == triage_id).first()
    if not triage:
        return None
    for key, value in updates.items():
        setattr(triage, key, value)
    db.commit()
    db.refresh(triage)
    return triage


def get_phase_triages(db: Session, phase_execution_id: int) -> List[models.PhaseTriage]:
    return (
        db.query(models.PhaseTriage)
        .filter(models.PhaseTriage.phase_execution_id == phase_execution_id)
        .order_by(models.PhaseTriage.created_at.desc(), models.PhaseTriage.id.desc())
        .all()
    )


def get_phase_triage(db: Session, triage_id: int) -> Optional[models.PhaseTriage]:
    return db.query(models.PhaseTriage).filter(models.PhaseTriage.id == triage_id).first()


def latest_phase_triage(db: Session, phase_execution_id: int) -> Optional[models.PhaseTriage]:
    return (
        db.query(models.PhaseTriage)
        .filter(models.PhaseTriage.phase_execution_id == phase_execution_id)
        .order_by(models.PhaseTriage.created_at.desc(), models.PhaseTriage.id.desc())
        .first()
    )


def update_audit_status(db: Session, audit_id: UUID, new_status: str) -> Optional[models.Audit]:
    db_audit = get_audit(db, audit_id)
    if not db_audit:
        return None
    
    db_audit.status = new_status
    db.commit()
    db.refresh(db_audit)
    return db_audit


def update_audit_findings_count(db: Session, audit_id: UUID) -> Optional[models.Audit]:
    db_audit = get_audit(db, audit_id)
    if not db_audit:
        return None
    
    total = db.query(func.count(models.Finding.id)).filter(models.Finding.audit_id == audit_id).scalar()
    status_counts = db.query(
        models.Finding.status, func.count(models.Finding.id).label("count")
    ).filter(
        models.Finding.audit_id == audit_id
    ).group_by(models.Finding.status).all()
    
    db_audit.total_findings = total
    db_audit.findings_by_status = {sc.status: sc.count for sc in status_counts}
    
    # Ensure all statuses present
    for s in ["PENDING", "CONFIRMED", "EXPLOITED", "REJECTED", "DUPLICATE"]:
        if s not in db_audit.findings_by_status:
            db_audit.findings_by_status[s] = 0
    
    db.commit()
    db.refresh(db_audit)
    return db_audit


def delete_audit(db: Session, audit_id: UUID) -> bool:
    db_audit = get_audit(db, audit_id)
    if not db_audit:
        return False
    
    db.delete(db_audit)
    db.commit()
    return True


# === Phase Execution CRUD ===

def create_phase_execution(db: Session, phase_data: dict) -> models.PhaseExecution:
    db_phase = models.PhaseExecution(**phase_data)
    db.add(db_phase)
    db.commit()
    db.refresh(db_phase)
    return db_phase


def get_phase_executions(db: Session, audit_id: UUID) -> List[models.PhaseExecution]:
    return db.query(models.PhaseExecution).filter(
        models.PhaseExecution.audit_id == audit_id
    ).order_by(models.PhaseExecution.started_at.asc(), models.PhaseExecution.id.asc()).all()


def update_phase_execution(db: Session, exec_id: int, phase_data: dict) -> Optional[models.PhaseExecution]:
    db_phase = db.query(models.PhaseExecution).get(exec_id)
    if not db_phase:
        return None
    
    for key, value in phase_data.items():
        setattr(db_phase, key, value)
    
    db.commit()
    db.refresh(db_phase)
    return db_phase


# === Finding CRUD ===

def upsert_finding(db: Session, finding_data: dict) -> models.Finding:
    finding_id = finding_data["id"]
    
    existing = db.query(models.Finding).filter(models.Finding.id == finding_id).first()
    
    if existing:
        for key, value in finding_data.items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing
    else:
        db_finding = models.Finding(**finding_data)
        db.add(db_finding)
        db.commit()
        db.refresh(db_finding)
        return db_finding


def delete_findings_for_audit(db: Session, audit_id: UUID) -> int:
    result = db.query(models.Finding).filter(models.Finding.audit_id == audit_id).delete()
    db.commit()
    return result


def get_findings(db: Session, audit_id: Optional[UUID] = None, skip: int = 0, limit: int = 50, 
                 status_filter: Optional[str] = None, severity_filter: Optional[str] = None,
                 category_filter: Optional[str] = None) -> tuple[int, List[models.Finding]]:
    query = db.query(models.Finding)
    count_query = db.query(func.count(models.Finding.id))

    if audit_id:
        query = query.filter(models.Finding.audit_id == audit_id)
        count_query = count_query.filter(models.Finding.audit_id == audit_id)
    
    if status_filter:
        query = query.filter(models.Finding.status == status_filter)
        count_query = count_query.filter(models.Finding.status == status_filter)
    if severity_filter:
        query = query.filter(models.Finding.severity == severity_filter)
        count_query = count_query.filter(models.Finding.severity == severity_filter)
    if category_filter:
        query = query.filter(models.Finding.category == category_filter)
        count_query = count_query.filter(models.Finding.category == category_filter)
    
    total = count_query.scalar()
    findings = query.order_by(models.Finding.severity.desc(), models.Finding.created_at.desc()).offset(skip).limit(limit).all()
    
    return total, findings


def get_finding(db: Session, finding_id: str) -> Optional[models.Finding]:
    return db.query(models.Finding).filter(models.Finding.id == finding_id).first()


def apply_finding_update(finding: models.Finding, update_data: schemas.FindingUpdate) -> models.Finding:
    data = update_data.model_dump(exclude_unset=True)
    reviewer_note = data.pop("reviewer_note", None)

    frontmatter = dict(finding.frontmatter or {})
    review_history = list(frontmatter.get("review_history") or [])

    for key, value in data.items():
        setattr(finding, key, value)
        frontmatter[key] = value

    if reviewer_note:
        review_history.append({"note": reviewer_note, "timestamp": datetime.now().isoformat()})
        frontmatter["review_history"] = review_history

    finding.frontmatter = frontmatter
    return finding


def update_finding(db: Session, finding_id: str, update_data: schemas.FindingUpdate, audit_id: Optional[UUID] = None) -> Optional[models.Finding]:
    query = db.query(models.Finding).filter(models.Finding.id == finding_id)
    if audit_id:
        query = query.filter(models.Finding.audit_id == audit_id)
    finding = query.first()
    if not finding:
        return None

    apply_finding_update(finding, update_data)
    db.commit()
    db.refresh(finding)
    update_audit_findings_count(db, finding.audit_id)
    return finding


# === Audit Log CRUD ===

def create_audit_log(db: Session, audit_id: UUID, level: str, message: str, 
                     metadata: Optional[dict] = None, phase: Optional[str] = None,
                     agent: Optional[str] = None, source: Optional[str] = None) -> models.AuditLog:
    db_log = models.AuditLog(
        audit_id=audit_id,
        level=level,
        message=message,
        log_metadata=metadata or {},
        phase=phase,
        agent=agent,
        source=source
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log


def get_audit_logs(db: Session, audit_id: UUID, skip: int = 0, limit: int = 100,
                   level_filter: Optional[str] = None, phase_filter: Optional[str] = None) -> tuple[int, List[models.AuditLog]]:
    query = db.query(models.AuditLog).filter(models.AuditLog.audit_id == audit_id)
    count_query = db.query(func.count(models.AuditLog.id)).filter(models.AuditLog.audit_id == audit_id)
    
    if level_filter:
        query = query.filter(models.AuditLog.level == level_filter)
        count_query = count_query.filter(models.AuditLog.level == level_filter)
    if phase_filter:
        query = query.filter(models.AuditLog.phase == phase_filter)
        count_query = count_query.filter(models.AuditLog.phase == phase_filter)
    
    total = count_query.scalar()
    logs = query.order_by(models.AuditLog.timestamp.desc()).offset(skip).limit(limit).all()
    
    return total, logs


def get_new_audit_logs(db: Session, audit_id: UUID, last_id: int = 0) -> List[models.AuditLog]:
    return db.query(models.AuditLog).filter(
        models.AuditLog.audit_id == audit_id,
        models.AuditLog.id > last_id
    ).order_by(models.AuditLog.id.asc()).all()


# === AI Review CRUD ===

def create_ai_review(db: Session, review_data: dict) -> models.AIReviewHistory:
    db_review = models.AIReviewHistory(**review_data)
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    return db_review


def get_ai_reviews(db: Session, audit_id: UUID) -> List[models.AIReviewHistory]:
    return db.query(models.AIReviewHistory).filter(
        models.AIReviewHistory.audit_id == audit_id
    ).order_by(models.AIReviewHistory.reviewed_at.desc()).all()
