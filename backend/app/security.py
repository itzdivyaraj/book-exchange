"""
Everything about passwords and login tokens.

Job 1 - passwords:   bcrypt turns "shobhit123" into a one-way scramble. We store the scramble.
Job 2 - tokens:      after login we hand out a long random token (the "wristband").
                     The browser sends it back on every request in the header:
                         Authorization: Bearer <token>
                     get_current_user() looks it up and tells the route who is calling.
"""
import hashlib
import secrets
from datetime import timedelta

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select

from .config import SESSION_DAYS
from .db import get_session
from .models import AuthSession, User, utcnow


# ---------- Job 1: passwords ----------
def hash_password(password: str) -> str:
    # gensalt() adds random "salt" so two users with the same password get different scrambles.
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:  # deleted accounts have no password at all
        return False
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# ---------- Job 2: tokens ----------
def _fingerprint(token: str) -> str:
    """SHA-256 of the token. Fast and one-way; fine here because tokens are long and random."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user_id: int) -> str:
    token = secrets.token_urlsafe(32)  # ~43 random characters; impossible to guess
    db.add(
        AuthSession(
            user_id=user_id,
            token_hash=_fingerprint(token),
            expires_at=utcnow() + timedelta(days=SESSION_DAYS),
        )
    )
    db.commit()
    return token  # the real token goes to the browser ONCE; we only keep the fingerprint


def delete_session(db: Session, token: str) -> None:
    row = db.exec(select(AuthSession).where(AuthSession.token_hash == _fingerprint(token))).first()
    if row:
        db.delete(row)
        db.commit()


# auto_error=False so WE control the error message instead of FastAPI's default.
bearer_scheme = HTTPBearer(auto_error=False)

NOT_LOGGED_IN = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not logged in, or your session expired. Please log in again.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_token(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if creds is None or not creds.credentials:
        raise NOT_LOGGED_IN
    return creds.credentials


def get_current_user(
    token: str = Depends(get_current_token),
    db: Session = Depends(get_session),
) -> User:
    """
    Add `user: User = Depends(get_current_user)` to any route to make it login-only.
    FastAPI runs this first; if it raises 401, the route never runs.
    """
    row = db.exec(select(AuthSession).where(AuthSession.token_hash == _fingerprint(token))).first()
    if row is None:
        raise NOT_LOGGED_IN
    if row.expires_at < utcnow():
        db.delete(row)  # clean up the expired wristband
        db.commit()
        raise NOT_LOGGED_IN
    user = db.get(User, row.user_id)
    if user is None or user.is_deleted:
        raise NOT_LOGGED_IN
    return user


def get_verified_user(user: User = Depends(get_current_user)) -> User:
    """
    Like get_current_user, but ALSO requires a verified email.
    Used for actions that affect other people: listing books, requesting, messaging.
    """
    if not user.email_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Please verify your email first. Check your inbox for the 6-digit code.",
        )
    return user


def delete_all_sessions(db: Session, user_id: int, keep_token: str | None = None) -> None:
    """Log out everywhere (optionally keeping the current device logged in)."""
    keep = _fingerprint(keep_token) if keep_token else None
    for row in db.exec(select(AuthSession).where(AuthSession.user_id == user_id)).all():
        if row.token_hash != keep:
            db.delete(row)
    db.commit()


def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_session),
) -> User | None:
    """
    For PUBLIC pages that behave a little differently when you're logged in
    (e.g. browsing books shows "this is yours" on your own listings).
    No token or a bad token -> None (treated as a visitor), never an error.
    """
    if creds is None or not creds.credentials:
        return None
    try:
        return get_current_user(token=creds.credentials, db=db)
    except HTTPException:
        return None
