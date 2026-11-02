"""
Database tables. Each class with table=True becomes one table.

Tables:
  College       - one row per real college (the "official" name)
  CollegeAlias  - other names people type for a college ("DU", "Delhi University")
  User          - a registered student
  AuthSession   - one row per logged-in device (the "wristband" / token)

  Book          - a listing (step 2)
  BookImage     - photos of a listing, up to 3 (step 2)

  Conversation  - a chat between a buyer and a seller about one book (step 3)
  Message       - one chat message (step 3)
  Report        - "this user/listing is a scam/spam/..." (step 3)
  Block         - "I don't want to hear from this person" (step 3)

  EmailCode     - 6-digit codes for verifying email / resetting password (step 4)
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Current time in UTC. We keep ALL times in UTC and convert to IST only when showing them."""
    return datetime.now(timezone.utc)


class College(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str                                   # official name, shown to users
    city: Optional[str] = None
    state: Optional[str] = None
    # Cleaned-up version of the name used for duplicate checks: "Delhi Univ." -> "delhi univ"
    normalized_name: str = Field(index=True, unique=True)
    # True = from our curated list. False = added by a user, not reviewed yet.
    is_verified: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class CollegeAlias(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    college_id: int = Field(foreign_key="college.id", index=True)
    alias: str                                  # what people type, e.g. "DU"
    normalized_alias: str = Field(index=True, unique=True)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str = Field(index=True, unique=True)  # stored lowercase
    # NOT the password. The bcrypt scramble of it. See security.py.
    password_hash: str
    college_id: int = Field(foreign_key="college.id", index=True)
    email_verified: bool = False   # step 4: must verify before listing/requesting/messaging
    is_deleted: bool = False       # step 4: account deleted; personal data erased
    created_at: datetime = Field(default_factory=utcnow)


class AuthSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    # We store a SHA-256 fingerprint of the token, not the token itself,
    # so even someone who steals the database can't log in as anyone.
    token_hash: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime


# ======================= Step 2: books =======================

class BookCondition(str, Enum):
    like_new = "like_new"   # barely used, no marks
    good = "good"           # some wear, a few notes
    fair = "fair"           # heavy highlighting, worn cover
    poor = "poor"           # usable but damaged


class BookStatus(str, Enum):
    available = "available"  # shown in Browse; people can message the seller
    sold = "sold"            # seller marked it sold (can switch back if a deal falls through)


class Book(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    seller_id: int = Field(foreign_key="user.id", index=True)
    # Copied from the seller when the book is listed, so "books at my college"
    # is a simple filter on this table instead of a join through users.
    college_id: int = Field(foreign_key="college.id", index=True)

    # Where the book can be picked up. Starts as the seller's college city, but they can change it.
    city: str = Field(index=True)
    title: str = Field(index=True)
    author: str = Field(index=True)
    edition: Optional[str] = None
    isbn: Optional[str] = None
    subject: Optional[str] = Field(default=None, index=True)
    semester: Optional[int] = None
    condition: BookCondition = BookCondition.good
    price: int                                   # whole rupees; 0 = giving it away free
    description: Optional[str] = None

    status: BookStatus = Field(default=BookStatus.available, index=True)

    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)


class BookImage(SQLModel, table=True):
    """One row per photo. One Book has many BookImages (one-to-many)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: int = Field(foreign_key="book.id", index=True)
    url: str          # where the browser loads it from
    storage_key: str  # how WE find it again to delete it (file name, or Cloudinary id later)
    position: int = 0 # display order
    created_at: datetime = Field(default_factory=utcnow)


# ======================= Step 3: conversations, safety =======================
# Book Exchange is a listing site: it connects buyers and sellers, who then agree on
# price, place and payment themselves in the chat. So a conversation has no "deal status".

class Conversation(SQLModel, table=True):
    # One conversation per (book, buyer). Messaging the same seller about the same book reopens it.
    __table_args__ = (UniqueConstraint("book_id", "buyer_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: int = Field(foreign_key="book.id", index=True)
    buyer_id: int = Field(foreign_key="user.id", index=True)
    seller_id: int = Field(foreign_key="user.id", index=True)  # copied from the book: quick "chats about my books"
    # When each side last opened the chat. Messages after this = unread.
    buyer_last_read_at: Optional[datetime] = None
    seller_last_read_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)  # last activity: sorts the inbox


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    sender_id: Optional[int] = Field(default=None, foreign_key="user.id")  # None = automatic system message
    body: str
    created_at: datetime = Field(default_factory=utcnow, index=True)


class ReportReason(str, Enum):
    scam = "scam"                    # asked for advance payment, fake listing, etc.
    spam = "spam"
    inappropriate = "inappropriate"
    wrong_info = "wrong_info"        # e.g. wrong book, wrong price, already sold
    other = "other"


class Report(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    reporter_id: int = Field(foreign_key="user.id", index=True)
    reported_user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    book_id: Optional[int] = Field(default=None, foreign_key="book.id")
    reason: ReportReason
    details: Optional[str] = None
    is_resolved: bool = False        # for the admin dashboard later
    created_at: datetime = Field(default_factory=utcnow)


class Block(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    blocker_id: int = Field(foreign_key="user.id", index=True)
    blocked_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)


# ======================= Step 4: email codes =======================

class CodePurpose(str, Enum):
    verify_email = "verify_email"
    reset_password = "reset_password"


class EmailCode(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    purpose: CodePurpose
    code_hash: str                  # fingerprint of the 6 digits, never the digits themselves
    attempts: int = 0               # wrong guesses so far
    expires_at: datetime
    used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)
