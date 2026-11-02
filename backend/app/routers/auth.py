"""
Auth endpoints:
  POST /auth/signup               create account -> token + a verification code is emailed
  POST /auth/login                email + password -> token
  GET  /auth/me                   who am I? (needs token)
  POST /auth/logout               delete this token (needs token)

  Step 4:
  POST /auth/verify-email         6-digit code -> email_verified = true
  POST /auth/resend-verification  send a fresh code
  POST /auth/forgot-password      email a reset code (same answer whether or not the email exists)
  POST /auth/reset-password       email + code + new password -> logged out everywhere
  POST /auth/change-password      old + new password (logged in) -> other devices logged out
  POST /auth/delete-account       password -> personal data erased
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, col, or_, select

from ..codes import CodeError, create_code, use_code
from ..config import CODE_MINUTES
from ..db import get_session
from ..emailer import send_reset_code, send_verification_code
from ..models import (
    AuthSession, Block, Book, BookImage, BookStatus, BuyRequest, CodePurpose, College, EmailCode,
    Message, RequestStatus, User, utcnow,
)
from ..ratelimit import (
    FORGOT_LIMIT, LOGIN_LIMIT, RESEND_CODE_HOURLY, RESEND_CODE_LIMIT, check_rate_limit,
)
from ..schemas import (
    ChangePasswordIn, CollegeOut, DeleteAccountIn, ForgotPasswordIn, LoginIn, ResetPasswordIn,
    SignupIn, TokenOut, UserOut, VerifyEmailIn,
)
from ..security import (
    create_session,
    delete_all_sessions,
    delete_session,
    get_current_token,
    get_current_user,
    hash_password,
    verify_password,
)
from ..storage import delete_image

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("uvicorn.error")


def to_user_out(db: Session, user: User) -> UserOut:
    college = db.get(College, user.college_id)
    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        email_verified=user.email_verified,
        college=CollegeOut.model_validate(college),
    )


def _send_verification(db: Session, user: User) -> None:
    code = create_code(db, user.id, CodePurpose.verify_email)
    try:
        send_verification_code(user.email, user.name, code, CODE_MINUTES)
    except Exception:  # an email hiccup shouldn't break signup; they can press "resend"
        log.exception("Could not send verification email")


# ---------------------------------------------------------------- signup / login
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

    _send_verification(db, user)
    token = create_session(db, user.id)
    return TokenOut(token=token, user=to_user_out(db, user))


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_session)):
    # Max 10 tries per 5 minutes for one email: stops bots guessing passwords.
    check_rate_limit(
        f"login:{data.email.lower()}", *LOGIN_LIMIT,
        "Too many login attempts. Please wait a few minutes and try again.",
    )
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


# ---------------------------------------------------------------- email verification
@router.post("/verify-email", response_model=UserOut)
def verify_email(data: VerifyEmailIn, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    if user.email_verified:
        return to_user_out(db, user)
    try:
        use_code(db, user.id, CodePurpose.verify_email, data.code)
    except CodeError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    user.email_verified = True
    db.add(user)
    db.commit()
    db.refresh(user)
    return to_user_out(db, user)


@router.post("/resend-verification")
def resend_verification(user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    if user.email_verified:
        return {"detail": "Your email is already verified."}
    check_rate_limit(f"resend:{user.id}", *RESEND_CODE_LIMIT, "Please wait a minute before asking for another code.")
    check_rate_limit(f"resend-h:{user.id}", *RESEND_CODE_HOURLY, "Too many codes requested. Please try again later.")
    _send_verification(db, user)
    return {"detail": f"A new code has been sent to {user.email}."}


# ---------------------------------------------------------------- passwords
FORGOT_ANSWER = {"detail": "If an account exists for that email, we've sent a reset code. It expires in 15 minutes."}


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordIn, db: Session = Depends(get_session)):
    """
    Always the SAME answer, whether or not the email is registered.
    Otherwise this form would tell strangers who has an account.
    """
    email = data.email.lower()
    check_rate_limit(f"forgot:{email}", *FORGOT_LIMIT, "Too many reset requests. Please try again in 15 minutes.")
    user = db.exec(select(User).where(User.email == email)).first()
    if user is not None:
        code = create_code(db, user.id, CodePurpose.reset_password)
        try:
            send_reset_code(user.email, user.name, code, CODE_MINUTES)
        except Exception:
            log.exception("Could not send reset email")
    return FORGOT_ANSWER


@router.post("/reset-password")
def reset_password(data: ResetPasswordIn, db: Session = Depends(get_session)):
    user = db.exec(select(User).where(User.email == data.email.lower())).first()
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This code has expired. Please ask for a new one.")
    try:
        use_code(db, user.id, CodePurpose.reset_password, data.code)
    except CodeError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    user.password_hash = hash_password(data.new_password)
    user.email_verified = True  # they just proved they can read this inbox
    db.add(user)
    db.commit()
    delete_all_sessions(db, user.id)  # if someone else was logged in, they're kicked out now
    return {"detail": "Password changed. Please log in with your new password."}


@router.post("/change-password")
def change_password(
    data: ChangePasswordIn,
    user: User = Depends(get_current_user),
    token: str = Depends(get_current_token),
    db: Session = Depends(get_session),
):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is wrong.")
    user.password_hash = hash_password(data.new_password)
    db.add(user)
    db.commit()
    delete_all_sessions(db, user.id, keep_token=token)  # stay logged in here, log out other devices
    return {"detail": "Password changed. Other devices have been logged out."}


# ---------------------------------------------------------------- delete account
@router.post("/delete-account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(data: DeleteAccountIn, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    """
    Erase personal data while keeping other people's chats and sale history readable.
    (Deleting the user row outright would break every conversation they were part of.)
    """
    from .books import remove_book  # imported here to avoid a circular import
    from .requests import add_system_message

    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Wrong password.")
    uid = user.id

    # 1. Close their open deals and tell the other person.
    open_reqs = db.exec(
        select(BuyRequest).where(
            or_(BuyRequest.buyer_id == uid, BuyRequest.seller_id == uid),
            col(BuyRequest.status).in_([RequestStatus.pending, RequestStatus.accepted]),
        )
    ).all()
    for r in open_reqs:
        if r.status == RequestStatus.accepted:
            book = db.get(Book, r.book_id)
            book.status = BookStatus.available
            book.buyer_id = None
            db.add(book)
        r.status = RequestStatus.cancelled
        r.updated_at = utcnow()
        db.add(r)
        add_system_message(db, r.id, "This person deleted their account. The conversation is closed.")
    db.flush()

    # 2. Their listings: unsold ones are removed completely; sold ones stay as history, minus photos.
    for book in db.exec(select(Book).where(Book.seller_id == uid)).all():
        if book.status == BookStatus.sold:
            for img in db.exec(select(BookImage).where(BookImage.book_id == book.id)).all():
                delete_image(img.storage_key)
                db.delete(img)
            book.description = None
            db.add(book)
        else:
            remove_book(db, book)
    db.flush()

    # 3. Words they wrote in chats.
    for m in db.exec(select(Message).where(Message.sender_id == uid)).all():
        m.body = "[message deleted]"
        db.add(m)

    # 4. Things that only matter to them.
    for row in db.exec(select(Block).where(or_(Block.blocker_id == uid, Block.blocked_id == uid))).all():
        db.delete(row)
    for row in db.exec(select(EmailCode).where(EmailCode.user_id == uid)).all():
        db.delete(row)
    for row in db.exec(select(AuthSession).where(AuthSession.user_id == uid)).all():
        db.delete(row)

    # 5. The person themselves: keep the row (other rows point to it), erase who they were.
    user.name = "Deleted user"
    user.email = f"deleted-{uid}@deleted.invalid"  # frees up their real email for a future signup
    user.password_hash = ""                         # no password can ever match
    user.email_verified = False
    user.is_deleted = True
    db.add(user)
    db.commit()
