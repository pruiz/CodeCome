from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID

from app import crud, schemas
from app.database import get_db
from app.models import PhaseExecution
from app.workers.question_answering import auto_answer_open_questions, write_user_answers_context
from pathlib import Path

router = APIRouter()


@router.get("/", response_model=schemas.PhaseQuestionListResponse)
def list_questions(
    audit_id: UUID | None = Query(None),
    phase_execution_id: int | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    total, questions = crud.get_phase_questions(
        db,
        audit_id=audit_id,
        phase_execution_id=phase_execution_id,
        status_filter=status,
    )
    return schemas.PhaseQuestionListResponse(total=total, questions=questions)


@router.post("/", response_model=schemas.PhaseQuestionResponse, status_code=201)
def create_question(question_data: schemas.PhaseQuestionCreate, db: Session = Depends(get_db)):
    if not crud.get_audit(db, question_data.audit_id):
        raise HTTPException(status_code=404, detail="Audit not found")
    if question_data.assigned_user_id and not crud.get_user(db, question_data.assigned_user_id):
        raise HTTPException(status_code=404, detail="Assigned user not found")
    return crud.create_phase_question(db, question_data)


@router.get("/{question_id}", response_model=schemas.PhaseQuestionResponse)
def get_question(question_id: int, db: Session = Depends(get_db)):
    question = crud.get_phase_question(db, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


@router.patch("/{question_id}", response_model=schemas.PhaseQuestionResponse)
def update_question(question_id: int, question_data: schemas.PhaseQuestionUpdate, db: Session = Depends(get_db)):
    if question_data.assigned_user_id and not crud.get_user(db, question_data.assigned_user_id):
        raise HTTPException(status_code=404, detail="Assigned user not found")
    if question_data.answered_by_user_id and not crud.get_user(db, question_data.answered_by_user_id):
        raise HTTPException(status_code=404, detail="Answering user not found")
    question = crud.update_phase_question(db, question_id, question_data)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


@router.post("/{question_id}/answer", response_model=schemas.PhaseQuestionResponse)
def answer_question(question_id: int, answer_data: schemas.PhaseQuestionAnswer, db: Session = Depends(get_db)):
    if answer_data.answered_by_user_id and not crud.get_user(db, answer_data.answered_by_user_id):
        raise HTTPException(status_code=404, detail="Answering user not found")
    question = crud.answer_phase_question(db, question_id, answer_data)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


@router.post("/{question_id}/dismiss", response_model=schemas.PhaseQuestionResponse)
def dismiss_question(question_id: int, answered_by_user_id: int | None = None, db: Session = Depends(get_db)):
    if answered_by_user_id and not crud.get_user(db, answered_by_user_id):
        raise HTTPException(status_code=404, detail="Answering user not found")
    question = crud.dismiss_phase_question(db, question_id, answered_by_user_id=answered_by_user_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


@router.post("/{question_id}/auto-answer", response_model=schemas.PhaseQuestionResponse)
def auto_answer_question(question_id: int, db: Session = Depends(get_db)):
    question = crud.get_phase_question(db, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    audit = crud.get_audit(db, question.audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    owner = crud.get_user(db, question.assigned_user_id or audit.question_owner_user_id) if (question.assigned_user_id or audit.question_owner_user_id) else None
    if not owner or not owner.is_llm_user:
        raise HTTPException(status_code=409, detail="Question is not assigned to a fake AI user")
    phase_exec = db.query(PhaseExecution).filter(PhaseExecution.id == question.phase_execution_id).first()
    if not phase_exec:
        raise HTTPException(status_code=404, detail="Phase execution not found")
    auto_answer_open_questions(db, audit, phase_exec, owner, Path(audit.workspace_path), phase_exec.stdout_log or "")
    updated = crud.get_phase_question(db, question_id)
    return updated


@router.post("/audits/{audit_id}/write-answer-context")
def write_answer_context(audit_id: UUID, db: Session = Depends(get_db)):
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    path = write_user_answers_context(db, audit, Path(audit.workspace_path))
    return {"audit_id": str(audit_id), "path": str(path.relative_to(Path(audit.workspace_path)))}
