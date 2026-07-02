from types import SimpleNamespace

from app.workers import ai_tasks
from app.workers.phase_tasks import queue_failure_triage_if_enabled


def test_triage_enabled_defaults_to_true():
    assert ai_tasks.triage_enabled(None) is True
    assert ai_tasks.triage_enabled({"__audit_options": {}}) is True
    assert ai_tasks.triage_enabled({"__audit_options": {"failure_triage_enabled": False}}) is False


def test_normalize_decision_rejects_unknown_values():
    normalized = ai_tasks._normalize_decision({
        "decision": "delete_everything",
        "confidence": "certain",
        "recommended_env": ["bad"],
        "evidence": "one fact",
    })

    assert normalized["decision"] == "NEEDS_HUMAN"
    assert normalized["confidence"] == "LOW"
    assert normalized["recommended_env"] == {}
    assert normalized["evidence"] == ["one fact"]


def test_queue_failure_triage_respects_disabled_option(monkeypatch):
    calls = []

    class FakeCrud:
        @staticmethod
        def latest_phase_triage(db, phase_execution_id):
            calls.append(("latest", phase_execution_id))
            return None

        @staticmethod
        def create_audit_log(*args, **kwargs):
            calls.append(("log", args, kwargs))

    monkeypatch.setattr("app.workers.phase_tasks.crud", FakeCrud)

    audit = SimpleNamespace(id="audit-1", model_settings={"__audit_options": {"failure_triage_enabled": False}})
    phase_exec = SimpleNamespace(id=7, phase="phase-3")

    queue_failure_triage_if_enabled(object(), audit, phase_exec)

    assert calls == []


def test_queue_failure_triage_requires_fake_ai_owner(monkeypatch):
    calls = []

    class FakeCrud:
        @staticmethod
        def get_user(db, user_id):
            calls.append(("get_user", user_id))
            return None

        @staticmethod
        def create_audit_log(*args, **kwargs):
            calls.append(("log", args, kwargs))

    class FakeTask:
        @staticmethod
        def delay(*args):
            calls.append(("delay", args))

    monkeypatch.setattr("app.workers.phase_tasks.crud", FakeCrud)
    monkeypatch.setattr("app.workers.phase_tasks.triage_failed_phase_task", FakeTask, raising=False)

    audit = SimpleNamespace(id="audit-1", question_owner_user_id=None, model_settings={})
    phase_exec = SimpleNamespace(id=7, phase="phase-3")

    queue_failure_triage_if_enabled(object(), audit, phase_exec)

    assert not any(call[0] == "delay" for call in calls)
    assert any(call[0] == "log" for call in calls)


def test_triage_ai_user_requires_active_fake_ai_user():
    db = object()
    audit = SimpleNamespace(question_owner_user_id=3)

    class FakeCrud:
        @staticmethod
        def get_user(db_arg, user_id):
            assert db_arg is db
            assert user_id == 3
            return SimpleNamespace(active=True, is_llm_user=True, llm_model="local/model")

    original = ai_tasks.crud
    try:
        ai_tasks.crud = FakeCrud
        owner = ai_tasks.triage_ai_user(db, audit)
    finally:
        ai_tasks.crud = original

    assert owner.llm_model == "local/model"


def test_extract_json_from_fenced_block():
    parsed = ai_tasks._extract_json('before```json\n{"decision":"RERUN_SAME_OPTIONS"}\n```after')

    assert parsed == {"decision": "RERUN_SAME_OPTIONS"}
