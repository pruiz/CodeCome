from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


# === Audit Schemas ===

class AuditCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(..., pattern="^(git|zip|local)$")
    source_location: str = Field(..., min_length=1)
    codecome_yml: Optional[str] = None
    model_settings: Optional[Dict[str, Any]] = None
    ai_review_enabled: bool = False
    auto_continue: bool = True
    worker_id: Optional[int] = None
    question_owner_user_id: Optional[int] = None
    workspace_path: str = ""


class AuditUpdate(BaseModel):
    name: Optional[str] = None
    codecome_yml: Optional[str] = None
    model_settings: Optional[Dict[str, Any]] = None
    ai_review_enabled: Optional[bool] = None
    auto_continue: Optional[bool] = None
    worker_id: Optional[int] = None
    question_owner_user_id: Optional[int] = None
    user_notes: Optional[str] = None


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=255)
    display_name: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, min_length=1)
    is_llm_user: bool = False
    llm_model: Optional[str] = None
    llm_context: Optional[str] = None
    auto_answer_enabled: bool = True
    active: bool = True


class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, min_length=1)
    is_llm_user: Optional[bool] = None
    llm_model: Optional[str] = None
    llm_context: Optional[str] = None
    auto_answer_enabled: Optional[bool] = None
    active: Optional[bool] = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    is_llm_user: bool
    llm_model: Optional[str] = None
    llm_context: Optional[str] = None
    auto_answer_enabled: bool
    active: bool
    created_at: datetime
    updated_at: datetime

class UserListResponse(BaseModel):
    total: int
    users: List[UserResponse]


class AuthLoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class PhaseExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    audit_id: UUID
    worker_id: Optional[int] = None
    phase: str
    attempt: int
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    exit_code: Optional[int] = None
    command_line: Optional[str] = None
    remote_job_dir: Optional[str] = None
    remote_pid: Optional[str] = None
    local_pid: Optional[int] = None
    model_used: Optional[str] = None
    run_summary_path: Optional[str] = None
    
class PhaseTriageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    audit_id: UUID
    phase_execution_id: int
    phase: str
    status: str
    decision: Optional[str] = None
    confidence: Optional[str] = None
    reason: Optional[str] = None
    recommended_env: Optional[Dict[str, Any]] = None
    evidence: Optional[List[str]] = None
    raw_response: Optional[str] = None
    report_path: Optional[str] = None
    decision_path: Optional[str] = None
    error_message: Optional[str] = None
    applied_at: Optional[datetime] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

class PhaseTriageApplyRequest(BaseModel):
    apply_env: bool = True


class PhaseQuestionCreate(BaseModel):
    audit_id: UUID
    phase_execution_id: int
    phase: str
    question: str = Field(..., min_length=1)
    context: Optional[str] = None
    source: str = "llm_detector"
    blocking: bool = True
    assigned_user_id: Optional[int] = None


class PhaseQuestionAnswer(BaseModel):
    answer: str = Field(..., min_length=1)
    answered_by_user_id: Optional[int] = None
    status: str = Field("ANSWERED", pattern="^(ANSWERED|AUTO_ANSWERED)$")
    answer_model: Optional[str] = None
    answer_confidence: Optional[str] = None


class PhaseQuestionUpdate(BaseModel):
    question: Optional[str] = None
    context: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(OPEN|ANSWERED|AUTO_ANSWERED|DISMISSED)$")
    blocking: Optional[bool] = None
    assigned_user_id: Optional[int] = None
    answer: Optional[str] = None
    answered_by_user_id: Optional[int] = None
    answer_model: Optional[str] = None
    answer_confidence: Optional[str] = None


class PhaseQuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    audit_id: UUID
    phase_execution_id: int
    phase: str
    question: str
    context: Optional[str] = None
    source: Optional[str] = None
    status: str
    blocking: bool
    assigned_user_id: Optional[int] = None
    answer: Optional[str] = None
    answered_by_user_id: Optional[int] = None
    answer_model: Optional[str] = None
    answer_confidence: Optional[str] = None
    created_at: datetime
    answered_at: Optional[datetime] = None

class PhaseQuestionListResponse(BaseModel):
    total: int
    questions: List[PhaseQuestionResponse]


class AuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    status: str
    current_phase: Optional[str] = None
    assigned_worker_id: Optional[int] = None
    question_owner_user_id: Optional[int] = None
    workspace_path: str
    source_type: Optional[str] = None
    source_location: Optional[str] = None
    has_codecome_yml: bool = False
    codecome_yml: Optional[str] = None
    model_settings: Optional[Dict[str, Any]] = None
    ai_review_enabled: bool
    auto_continue: bool
    total_findings: int
    findings_by_status: Dict[str, int]
    open_questions: int = 0
    blocking_questions: int = 0
    created_at: datetime
    updated_at: datetime
    phase_executions: Optional[List[PhaseExecutionResponse]] = None
    
class AuditListResponse(BaseModel):
    total: int
    audits: List[AuditResponse]


# === Worker Schemas ===

class WorkerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field("local", pattern="^(local|ssh|proxmox-vm|proxmox-lxc)$")
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    workspace_base_path: Optional[str] = None
    max_concurrent_jobs: int = Field(1, ge=1, le=64)
    capabilities: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None


class WorkerUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(idle|running|offline|error|disabled)$")
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    workspace_base_path: Optional[str] = None
    max_concurrent_jobs: Optional[int] = Field(None, ge=1, le=64)
    capabilities: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None


class WorkerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    status: str
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    workspace_base_path: Optional[str] = None
    max_concurrent_jobs: int
    current_jobs: int
    capabilities: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None
    last_seen: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

class WorkerListResponse(BaseModel):
    total: int
    workers: List[WorkerResponse]


class WorkerOpenCodeConfig(BaseModel):
    content: str = ""
    updated: bool = False


class WorkerRequirementCheck(BaseModel):
    key: str
    label: str
    required: bool = True
    ok: bool = False
    detail: str = ""


class WorkerChecksResponse(BaseModel):
    worker_id: int
    worker_name: str
    source: str
    checks: List[WorkerRequirementCheck]


class PreviewAnalysisConfig(BaseModel):
    prompt: str = ""
    updated: bool = False


# === Finding Schemas ===

class FindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    audit_id: UUID
    audit_name: Optional[str] = None
    title: str
    status: str
    severity: Optional[str] = None
    confidence: Optional[str] = None
    category: Optional[str] = None
    file_path: Optional[str] = None
    frontmatter: Dict[str, Any]
    content: Optional[str] = None
    evidence_dir: Optional[str] = None
    has_evidence: bool
    has_exploit: bool
    created_at: datetime
    updated_at: datetime
    
class FindingListResponse(BaseModel):
    total: int
    findings: List[FindingResponse]


class FindingUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern="^(PENDING|CONFIRMED|EXPLOITED|REJECTED|DUPLICATE)$")
    severity: Optional[str] = Field(None, pattern="^(CRITICAL|HIGH|MEDIUM|LOW|INFO)$")
    confidence: Optional[str] = Field(None, pattern="^(LOW|MEDIUM|HIGH|CONFIRMED)$")
    category: Optional[str] = None
    reviewer_note: Optional[str] = None


# === Log Schemas ===

class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    audit_id: UUID
    timestamp: datetime
    level: str
    phase: Optional[str] = None
    agent: Optional[str] = None
    message: str
    metadata: Optional[Dict[str, Any]] = None
    source: Optional[str] = None
    
class LogExportResponse(BaseModel):
    audit_id: UUID
    total: int
    logs: List[AuditLogResponse]


# === AI Review Schemas ===

class AIReviewRequest(BaseModel):
    override_decision: Optional[str] = None
    notes: Optional[str] = None


class AIReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    audit_id: UUID
    phase: str
    decision: str
    reasoning: Optional[str] = None
    confidence: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    human_override: bool
    action_result: Optional[str] = None
    reviewed_at: datetime
    
# === Template Schemas ===

class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    codecome_yml: str
    model_settings: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    codecome_yml: str
    model_settings: Optional[Dict[str, Any]] = None
    use_count: int
    tags: Optional[List[str]] = None
    is_builtin: bool
    
# === Evidence ===

class EvidenceFile(BaseModel):
    name: str
    path: str
    size: int
    mime_type: str


class EvidenceListResponse(BaseModel):
    finding_id: str
    evidence_dir: Optional[str] = None
    files: List[EvidenceFile]
