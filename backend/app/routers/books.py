"""
Book endpoints.

  GET    /books                         browse: search, filters, sorting, pages   (public)
  GET    /books/mine                    my listings, all statuses                 (login)
  GET    /books/{id}                    one book                                  (public)
  POST   /books                         create a listing                          (login)
  PATCH  /books/{id}                    edit details                              (owner)
  PATCH  /books/{id}/status             mark sold outside the app                 (owner)
  DELETE /books/{id}                    delete listing + its photos               (owner)
  POST   /books/{id}/images             upload a photo (max 3)                    (owner)
  DELETE /books/{id}/images/{image_id}  remove a photo                            (owner)

Authentication = "who are you?"   (step 1: get_current_user -> 401 if unknown)
Authorization  = "are you ALLOWED?" (this step: get_own_book -> 403 if not yours)
"""
import math
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlmodel import Session, col, func, or_, select

from ..blocking import hidden_user_ids
from ..config import MAX_IMAGES_PER_BOOK, MAX_UPLOAD_MB
from ..db import get_session
from ..models import (
    Book, BookCondition, BookImage, BookStatus, BuyRequest, College, Message, Report, RequestStatus, User, utcnow,
)
from ..schemas import (
    BookCreate,
    BookImageOut,
    BookOut,
    BookPage,
    BookStatusUpdate,
    BookUpdate,
    CollegeOut,
    SellerOut,
    SortOption,
)
from ..security import get_current_user, get_optional_user
from ..storage import BadImage, delete_image, process_image, public_url, save_image

router = APIRouter(prefix="/books", tags=["books"])


# ---------------------------------------------------------------- helpers
def to_book_outs(db: Session, books: list[Book], viewer: Optional[User]) -> list[BookOut]:
    """
    Turn database rows into API responses.

    Each book needs its seller, college and photos. Fetching those one book at a time
    would be 3 extra queries PER BOOK (60 for a page of 20 - the classic "N+1 problem").
    Instead we fetch all sellers in 1 query, all colleges in 1, all photos in 1.
    """
    if not books:
        return []
    seller_ids = {b.seller_id for b in books}
    college_ids = {b.college_id for b in books}
    book_ids = [b.id for b in books]

    sellers = {u.id: u for u in db.exec(select(User).where(col(User.id).in_(seller_ids))).all()}
    colleges = {c.id: c for c in db.exec(select(College).where(col(College.id).in_(college_ids))).all()}
    images: dict[int, list[BookImage]] = {bid: [] for bid in book_ids}
    for img in db.exec(
        select(BookImage).where(col(BookImage.book_id).in_(book_ids)).order_by(BookImage.position, BookImage.id)
    ).all():
        images[img.book_id].append(img)

    return [
        BookOut(
            **b.model_dump(exclude={"seller_id", "college_id", "buyer_id"}),
            seller=SellerOut(id=b.seller_id, name=sellers[b.seller_id].name),
            college=CollegeOut.model_validate(colleges[b.college_id]),
            images=[
                BookImageOut(id=i.id, url=public_url(i.url), position=i.position) for i in images[b.id]
            ],
            is_mine=viewer is not None and viewer.id == b.seller_id,
        )
        for b in books
    ]


def to_book_out(db: Session, book: Book, viewer: Optional[User]) -> BookOut:
    return to_book_outs(db, [book], viewer)[0]


def get_book_or_404(db: Session, book_id: int) -> Book:
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Book not found.")
    return book


def get_own_book(db: Session, book_id: int, user: User) -> Book:
    """The authorization check. Exists? (404) Yours? (403)"""
    book = get_book_or_404(db, book_id)
    if book.seller_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only change your own listings.")
    return book


def _escape_like(text: str) -> str:
    # In SQL LIKE, % and _ are wildcards. Escape them so searching "100%" means literally "100%".
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---------------------------------------------------------------- browse
@router.get("", response_model=BookPage)
def browse_books(
    q: Optional[str] = Query(None, max_length=100, description="Search title, author, subject or ISBN"),
    college_id: Optional[int] = Query(None, description="Only books at this college"),
    subject: Optional[str] = Query(None, max_length=100),
    semester: Optional[int] = Query(None, ge=1, le=12),
    condition: Optional[BookCondition] = None,
    min_price: Optional[int] = Query(None, ge=0),
    max_price: Optional[int] = Query(None, ge=0),
    book_status: BookStatus = Query(BookStatus.available, alias="status"),
    sort: SortOption = "newest",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_session),
    viewer: Optional[User] = Depends(get_optional_user),
):
    """
    Every query parameter is optional and they combine with AND, e.g.
    /books?q=physics&college_id=1&max_price=300&sort=price_low&page=2
    """
    filters = [Book.status == book_status]
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        # ilike = case-insensitive LIKE. Works on both SQLite and Postgres.
        filters.append(
            or_(
                col(Book.title).ilike(pattern, escape="\\"),
                col(Book.author).ilike(pattern, escape="\\"),
                col(Book.subject).ilike(pattern, escape="\\"),
                col(Book.isbn).ilike(pattern, escape="\\"),
            )
        )
    if college_id is not None:
        filters.append(Book.college_id == college_id)
    if subject:
        filters.append(col(Book.subject).ilike(f"%{_escape_like(subject.strip())}%", escape="\\"))
    if semester is not None:
        filters.append(Book.semester == semester)
    if condition is not None:
        filters.append(Book.condition == condition)
    if min_price is not None:
        filters.append(Book.price >= min_price)
    if max_price is not None:
        filters.append(Book.price <= max_price)
    if viewer is not None:
        hidden = hidden_user_ids(db, viewer.id)  # people blocked in either direction
        if hidden:
            filters.append(col(Book.seller_id).notin_(hidden))

    # 1) How many match in total? (for "Page 2 of 14")
    total = db.exec(select(func.count()).select_from(Book).where(*filters)).one()

    # 2) Fetch only this page's rows.
    order = {
        "newest": [col(Book.created_at).desc(), col(Book.id).desc()],
        "oldest": [col(Book.created_at).asc(), col(Book.id).asc()],
        "price_low": [col(Book.price).asc(), col(Book.id).desc()],
        "price_high": [col(Book.price).desc(), col(Book.id).desc()],
    }[sort]
    rows = db.exec(
        select(Book).where(*filters).order_by(*order).offset((page - 1) * page_size).limit(page_size)
    ).all()

    return BookPage(
        items=to_book_outs(db, list(rows), viewer),
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


# NOTE: /mine must be defined BEFORE /{book_id}, or FastAPI would try to read "mine" as a book id.
@router.get("/mine", response_model=list[BookOut])
def my_books(user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    rows = db.exec(
        select(Book).where(Book.seller_id == user.id).order_by(col(Book.created_at).desc(), col(Book.id).desc())
    ).all()
    return to_book_outs(db, list(rows), user)


@router.get("/{book_id}", response_model=BookOut)
def get_book(
    book_id: int,
    db: Session = Depends(get_session),
    viewer: Optional[User] = Depends(get_optional_user),
):
    return to_book_out(db, get_book_or_404(db, book_id), viewer)


# ---------------------------------------------------------------- create / edit / delete
@router.post("", response_model=BookOut, status_code=status.HTTP_201_CREATED)
def create_book(data: BookCreate, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    # Catch accidental double listings: same seller, same title + author, still available.
    if not data.allow_duplicate:
        twin = db.exec(
            select(Book).where(
                Book.seller_id == user.id,
                Book.status == BookStatus.available,
                func.lower(Book.title) == data.title.strip().lower(),
                func.lower(Book.author) == data.author.strip().lower(),
            )
        ).first()
        if twin:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"You already have this book listed (id {twin.id}). "
                "If it's a second copy, send allow_duplicate: true.",
            )
    fields = data.model_dump(exclude={"allow_duplicate"})
    fields["title"], fields["author"] = fields["title"].strip(), fields["author"].strip()
    book = Book(**fields, seller_id=user.id, college_id=user.college_id)
    db.add(book)
    db.commit()
    db.refresh(book)
    return to_book_out(db, book, user)


@router.patch("/{book_id}", response_model=BookOut)
def update_book(
    book_id: int,
    data: BookUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    book = get_own_book(db, book_id, user)
    if book.status == BookStatus.sold:
        raise HTTPException(status.HTTP_409_CONFLICT, "This book is sold and can't be edited.")
    # exclude_unset: only the fields the user actually sent. Missing fields stay as they were.
    changes = data.model_dump(exclude_unset=True)
    for required in ("title", "author", "price", "condition"):
        if required in changes and changes[required] is None:
            raise HTTPException(422, f"{required} can't be empty.")
    for field, value in changes.items():
        setattr(book, field, value)
    book.updated_at = utcnow()
    db.add(book)
    db.commit()
    db.refresh(book)
    return to_book_out(db, book, user)


@router.patch("/{book_id}/status", response_model=BookOut)
def change_status(
    book_id: int,
    data: BookStatusUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    "I sold it outside the app" -> sold. (The only manual change.)
    Reserving and completing a sale happen through buy requests (/requests),
    so the book and the conversation always agree.
    """
    from .requests import reject_other_pending  # imported here to avoid a circular import

    book = get_own_book(db, book_id, user)
    if book.status == BookStatus.sold:
        return to_book_out(db, book, user)
    if book.status == BookStatus.reserved:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This book is reserved for a buyer. Complete or cancel that deal in your requests instead.",
        )
    book.status = BookStatus.sold
    book.updated_at = utcnow()
    db.add(book)
    reject_other_pending(db, book.id, None, "Sorry, this book has been sold.")
    db.commit()
    db.refresh(book)
    return to_book_out(db, book, user)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    book = get_own_book(db, book_id, user)
    requests = db.exec(select(BuyRequest).where(BuyRequest.book_id == book.id)).all()
    if any(r.status in (RequestStatus.accepted, RequestStatus.completed) for r in requests):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This book has an accepted or completed deal, so it can't be deleted. "
            "Cancel the deal first, or keep it as sold.",
        )
    # Delete in order: things that POINT TO the book first, then the book itself.
    # (Postgres refuses to delete a row that other rows still point to.)
    for r in requests:
        for m in db.exec(select(Message).where(Message.request_id == r.id)).all():
            db.delete(m)
    db.flush()
    for r in requests:
        db.delete(r)
    for report in db.exec(select(Report).where(Report.book_id == book.id)).all():
        report.book_id = None  # keep the report for the admin, note what it was about
        report.details = f"[deleted listing: {book.title}] " + (report.details or "")
        db.add(report)
    for img in db.exec(select(BookImage).where(BookImage.book_id == book.id)).all():
        delete_image(img.storage_key)  # remove the actual file, not just the database row
        db.delete(img)
    db.flush()
    db.delete(book)
    db.commit()


# ---------------------------------------------------------------- photos
@router.post("/{book_id}/images", response_model=BookOut, status_code=status.HTTP_201_CREATED)
def upload_image(
    book_id: int,
    file: UploadFile = File(..., description=f"JPG, PNG or WEBP, max {MAX_UPLOAD_MB} MB"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    book = get_own_book(db, book_id, user)
    if book.status == BookStatus.sold:
        raise HTTPException(status.HTTP_409_CONFLICT, "This book is sold and can't be edited.")
    existing = db.exec(select(BookImage).where(BookImage.book_id == book.id)).all()
    if len(existing) >= MAX_IMAGES_PER_BOOK:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A listing can have at most {MAX_IMAGES_PER_BOOK} photos.")

    # Read at most limit+1 bytes: enough to know it's too big without loading a huge file into memory.
    raw = file.file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    try:
        jpeg = process_image(raw)
    except BadImage as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    url, key = save_image(jpeg)
    next_position = max((i.position for i in existing), default=-1) + 1
    db.add(BookImage(book_id=book.id, url=url, storage_key=key, position=next_position))
    book.updated_at = utcnow()
    db.add(book)
    db.commit()
    db.refresh(book)
    return to_book_out(db, book, user)


@router.delete("/{book_id}/images/{image_id}", response_model=BookOut)
def remove_image(
    book_id: int,
    image_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    book = get_own_book(db, book_id, user)
    img = db.get(BookImage, image_id)
    if img is None or img.book_id != book.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found on this listing.")
    delete_image(img.storage_key)
    db.delete(img)
    book.updated_at = utcnow()
    db.add(book)
    db.commit()
    db.refresh(book)
    return to_book_out(db, book, user)
