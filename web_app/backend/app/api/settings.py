from pathlib import Path
import json

from fastapi import APIRouter

from app import schemas
from app.config import settings

router = APIRouter()


def settings_dir() -> Path:
    path = Path(settings.CODECOME_ROOT) / "web_app" / "backend" / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def code_server_settings_path() -> Path:
    return settings_dir() / "code-server-settings.json"


def default_code_server_settings() -> schemas.CodeServerSettings:
    return schemas.CodeServerSettings(
        bind_addr=settings.CODE_SERVER_BIND_ADDR,
        public_base_url=settings.CODE_SERVER_PUBLIC_BASE_URL,
        updated=False,
    )


def load_code_server_settings() -> schemas.CodeServerSettings:
    path = code_server_settings_path()
    if not path.exists():
        return default_code_server_settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_code_server_settings()
    return schemas.CodeServerSettings(
        bind_addr=str(data.get("bind_addr") or settings.CODE_SERVER_BIND_ADDR),
        public_base_url=str(data.get("public_base_url") or ""),
        updated=True,
    )


@router.get("/code-server", response_model=schemas.CodeServerSettings)
def get_code_server_settings():
    return load_code_server_settings()


@router.put("/code-server", response_model=schemas.CodeServerSettings)
def update_code_server_settings(config: schemas.CodeServerSettings):
    bind_addr = (config.bind_addr or "127.0.0.1").strip()
    public_base_url = (config.public_base_url or "").strip().rstrip("/")
    payload = {"bind_addr": bind_addr, "public_base_url": public_base_url}
    code_server_settings_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return schemas.CodeServerSettings(bind_addr=bind_addr, public_base_url=public_base_url, updated=True)
