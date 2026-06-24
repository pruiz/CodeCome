from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.sql import func
from app.database import Base
import uuid


class Audit(Base):
    __tablename__ = "audits"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    status = Column(String(50), nullable=False, default="initializing")
    
    # Workspace
    workspace_path = Column(Text, nullable=False, unique=True)
    
    # Source code origin
    source_type = Column(String(20))  # 'git', 'zip', 'local'
    source_location = Column(Text)
    
    # Configuration
    codecome_yml = Column(Text)
    model_settings = Column(JSON)
    
    # Orchestration
    current_phase = Column(String(20))
    assigned_worker_id = Column(Integer, ForeignKey("workers.id", ondelete="SET NULL"))
    ai_review_enabled = Column(Boolean, default=False)
    auto_continue = Column(Boolean, default=True)
    
    # Results
    total_findings = Column(Integer, default=0)
    findings_by_status = Column(JSON, default=lambda: {
        "PENDING": 0, "CONFIRMED": 0, "EXPLOITED": 0, "REJECTED": 0, "DUPLICATE": 0
    })
    
    # Metadata
    user_notes = Column(Text)
    tags = Column(ARRAY(String))
    
    __table_args__ = (
        Index("idx_audits_status", "status"),
        Index("idx_audits_created_at", "created_at", postgresql_using="brin"),
        Index("idx_audits_current_phase", "current_phase"),
        Index("idx_audits_worker", "assigned_worker_id"),
    )


class Worker(Base):
    __tablename__ = "workers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    type = Column(String(50), nullable=False, default="local")  # local, ssh, proxmox-vm, proxmox-lxc
    status = Column(String(50), nullable=False, default="idle")  # idle, running, offline, error, disabled
    host = Column(String(255))
    port = Column(Integer)
    username = Column(String(255))
    workspace_base_path = Column(Text)
    max_concurrent_jobs = Column(Integer, default=1)
    current_jobs = Column(Integer, default=0)
    capabilities = Column(JSON, default=dict)
    config = Column(JSON, default=dict)
    last_seen = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_workers_type", "type"),
        Index("idx_workers_status", "status"),
    )


class PhaseExecution(Base):
    __tablename__ = "phase_executions"
    
    id = Column(Integer, primary_key=True, index=True)
    audit_id = Column(UUID(as_uuid=True), ForeignKey("audits.id", ondelete="CASCADE"), nullable=False)
    worker_id = Column(Integer, ForeignKey("workers.id", ondelete="SET NULL"))
    phase = Column(String(20), nullable=False)
    attempt = Column(Integer, default=1)
    
    # Timing
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    duration_seconds = Column(Integer)
    
    # Status
    status = Column(String(20), nullable=False)  # 'running', 'success', 'failed', 'cancelled', 'skipped'
    exit_code = Column(Integer)
    error_message = Column(Text)
    command_line = Column(Text)
    
    # Logs (truncated)
    stdout_log = Column(Text)
    stderr_log = Column(Text)
    
    # Artifacts
    run_summary_path = Column(Text)
    transcript_path = Column(Text)
    remote_job_dir = Column(Text)
    remote_pid = Column(String(64))
    local_pid = Column(Integer)
    
    # AI review
    ai_review_decision = Column(JSON)
    ai_review_reasoning = Column(Text)
    ai_review_model = Column(String(100))
    
    # Metadata
    model_used = Column(String(100))
    variant_used = Column(String(20))
    opencode_session_id = Column(String(255))
    
    __table_args__ = (
        Index("idx_phase_executions_audit", "audit_id"),
        Index("idx_phase_executions_worker", "worker_id"),
        Index("idx_phase_executions_phase", "phase"),
        Index("idx_phase_executions_status", "status"),
        Index("idx_phase_executions_started", "started_at"),
    )


class PhaseTriage(Base):
    __tablename__ = "phase_triages"

    id = Column(Integer, primary_key=True, index=True)
    audit_id = Column(UUID(as_uuid=True), ForeignKey("audits.id", ondelete="CASCADE"), nullable=False)
    phase_execution_id = Column(Integer, ForeignKey("phase_executions.id", ondelete="CASCADE"), nullable=False)

    phase = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="queued")  # queued, running, completed, failed, applied
    decision = Column(String(50))  # ACCEPT_AS_COMPLETE, RERUN_SAME_OPTIONS, RERUN_WITH_OPTIONS, NEEDS_HUMAN
    confidence = Column(String(20))
    reason = Column(Text)
    recommended_env = Column(JSON, default=dict)
    evidence = Column(JSON, default=list)
    raw_response = Column(Text)
    report_path = Column(Text)
    decision_path = Column(Text)
    error_message = Column(Text)
    applied_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_phase_triages_audit", "audit_id"),
        Index("idx_phase_triages_execution", "phase_execution_id"),
        Index("idx_phase_triages_status", "status"),
    )


class Finding(Base):
    __tablename__ = "findings"
    
    id = Column(String(20), primary_key=True)  # e.g., 'CC-0001'
    audit_id = Column(UUID(as_uuid=True), ForeignKey("audits.id", ondelete="CASCADE"), nullable=False)
    
    # Core metadata
    title = Column(Text, nullable=False)
    status = Column(String(20), nullable=False)
    severity = Column(String(20))
    confidence = Column(String(20))
    category = Column(String(100))
    
    # Location
    file_path = Column(Text)
    line_numbers = Column(Text)
    
    # Full frontmatter and content
    frontmatter = Column(JSON, nullable=False)
    content = Column(Text)
    content_preview = Column(Text)
    
    # Evidence
    evidence_dir = Column(Text)
    has_evidence = Column(Boolean, default=False)
    has_exploit = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    duplicate_of = Column(String(20), ForeignKey("findings.id"))
    
    __table_args__ = (
        Index("idx_findings_audit", "audit_id"),
        Index("idx_findings_status", "status"),
        Index("idx_findings_severity", "severity"),
        Index("idx_findings_category", "category"),
        Index("idx_findings_created", "created_at"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    audit_id = Column(UUID(as_uuid=True), ForeignKey("audits.id", ondelete="CASCADE"), nullable=False)
    
    # Log entry
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    level = Column(String(10), nullable=False)  # 'DEBUG', 'INFO', 'WARN', 'ERROR'
    phase = Column(String(20))
    agent = Column(String(50))
    
    # Message
    message = Column(Text, nullable=False)
    log_metadata = Column(JSON)
    
    # Source
    source = Column(String(50))  # 'stdout', 'stderr', 'opencode', 'system'
    process_id = Column(Integer)
    
    __table_args__ = (
        Index("idx_audit_logs_audit", "audit_id"),
        Index("idx_audit_logs_timestamp", "timestamp"),
        Index("idx_audit_logs_level", "level"),
    )


class AIReviewHistory(Base):
    __tablename__ = "ai_review_history"
    
    id = Column(Integer, primary_key=True, index=True)
    audit_id = Column(UUID(as_uuid=True), ForeignKey("audits.id", ondelete="CASCADE"), nullable=False)
    phase_execution_id = Column(Integer, ForeignKey("phase_executions.id", ondelete="SET NULL"))
    
    # Review context
    phase = Column(String(20), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # AI analysis
    model_used = Column(String(100), nullable=False)
    prompt = Column(Text)
    raw_response = Column(Text)
    
    # Parsed decision
    decision = Column(String(50), nullable=False)
    reasoning = Column(Text)
    confidence = Column(String(20))
    parameters = Column(JSON)
    
    # Human override
    human_override = Column(Boolean, default=False)
    human_decision = Column(String(50))
    human_notes = Column(Text)
    
    # Execution
    action_taken = Column(String(50))
    action_result = Column(String(20))  # 'success', 'failed', 'pending'
    
    __table_args__ = (
        Index("idx_ai_review_history_audit", "audit_id"),
        Index("idx_ai_review_history_phase", "phase"),
        Index("idx_ai_review_history_reviewed", "reviewed_at"),
    )


class AuditTemplate(Base):
    __tablename__ = "audit_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text)
    
    # Template content
    codecome_yml = Column(Text, nullable=False)
    model_settings = Column(JSON)
    
    # Usage tracking
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True))
    use_count = Column(Integer, default=0)
    
    # Categorization
    tags = Column(ARRAY(String))
    is_builtin = Column(Boolean, default=False)
    
    __table_args__ = (
        Index("idx_audit_templates_name", "name"),
    )
