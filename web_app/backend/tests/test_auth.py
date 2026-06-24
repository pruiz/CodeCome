from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import crud, schemas
from app.auth import create_access_token, verify_access_token
from app.api import auth as auth_api


def test_access_token_roundtrip():
    user = SimpleNamespace(id=7, username="derek")
    token = create_access_token(user, expires_in_seconds=60)

    payload = verify_access_token(token)

    assert payload["sub"] == 7
    assert payload["username"] == "derek"


def test_access_token_rejects_tampering():
    user = SimpleNamespace(id=7, username="derek")
    token = create_access_token(user, expires_in_seconds=60)
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")

    with pytest.raises(HTTPException):
        verify_access_token(tampered)


def test_human_user_can_verify_password():
    user = crud.create_user(SimpleNamespace(add=lambda obj: None, commit=lambda: None, refresh=lambda obj: setattr(obj, "id", 1)), schemas.UserCreate(
        username="human",
        password="secret",
    ))

    assert crud.verify_password("secret", user.password_hash) is True


def test_auth_status_reports_bootstrap_required(monkeypatch):
    monkeypatch.setattr(crud, "has_active_human_users", lambda db: False)

    assert auth_api.auth_status(object()) == {"bootstrap_required": True}
