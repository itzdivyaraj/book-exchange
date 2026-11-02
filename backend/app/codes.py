"""
6-digit one-time codes (for verifying email and resetting passwords).

Rules:
  - random 6 digits from `secrets` (safe randomness, not `random`)
  - stored only as a SHA-256 fingerprint
  - valid for CODE_MINUTES, one use only
  - CODE_MAX_ATTEMPTS wrong guesses and the code is dead
  - asking for a new code cancels the old ones
"""
import hashlib
import secrets
from datetime import timedelta

from sqlmodel import Session, select

from .config import CODE_MAX_ATTEMPTS, CODE_MINUTES
from .models import CodePurpose, EmailCode, utcnow


def _fingerprint(user_id: int, purpose: CodePurpose, code: str) -> str:
    # Mixing in the user id + purpose means the same 6 digits give different fingerprints
    # for different people/purposes.
    return hashlib.sha256(f"{user_id}:{purpose.value}:{code}".encode()).hexdigest()


def create_code(db: Session, user_id: int, purpose: CodePurpose) -> str:
    """Make a new code (cancelling any older unused ones) and return the 6 digits to email."""
    for old in db.exec(
        select(EmailCode).where(
            EmailCode.user_id == user_id, EmailCode.purpose == purpose, EmailCode.used_at.is_(None)
        )
    ).all():
        old.used_at = utcnow()  # mark as used = no longer valid
        db.add(old)

    code = f"{secrets.randbelow(1_000_000):06d}"  # 000000 - 999999
    db.add(
        EmailCode(
            user_id=user_id,
            purpose=purpose,
            code_hash=_fingerprint(user_id, purpose, code),
            expires_at=utcnow() + timedelta(minutes=CODE_MINUTES),
        )
    )
    db.commit()
    return code


class CodeError(ValueError):
    """Message is safe to show the user."""


def use_code(db: Session, user_id: int, purpose: CodePurpose, code: str) -> None:
    """Check a code. On success it's marked used. On failure raises CodeError (and counts the attempt)."""
    row = db.exec(
        select(EmailCode)
        .where(EmailCode.user_id == user_id, EmailCode.purpose == purpose, EmailCode.used_at.is_(None))
        .order_by(EmailCode.id.desc())
    ).first()
    if row is None or row.expires_at < utcnow():
        raise CodeError("This code has expired. Please ask for a new one.")
    if row.attempts >= CODE_MAX_ATTEMPTS:
        raise CodeError("Too many wrong attempts. Please ask for a new code.")

    # compare_digest takes the same time whether the first or last character differs,
    # so an attacker can't learn anything from how fast the answer comes back.
    if not secrets.compare_digest(row.code_hash, _fingerprint(user_id, purpose, code.strip())):
        row.attempts += 1
        db.add(row)
        db.commit()
        left = CODE_MAX_ATTEMPTS - row.attempts
        raise CodeError(f"Wrong code. {left} attempt{'s' if left != 1 else ''} left." if left else
                        "Too many wrong attempts. Please ask for a new code.")

    row.used_at = utcnow()
    db.add(row)
    db.commit()
