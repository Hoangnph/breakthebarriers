from typing import Optional

from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models_db import DBUser
from backend.app.services.auth_service import decode_token


def get_optional_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[DBUser]:
    """Return DBUser if valid Bearer token present, else None (backward compat)."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token)
    except ValueError:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return db.query(DBUser).filter(DBUser.id == user_id).first()


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> DBUser:
    """Return DBUser or raise 401. Use on protected endpoints."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token claims", headers={"WWW-Authenticate": "Bearer"})
    user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
