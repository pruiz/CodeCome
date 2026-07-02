from types import SimpleNamespace

from app.api import settings as app_settings


def test_code_server_settings_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "code-server-settings.json"
    monkeypatch.setattr(app_settings, "code_server_settings_path", lambda: path)
    monkeypatch.setattr(app_settings.settings, "CODE_SERVER_BIND_ADDR", "127.0.0.1")
    monkeypatch.setattr(app_settings.settings, "CODE_SERVER_PUBLIC_BASE_URL", "")

    default = app_settings.get_code_server_settings()
    assert default.bind_addr == "127.0.0.1"
    assert default.public_base_url == ""
    assert default.updated is False

    saved = app_settings.update_code_server_settings(SimpleNamespace(bind_addr="0.0.0.0", public_base_url="http://server.local/", updated=False))
    assert saved.bind_addr == "0.0.0.0"
    assert saved.public_base_url == "http://server.local"
    assert saved.updated is True

    loaded = app_settings.get_code_server_settings()
    assert loaded.bind_addr == "0.0.0.0"
    assert loaded.public_base_url == "http://server.local"
    assert loaded.updated is True
