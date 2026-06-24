from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID

from app import crud, schemas
from app.database import get_db

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
