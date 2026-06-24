from app import crud, schemas
from app.api import users as users_api
from fastapi import HTTPException


class FakeDb:
    def __init__(self, query_result=None):
        self.added = []
        self.commits = 0
        self.refreshed = []
        self.query_result = query_result

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1
        self.refreshed.append(obj)

    def query(self, *args):
        result = self.query_result

        class Query:
            def filter(self, *filter_args):
                return self

            def order_by(self, *order_args):
                return self

            def first(self):
                return result

        return Query()


def test_password_hash_verification_roundtrip():
    hashed = crud.hash_password("secret-password")

    assert hashed != "secret-password"
    assert crud.verify_password("secret-password", hashed) is True
    assert crud.verify_password("wrong", hashed) is False


def test_create_fake_ai_user_sets_llm_fields():
    db = FakeDb()
    data = schemas.UserCreate(
        username="strict-reviewer",
        display_name="Strict Reviewer",
        is_llm_user=True,
        llm_model="local/qwen3.6-27b",
        llm_context="Answer conservatively.",
        auto_answer_enabled=True,
    )

    user = crud.create_user(db, data)

    assert user.username == "strict-reviewer"
    assert user.display_name == "Strict Reviewer"
    assert user.is_llm_user is True
    assert user.llm_model == "local/qwen3.6-27b"
    assert user.llm_context == "Answer conservatively."
    assert user.auto_answer_enabled is True
    assert user.active is True
    assert user.password_hash is None
    assert db.added == [user]
    assert db.commits == 1


def test_create_human_user_hashes_password():
    db = FakeDb()
    data = schemas.UserCreate(
        username="derek",
        password="secret-password",
        llm_model="local/hidden",
        llm_context="hidden context",
        auto_answer_enabled=True,
    )

    user = crud.create_user(db, data)

    assert user.display_name == "derek"
    assert user.is_llm_user is False
    assert user.password_hash != "secret-password"
    assert crud.verify_password("secret-password", user.password_hash) is True
    assert user.llm_model is None
    assert user.llm_context is None
    assert user.auto_answer_enabled is False


def test_default_question_owner_returns_first_active_human():
    owner = type("User", (), {"id": 3, "username": "owner"})()

    assert crud.default_question_owner(FakeDb(owner)) is owner


def test_opencode_model_options_reads_provider_models(tmp_path):
    config = tmp_path / "opencode.json"
    config.write_text('{"provider":{"local":{"models":{"qwen":{},"llama":{}}}}}')

    assert users_api.opencode_model_options(config) == [
        {"id": "local/llama", "provider": "local", "model": "llama"},
        {"id": "local/qwen", "provider": "local", "model": "qwen"},
    ]


def test_opencode_model_options_reads_jsonc_comments():
    text = '''{
      // local provider
      "provider": {
        "local": {
          "models": {
            "qwen": {}
          }
        }
      }
    }'''

    assert users_api.opencode_model_options_from_text(text) == [
        {"id": "local/qwen", "provider": "local", "model": "qwen"},
    ]


def test_user_model_options_endpoint(monkeypatch):
    monkeypatch.setattr(users_api, "opencode_model_options", lambda: [{"id": "local/qwen", "provider": "local", "model": "qwen"}])

    response = users_api.list_model_options()

    assert response.total == 1
    assert response.models[0].id == "local/qwen"


def test_update_human_user_clears_llm_fields():
    existing = type("User", (), {
        "id": 1,
        "display_name": "Human",
        "active": True,
        "is_llm_user": False,
        "password_hash": "hash",
        "llm_model": "local/old",
        "llm_context": "old context",
        "auto_answer_enabled": True,
    })()

    class Db(FakeDb):
        def query(self, *args):
            class Query:
                def filter(self, *filter_args):
                    return self

                def first(self):
                    return existing

            return Query()

    updated = crud.update_user(Db(), 1, schemas.UserUpdate(display_name="Human Updated"))

    assert updated.display_name == "Human Updated"
    assert updated.llm_model is None
    assert updated.llm_context is None
    assert updated.auto_answer_enabled is False


def test_update_fake_ai_user_clears_password_hash():
    existing = type("User", (), {
        "id": 2,
        "display_name": "AI",
        "active": True,
        "is_llm_user": True,
        "password_hash": "hash",
        "llm_model": None,
        "llm_context": None,
        "auto_answer_enabled": True,
    })()

    class Db(FakeDb):
        def query(self, *args):
            class Query:
                def filter(self, *filter_args):
                    return self

                def first(self):
                    return existing

            return Query()

    updated = crud.update_user(Db(), 2, schemas.UserUpdate(llm_model="local/model"))

    assert updated.llm_model == "local/model"
    assert updated.password_hash is None


def test_create_active_human_user_requires_password():
    db = FakeDb()

    try:
        users_api.create_user(schemas.UserCreate(username="human", is_llm_user=False, active=True), db=db)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "Password is required" in exc.detail
    else:
        raise AssertionError("Expected HTTPException")


def test_cannot_disable_last_active_human_user(monkeypatch):
    existing = type("User", (), {
        "id": 1,
        "active": True,
        "is_llm_user": False,
        "password_hash": "hash",
    })()
    monkeypatch.setattr(crud, "get_user", lambda db, user_id: existing)
    monkeypatch.setattr(crud, "has_other_active_human_users", lambda db, user_id: False)

    try:
        users_api.update_user(1, schemas.UserUpdate(active=False), db=FakeDb())
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "last active human" in exc.detail
    else:
        raise AssertionError("Expected HTTPException")


def test_can_disable_human_user_when_another_active_human_exists(monkeypatch):
    existing = type("User", (), {
        "id": 1,
        "active": True,
        "is_llm_user": False,
        "password_hash": "hash",
    })()
    updated = type("User", (), {
        "id": 1,
        "username": "human",
        "display_name": "Human",
        "active": False,
        "is_llm_user": False,
        "auto_answer_enabled": True,
        "created_at": None,
        "updated_at": None,
    })()
    monkeypatch.setattr(crud, "get_user", lambda db, user_id: existing)
    monkeypatch.setattr(crud, "has_other_active_human_users", lambda db, user_id: True)
    monkeypatch.setattr(crud, "update_user", lambda db, user_id, user_data: updated)

    assert users_api.update_user(1, schemas.UserUpdate(active=False), db=FakeDb()) is updated
