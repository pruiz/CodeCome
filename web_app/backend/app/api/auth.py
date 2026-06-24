from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.auth import create_access_token, get_current_user
from app.database import get_db
from app.models import User

router = APIRouter()


@router.post("/login", response_model=schemas.AuthResponse)
def login(credentials: schemas.AuthLoginRequest, db: Session = Depends(get_db)):
    user = crud.get_user_by_username(db, credentials.username)
    if not user or not user.active or user.is_llm_user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not crud.verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return schemas.AuthResponse(access_token=create_access_token(user), user=user)


@router.get("/status")
def auth_status(db: Session = Depends(get_db)):
    return {"bootstrap_required": not crud.has_active_human_users(db)}


@router.post("/bootstrap", response_model=schemas.AuthResponse, status_code=201)
def bootstrap_first_user(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    if crud.has_active_human_users(db):
        raise HTTPException(status_code=409, detail="Bootstrap is disabled after first active human user exists")
    if user_data.is_llm_user:
        raise HTTPException(status_code=400, detail="Bootstrap user must be human")
    if not user_data.password:
        raise HTTPException(status_code=400, detail="Password is required")
    if crud.get_user_by_username(db, user_data.username):
        raise HTTPException(status_code=409, detail="Username already exists")
    user = crud.create_user(db, user_data)
    return schemas.AuthResponse(access_token=create_access_token(user), user=user)


@router.get("/me", response_model=schemas.UserResponse)
def me(user: User = Depends(get_current_user)):
    return user
