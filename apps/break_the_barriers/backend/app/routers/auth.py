from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies import get_current_user
from backend.app.models import UserRegister, UserLogin, TokenResponse, UserInfo
from backend.app.models_db import DBUser
from backend.app.services.auth_service import hash_password, verify_password, create_access_token

router = APIRouter()


def _user_info(user: DBUser) -> UserInfo:
    return UserInfo(
        id=user.id,
        email=user.email,
        full_name=user.full_name or "",
        plan=user.plan,
        pages_limit=user.pages_limit,
        pages_used_this_month=user.pages_used_this_month,
    )


@router.post("/api/auth/register", response_model=TokenResponse)
def register(body: UserRegister, db: Session = Depends(get_db)):
    if db.query(DBUser).filter(DBUser.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = DBUser(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.email, user.plan)
    return TokenResponse(access_token=token, user=_user_info(user))


@router.post("/api/auth/login", response_model=TokenResponse)
def login(body: UserLogin, db: Session = Depends(get_db)):
    user = db.query(DBUser).filter(DBUser.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    # Reset quota if new calendar month
    now = datetime.now(timezone.utc)
    reset_at = user.pages_reset_at
    if reset_at is not None:
        if reset_at.tzinfo is None:
            reset_at = reset_at.replace(tzinfo=timezone.utc)
        if reset_at.year != now.year or reset_at.month != now.month:
            user.pages_used_this_month = 0
            user.pages_reset_at = now
            db.commit()
            db.refresh(user)
    token = create_access_token(user.id, user.email, user.plan)
    return TokenResponse(access_token=token, user=_user_info(user))


@router.get("/api/auth/me", response_model=UserInfo)
def me(current_user: DBUser = Depends(get_current_user)):
    return _user_info(current_user)
