from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import json

from app import crud, schemas
from app.config import settings
from app.database import get_db

router = APIRouter()


def opencode_model_options(config_path=None) -> list[dict]:
    path = config_path or (settings.CODECOME_ROOT / "opencode.json")
    if not path.exists():
        return []
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    providers = config.get("provider") or {}
    options = []
    if not isinstance(providers, dict):
        return options
    for provider_name, provider_config in providers.items():
        models = (provider_config or {}).get("models") if isinstance(provider_config, dict) else None
        if not isinstance(models, dict):
            continue
        for model_name in models.keys():
            options.append({
                "id": f"{provider_name}/{model_name}",
                "provider": str(provider_name),
                "model": str(model_name),
            })
    return sorted(options, key=lambda item: item["id"])


@router.get("/models", response_model=schemas.ModelOptionListResponse)
def list_model_options():
    models = opencode_model_options()
    return schemas.ModelOptionListResponse(total=len(models), models=models)


@router.get("/", response_model=schemas.UserListResponse)
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    active: bool | None = Query(None),
    is_llm_user: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    total, users = crud.get_users(db, skip=skip, limit=limit, active=active, is_llm_user=is_llm_user)
    return schemas.UserListResponse(total=total, users=users)


@router.post("/", response_model=schemas.UserResponse, status_code=201)
def create_user(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = crud.get_user_by_username(db, user_data.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")
    if not user_data.is_llm_user and user_data.active and not user_data.password:
        raise HTTPException(status_code=400, detail="Password is required for active human users")
    return crud.create_user(db, user_data)


@router.get("/{user_id}", response_model=schemas.UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=schemas.UserResponse)
def update_user(user_id: int, user_data: schemas.UserUpdate, db: Session = Depends(get_db)):
    existing = crud.get_user(db, user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    data = user_data.model_dump(exclude_unset=True)
    will_be_human = data.get("is_llm_user", existing.is_llm_user) is False
    will_be_active = data.get("active", existing.active) is True
    has_password = bool(data.get("password") or existing.password_hash)
    if will_be_human and will_be_active and not has_password:
        raise HTTPException(status_code=400, detail="Password is required for active human users")
    if existing.active and not existing.is_llm_user and (not will_be_active or not will_be_human):
        if not crud.has_other_active_human_users(db, user_id):
            raise HTTPException(status_code=400, detail="Cannot disable or convert the last active human user")
    user = crud.update_user(db, user_id, user_data)
    return user
