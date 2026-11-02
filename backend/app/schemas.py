"""
Shapes of data going IN to and OUT of the API (Pydantic models).

WHY separate from models.py: the database row for a User has password_hash.
We must never send that back to the browser. So the API uses its own "public" shapes.
Pydantic also validates input automatically: bad email or short password -> 422 error.
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- Colleges ----------
class CollegeOut(BaseModel):
    # Lets Pydantic build this from a database College object (reads its attributes).
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    city: Optional[str] = None
    state: Optional[str] = None
    is_verified: bool


class CollegeCreate(BaseModel):
    name: str = Field(min_length=3, max_length=150)
    city: Optional[str] = Field(default=None, max_length=80)
    state: Optional[str] = Field(default=None, max_length=80)
    # Set to True when the user has seen our "did you mean...?" suggestions
    # and still says "no, mine is different".
    confirm_new: bool = False


class CollegeCreateResult(BaseModel):
    created: bool
    college: Optional[CollegeOut] = None        # the new (or exact existing) college
    suggestions: list[CollegeOut] = []          # close matches, if any


# ---------- Auth ----------
class SignupIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    # bcrypt only looks at the first 72 bytes, so we cap the length.
    password: str = Field(min_length=8, max_length=72)
    college_id: int


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    college: CollegeOut


class TokenOut(BaseModel):
    token: str
    user: UserOut


# ======================= Step 2: books =======================
from datetime import datetime  # noqa: E402
from typing import Literal  # noqa: E402

from .models import BookCondition, BookStatus  # noqa: E402


class BookCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    author: str = Field(min_length=2, max_length=150)
    edition: Optional[str] = Field(default=None, max_length=50)
    isbn: Optional[str] = Field(default=None, max_length=20)
    subject: Optional[str] = Field(default=None, max_length=100)
    semester: Optional[int] = Field(default=None, ge=1, le=12)
    condition: BookCondition = BookCondition.good
    price: int = Field(ge=0, le=100000, description="Whole rupees. 0 = free.")
    description: Optional[str] = Field(default=None, max_length=1000)
    # Set to true only after the user confirms "yes, this is a second copy".
    allow_duplicate: bool = False


class BookUpdate(BaseModel):
    """Every field optional: only the fields you send get changed (a 'partial update')."""
    title: Optional[str] = Field(default=None, min_length=2, max_length=200)
    author: Optional[str] = Field(default=None, min_length=2, max_length=150)
    edition: Optional[str] = Field(default=None, max_length=50)
    isbn: Optional[str] = Field(default=None, max_length=20)
    subject: Optional[str] = Field(default=None, max_length=100)
    semester: Optional[int] = Field(default=None, ge=1, le=12)
    condition: Optional[BookCondition] = None
    price: Optional[int] = Field(default=None, ge=0, le=100000)
    description: Optional[str] = Field(default=None, max_length=1000)


class BookStatusUpdate(BaseModel):
    # Only "sold" (sold outside the app). Reserved/completed happen through buy requests.
    status: Literal["sold"]


class BookImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    url: str
    position: int


class SellerOut(BaseModel):
    """What buyers may see about a seller. No email, no phone."""
    id: int
    name: str


class BookOut(BaseModel):
    id: int
    title: str
    author: str
    edition: Optional[str]
    isbn: Optional[str]
    subject: Optional[str]
    semester: Optional[int]
    condition: BookCondition
    price: int
    description: Optional[str]
    status: BookStatus
    created_at: datetime
    updated_at: datetime
    seller: SellerOut
    college: CollegeOut
    images: list[BookImageOut]
    is_mine: bool  # handy for the frontend: show "Edit" instead of "Request to buy"


class BookPage(BaseModel):
    """One page of search results."""
    items: list[BookOut]
    total: int      # how many books match in total
    page: int
    page_size: int
    pages: int      # total number of pages


SortOption = Literal["newest", "oldest", "price_low", "price_high"]


# ======================= Step 3: requests, chat, safety =======================
from .models import ReportReason, RequestStatus  # noqa: E402


class BuyRequestCreate(BaseModel):
    book_id: int
    message: Optional[str] = Field(default=None, max_length=1000, description="Optional first message to the seller")


class PersonOut(BaseModel):
    id: int
    name: str


class BookSummaryOut(BaseModel):
    """A small version of a book, for inbox rows."""
    id: int
    title: str
    author: str
    price: int
    status: BookStatus
    image_url: Optional[str] = None


class MessageOut(BaseModel):
    id: int
    body: str
    created_at: datetime
    sender_id: Optional[int]
    is_mine: bool
    is_system: bool  # automatic safety/status messages from the app itself


class BuyRequestOut(BaseModel):
    id: int
    status: RequestStatus
    my_role: Literal["buyer", "seller"]
    book: BookSummaryOut
    buyer: PersonOut
    seller: PersonOut
    last_message: Optional[MessageOut] = None
    unread_count: int
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


class ReportCreate(BaseModel):
    """Report a listing (book_id) or a person (user_id) - at least one of them."""
    book_id: Optional[int] = None
    user_id: Optional[int] = None
    reason: ReportReason
    details: Optional[str] = Field(default=None, max_length=1000)


class BlockedUserOut(BaseModel):
    id: int
    name: str
    blocked_at: datetime
