"""
Database tables. Each class with table=True becomes one table.

Tables:
  College       - one row per real college (the "official" name)
  CollegeAlias  - other names people type for a college ("DU", "Delhi University")
  User          - a registered student
  AuthSession   - one row per logged-in device (the "wristband" / token)

  Book          - a listing (step 2)
  BookImage     - photos of a listing, up to 3 (step 2)

Buy requests and messages come in step 3.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

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
    available = "available"  # anyone can request it
    reserved = "reserved"    # seller agreed with a buyer, meetup pending
    sold = "sold"            # done; final


class Book(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    seller_id: int = Field(foreign_key="user.id", index=True)
    # Copied from the seller when the book is listed, so "books at my college"
    # is a simple filter on this table instead of a join through users.
    college_id: int = Field(foreign_key="college.id", index=True)

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
    buyer_id: Optional[int] = Field(default=None, foreign_key="user.id")  # filled in step 3

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
