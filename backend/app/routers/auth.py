"""
Auth endpoints:
  POST /auth/signup   create account  -> returns token (you're logged in straight away)
  POST /auth/login    email + password -> returns token
  GET  /auth/me       who am I? (needs token)
  POST /auth/logout   delete this token (needs token)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..db import get_session
from ..models import College, User
from ..schemas import CollegeOut, LoginIn, SignupIn, TokenOut, UserOut
from ..security import (
    create_session,
    delete_session,
    get_current_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def to_user_out(db: Session, user: User) -> UserOut:
    college = db.get(College, user.college_id)
    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        college=CollegeOut.model_validate(college),
    )


@router.post("/signup", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def signup(data: SignupIn, db: Session = Depends(get_session)):
    email = data.email.lower()
    if db.exec(select(User).where(User.email == email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    if db.get(College, data.college_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please pick your college from the list.")

    user = User(
        name=data.name.strip(),
        email=email,
        password_hash=hash_password(data.password),  # the real password is never stored
        college_id=data.college_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)  # reload so user.id is filled in

    token = create_session(db, user.id)
    return TokenOut(token=token, user=to_user_out(db, user))


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_session)):
    user = db.exec(select(User).where(User.email == data.email.lower())).first()
    # Same message for "no such email" and "wrong password", so attackers
    # can't use this form to find out which emails are registered.
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password.")
    token = create_session(db, user.id)
    return TokenOut(token=token, user=to_user_out(db, user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    return to_user_out(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    _user: User = Depends(get_current_user),   # must be logged in to log out
    token: str = Depends(get_current_token),
    db: Session = Depends(get_session),
):
    delete_session(db, token)
