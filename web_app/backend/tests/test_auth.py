from types import SimpleNamespace
import asyncio

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app import crud, schemas
from app.auth import create_access_token, verify_access_token
from app.api import auth as auth_api
from app.api import websockets
from app.main import authenticated_user_from_bearer, require_api_auth


def test_access_token_roundtrip():
    user = SimpleNamespace(id=7, username="derek")
    token = create_access_token(user, expires_in_seconds=60)

    payload = verify_access_token(token)

    assert payload["sub"] == 7
    assert payload["username"] == "derek"


def test_access_token_rejects_tampering():
    user = SimpleNamespace(id=7, username="derek")
    token = create_access_token(user, expires_in_seconds=60)
    payload, signature = token.split(".", 1)
    tampered_payload = ("a" if payload[0] != "a" else "b") + payload[1:]
    tampered = f"{tampered_payload}.{signature}"

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


def test_websocket_user_from_token_accepts_active_user(monkeypatch):
    user = SimpleNamespace(id=7, username="derek", active=True)
    token = create_access_token(user, expires_in_seconds=60)
    monkeypatch.setattr(crud, "get_user", lambda db, user_id: user if user_id == 7 else None)

    assert websockets.websocket_user_from_token(token, object()) is user


def test_websocket_user_from_token_rejects_bad_token(monkeypatch):
    monkeypatch.setattr(crud, "get_user", lambda db, user_id: None)

    assert websockets.websocket_user_from_token("bad-token", object()) is None


def test_authenticated_user_from_bearer_rejects_inactive_user(monkeypatch):
    user = SimpleNamespace(id=7, username="derek", active=False)
    token = create_access_token(user, expires_in_seconds=60)
    monkeypatch.setattr(crud, "get_user", lambda db, user_id: user)

    with pytest.raises(HTTPException) as exc:
        authenticated_user_from_bearer(f"Bearer {token}", object())

    assert exc.value.status_code == 401
    assert "inactive" in exc.value.detail


def test_authenticated_user_from_bearer_rejects_missing_user(monkeypatch):
    user = SimpleNamespace(id=7, username="derek", active=True)
    token = create_access_token(user, expires_in_seconds=60)
    monkeypatch.setattr(crud, "get_user", lambda db, user_id: None)

    with pytest.raises(HTTPException) as exc:
        authenticated_user_from_bearer(f"Bearer {token}", object())

    assert exc.value.status_code == 401


class FakeUrl:
    def __init__(self, path):
        self.path = path


class FakeRequest:
    def __init__(self, path, headers=None, method="GET"):
        self.url = FakeUrl(path)
        self.headers = headers or {}
        self.method = method


def test_api_auth_middleware_allows_health_without_token():
    async def call_next(request):
        return JSONResponse({"ok": True})

    response = asyncio.run(require_api_auth(FakeRequest("/health"), call_next))

    assert response.status_code == 200
    assert response.body == b'{"ok":true}'


def test_api_auth_middleware_rejects_protected_route_without_token():
    async def call_next(request):
        return JSONResponse({"ok": True})

    response = asyncio.run(require_api_auth(FakeRequest("/api/audits/"), call_next))

    assert response.status_code == 401
    assert b"Missing bearer token" in response.body


def test_api_auth_middleware_rejects_invalid_token():
    async def call_next(request):
        return JSONResponse({"ok": True})

    response = asyncio.run(require_api_auth(FakeRequest("/api/audits/", {"authorization": "Bearer invalid-token"}), call_next))

    assert response.status_code == 401
