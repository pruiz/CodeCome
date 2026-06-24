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


@router.get("/me", response_model=schemas.UserResponse)
def me(user: User = Depends(get_current_user)):
    return user
