from uuid import uuid4

from app import crud, schemas
from app.workers import question_answering
from app.workers.question_detection import extract_open_questions, has_open_blocking_questions


class FakeQuery:
    def __init__(self, row):
        self.row = row

    def filter(self, *args):
        return self

    def first(self):
        return self.row

    def order_by(self, *args):
        return self

    def all(self):
        return [self.row] if self.row else []

    def scalar(self):
        return 1 if self.row else 0


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


def test_extract_open_questions_from_phase_output():
    output = """
Open questions for the user:

1 Should CC-0007 be rejected since the schema is already visible from source code review?
2 Should the information-disclosure findings be validated first?

Files modified:
- itemdb/findings/PENDING/CC-0001.md
"""

    assert extract_open_questions(output) == [
        "Should CC-0007 be rejected since the schema is already visible from source code review?",
        "Should the information-disclosure findings be validated first?",
    ]


def test_has_open_blocking_questions_uses_open_status(monkeypatch):
    class Question:
        def __init__(self, blocking):
            self.blocking = blocking

    monkeypatch.setattr(crud, "get_phase_questions", lambda db, phase_execution_id=None, status_filter=None: (1, [Question(True)]))

    assert has_open_blocking_questions(object(), 7) is True


def test_audit_has_open_blocking_questions():
    question = crud.create_phase_question(FakeDb(), schemas.PhaseQuestionCreate(
        audit_id=uuid4(),
        phase_execution_id=10,
        phase="phase-3",
        question="Should this block?",
    ))
    db = FakeDb(question)

    assert crud.audit_has_open_blocking_questions(db, question.audit_id) is True


def test_normalize_ai_answer_defaults_confidence():
    answer = question_answering.normalize_ai_answer({"answer": "Proceed with validation.", "confidence": "certain"})

    assert answer == {
        "answer": "Proceed with validation.",
        "confidence": "LOW",
        "reasoning": "",
    }


def test_with_user_answers_env_injects_context_file(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "user-answers-context.md").write_text("answers")

    env = question_answering.with_user_answers_env(tmp_path, {"CODECOME_THINKING": "0"})

    assert env["CODECOME_THINKING"] == "0"
    assert env["PROMPT_EXTRA_FILE"] == "runs/user-answers-context.md"


def test_auto_answer_open_questions_uses_fake_ai_user(monkeypatch, tmp_path):
    db = FakeDb()
    question = crud.create_phase_question(db, schemas.PhaseQuestionCreate(
        audit_id=uuid4(),
        phase_execution_id=9,
        phase="phase-3",
        question="Should we validate this first?",
    ))
    audit = type("Audit", (), {"id": question.audit_id, "name": "demo"})()
    phase_exec = type("PhaseExec", (), {"id": 9})()
    fake_user = type("User", (), {
        "id": 4,
        "display_name": "AI Reviewer",
        "is_llm_user": True,
        "auto_answer_enabled": True,
        "llm_model": "local/model",
        "llm_context": "Answer directly.",
    })()

    monkeypatch.setattr(question_answering, "generate_ai_answer", lambda *args, **kwargs: {
        "answer": "Yes, validate it first.",
        "confidence": "HIGH",
        "reasoning": "Simple path.",
    })

    answered = question_answering.auto_answer_open_questions(db, audit, phase_exec, fake_user, tmp_path)

    assert answered == 1
    assert question.status == "AUTO_ANSWERED"
    assert question.answer == "Yes, validate it first."
    assert question.answered_by_user_id == 4
    assert question.answer_model == "local/model"
    assert (tmp_path / "runs" / "user-answers-context.md").exists()
