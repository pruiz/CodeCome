from sqlalchemy.orm import Session
from sqlalchemy import select, func, update, delete
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
import hashlib
import hmac
import secrets
from app import models, schemas
from app.config import settings


# === Audit CRUD ===

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        algorithm, salt, digest = password_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return hmac.compare_digest(candidate, digest)


def create_user(db: Session, user_data: schemas.UserCreate) -> models.User:
    is_llm_user = user_data.is_llm_user
    db_user = models.User(
        username=user_data.username,
        display_name=user_data.display_name or user_data.username,
        password_hash=hash_password(user_data.password) if user_data.password else None,
        is_llm_user=is_llm_user,
        llm_model=user_data.llm_model if is_llm_user else None,
        llm_context=user_data.llm_context if is_llm_user else None,
        auto_answer_enabled=user_data.auto_answer_enabled if is_llm_user else False,
        active=user_data.active,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_user(db: Session, user_id: int) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.username == username).first()


def has_active_human_users(db: Session) -> bool:
    return db.query(models.User).filter(
        models.User.active.is_(True),
        models.User.is_llm_user.is_(False),
    ).first() is not None


def has_other_active_human_users(db: Session, user_id: int) -> bool:
    return db.query(models.User).filter(
        models.User.id != user_id,
        models.User.active.is_(True),
        models.User.is_llm_user.is_(False),
    ).first() is not None


def default_question_owner(db: Session) -> Optional[models.User]:
    return (
        db.query(models.User)
        .filter(models.User.active.is_(True), models.User.is_llm_user.is_(False))
        .order_by(models.User.id.asc())
        .first()
    )


def get_users(db: Session, skip: int = 0, limit: int = 100, active: Optional[bool] = None, is_llm_user: Optional[bool] = None) -> tuple[int, List[models.User]]:
    query = db.query(models.User)
    count_query = db.query(func.count(models.User.id))
    if active is not None:
        query = query.filter(models.User.active == active)
        count_query = count_query.filter(models.User.active == active)
    if is_llm_user is not None:
        query = query.filter(models.User.is_llm_user == is_llm_user)
        count_query = count_query.filter(models.User.is_llm_user == is_llm_user)
    total = count_query.scalar()
    users = query.order_by(models.User.username.asc()).offset(skip).limit(limit).all()
    return total, users


def update_user(db: Session, user_id: int, user_data: schemas.UserUpdate) -> Optional[models.User]:
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    data = user_data.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    if password:
        db_user.password_hash = hash_password(password)
    for key, value in data.items():
        setattr(db_user, key, value)
    if not db_user.is_llm_user:
        db_user.llm_model = None
        db_user.llm_context = None
        db_user.auto_answer_enabled = False
    else:
        db_user.password_hash = None
    db.commit()
    db.refresh(db_user)
    return db_user

def create_audit(db: Session, audit_data: schemas.AuditCreate) -> models.Audit:
    db_audit = models.Audit(
        name=audit_data.name,
        workspace_path=audit_data.workspace_path,
        source_type=audit_data.source_type,
        source_location=audit_data.source_location,
        codecome_yml=audit_data.codecome_yml,
        model_settings=audit_data.model_settings,
        assigned_worker_id=audit_data.worker_id,
        question_owner_user_id=audit_data.question_owner_user_id,
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


def worker_capacity_available(worker: models.Worker) -> bool:
    if not worker or worker.status in ("offline", "disabled", "error"):
        return False
    current_jobs = worker.current_jobs or 0
    if worker.type == "local":
        # Local CodeCome runs share Docker/sandbox resources; force one active
        # local job even if max_concurrent_jobs is configured higher.
        return current_jobs < 1
    return current_jobs < (worker.max_concurrent_jobs or 1)


def sync_worker_job_state(worker: models.Worker, running_jobs: int) -> bool:
    running_jobs = max(int(running_jobs or 0), 0)
    changed = (worker.current_jobs or 0) != running_jobs
    worker.current_jobs = running_jobs
    if worker.status not in ("offline", "disabled", "error"):
        next_status = "running" if running_jobs else "idle"
        changed = changed or worker.status != next_status
        worker.status = next_status
    return changed


def reconcile_worker_job_counts(db: Session, worker_ids: Optional[list[int]] = None) -> None:
    query = db.query(models.Worker)
    if worker_ids:
        query = query.filter(models.Worker.id.in_(worker_ids))
    workers = query.all()
    if not workers:
        return

    running_counts = dict(
        db.query(models.PhaseExecution.worker_id, func.count(models.PhaseExecution.id))
        .filter(models.PhaseExecution.status == "running")
        .filter(models.PhaseExecution.worker_id.in_([worker.id for worker in workers]))
        .group_by(models.PhaseExecution.worker_id)
        .all()
    )
    changed = False
    for worker in workers:
        changed = sync_worker_job_state(worker, running_counts.get(worker.id, 0)) or changed
    if changed:
        db.commit()


def select_available_worker(db: Session, preferred_worker_id: Optional[int] = None) -> Optional[models.Worker]:
    reconcile_worker_job_counts(db, [preferred_worker_id] if preferred_worker_id else None)
    if preferred_worker_id:
        worker = get_worker(db, preferred_worker_id)
        if worker_capacity_available(worker):
            return worker

    candidates = db.query(models.Worker).filter(
        models.Worker.status.in_(["idle", "running"]),
    ).order_by(models.Worker.current_jobs.asc(), models.Worker.id.asc()).all()

    for worker in candidates:
        if worker_capacity_available(worker):
            return worker

    if not candidates:
        return ensure_local_worker(db)
    return None


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


def create_phase_question(db: Session, question_data: schemas.PhaseQuestionCreate) -> models.PhaseQuestion:
    question = models.PhaseQuestion(status="OPEN", **question_data.model_dump())
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


def get_phase_question(db: Session, question_id: int) -> Optional[models.PhaseQuestion]:
    return db.query(models.PhaseQuestion).filter(models.PhaseQuestion.id == question_id).first()


def get_phase_questions(
    db: Session,
    audit_id: Optional[UUID] = None,
    phase_execution_id: Optional[int] = None,
    status_filter: Optional[str] = None,
) -> tuple[int, List[models.PhaseQuestion]]:
    query = db.query(models.PhaseQuestion)
    count_query = db.query(func.count(models.PhaseQuestion.id))
    if audit_id:
        query = query.filter(models.PhaseQuestion.audit_id == audit_id)
        count_query = count_query.filter(models.PhaseQuestion.audit_id == audit_id)
    if phase_execution_id:
        query = query.filter(models.PhaseQuestion.phase_execution_id == phase_execution_id)
        count_query = count_query.filter(models.PhaseQuestion.phase_execution_id == phase_execution_id)
    if status_filter:
        query = query.filter(models.PhaseQuestion.status == status_filter)
        count_query = count_query.filter(models.PhaseQuestion.status == status_filter)
    total = count_query.scalar()
    questions = query.order_by(models.PhaseQuestion.created_at.desc(), models.PhaseQuestion.id.desc()).all()
    return total, questions


def update_phase_question(db: Session, question_id: int, updates: schemas.PhaseQuestionUpdate) -> Optional[models.PhaseQuestion]:
    question = get_phase_question(db, question_id)
    if not question:
        return None
    data = updates.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(question, key, value)
    if data.get("status") in ("ANSWERED", "AUTO_ANSWERED", "DISMISSED") and not question.answered_at:
        question.answered_at = datetime.now()
    db.commit()
    db.refresh(question)
    return question


def answer_phase_question(db: Session, question_id: int, answer_data: schemas.PhaseQuestionAnswer) -> Optional[models.PhaseQuestion]:
    return update_phase_question(db, question_id, schemas.PhaseQuestionUpdate(
        status=answer_data.status,
        answer=answer_data.answer,
        answered_by_user_id=answer_data.answered_by_user_id,
        answer_model=answer_data.answer_model,
        answer_confidence=answer_data.answer_confidence,
    ))


def dismiss_phase_question(db: Session, question_id: int, answered_by_user_id: int | None = None) -> Optional[models.PhaseQuestion]:
    return update_phase_question(db, question_id, schemas.PhaseQuestionUpdate(
        status="DISMISSED",
        answered_by_user_id=answered_by_user_id,
    ))


def audit_has_open_blocking_questions(db: Session, audit_id: UUID) -> bool:
    return db.query(models.PhaseQuestion).filter(
        models.PhaseQuestion.audit_id == audit_id,
        models.PhaseQuestion.status == "OPEN",
        models.PhaseQuestion.blocking.is_(True),
    ).first() is not None


def question_counts_for_audit(db: Session, audit_id: UUID) -> dict[str, int]:
    _, open_questions = get_phase_questions(db, audit_id=audit_id, status_filter="OPEN")
    return {
        "open_questions": len(open_questions),
        "blocking_questions": sum(1 for question in open_questions if question.blocking),
    }


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
