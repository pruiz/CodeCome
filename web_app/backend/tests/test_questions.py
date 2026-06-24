from uuid import uuid4

from app import crud, schemas


class FakeQuery:
    def __init__(self, row):
        self.row = row

    def filter(self, *args):
        return self

    def first(self):
        return self.row


class FakeDb:
    def __init__(self, row=None):
        self.row = row
        self.added = []
        self.commits = 0
        self.refreshed = []

    def add(self, obj):
        self.added.append(obj)
        self.row = obj

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1
        self.refreshed.append(obj)

    def query(self, *args):
        return FakeQuery(self.row)


def test_create_phase_question_sets_assignment_and_blocking():
    audit_id = uuid4()
    db = FakeDb()
    question = crud.create_phase_question(db, schemas.PhaseQuestionCreate(
        audit_id=audit_id,
        phase_execution_id=7,
        phase="phase-3",
        question="Should CC-0007 be rejected?",
        context="Phase 3 asked for a user decision.",
        assigned_user_id=3,
    ))

    assert question.audit_id == audit_id
    assert question.phase_execution_id == 7
    assert question.status == "OPEN"
    assert question.blocking is True
    assert question.assigned_user_id == 3
    assert db.added == [question]
    assert db.commits == 1


def test_answer_phase_question_marks_answered():
    db = FakeDb()
    question = crud.create_phase_question(db, schemas.PhaseQuestionCreate(
        audit_id=uuid4(),
        phase_execution_id=7,
        phase="phase-3",
        question="Should this be validated first?",
    ))

    answered = crud.answer_phase_question(db, question.id, schemas.PhaseQuestionAnswer(
        answer="Yes, validate it first.",
        answered_by_user_id=4,
    ))

    assert answered.status == "ANSWERED"
    assert answered.answer == "Yes, validate it first."
    assert answered.answered_by_user_id == 4
    assert answered.answered_at is not None


def test_dismiss_phase_question_marks_dismissed():
    db = FakeDb()
    question = crud.create_phase_question(db, schemas.PhaseQuestionCreate(
        audit_id=uuid4(),
        phase_execution_id=8,
        phase="phase-2",
        question="Should we ask the user?",
    ))

    dismissed = crud.dismiss_phase_question(db, question.id)

    assert dismissed.status == "DISMISSED"
    assert dismissed.answered_at is not None
