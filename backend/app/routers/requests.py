"""
Buy requests and chat.

  POST /requests                          buyer asks for a book (opens a chat)
  GET  /requests                          my inbox (as buyer and/or seller)
  GET  /requests/{id}                     one conversation's details
  POST /requests/{id}/accept              seller: yes -> book becomes RESERVED
  POST /requests/{id}/reject              seller: no
  POST /requests/{id}/cancel              buyer withdraws, or either side: deal fell through
  POST /requests/{id}/complete            seller: handed over -> book becomes SOLD
  GET  /requests/{id}/messages?after_id=  read chat (only messages newer than after_id)
  POST /requests/{id}/messages            send a chat message

THE STATE MACHINE (which status may change into which):

      pending --accept--> accepted --complete--> completed
         |                   |
       reject / cancel     cancel
         v                   v
     rejected / cancelled   cancelled  (book goes back to available)

Every change to a request that affects the book (reserve / release / sell)
happens in the SAME database commit, so the two can never disagree.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, col, func, or_, select

from ..blocking import is_blocked_between
from ..db import get_session
from ..models import Book, BookImage, BookStatus, BuyRequest, Message, RequestStatus, User, utcnow
from ..ratelimit import MESSAGE_LIMIT, REQUEST_LIMIT, check_rate_limit
from ..schemas import BookSummaryOut, BuyRequestCreate, BuyRequestOut, MessageCreate, MessageOut, PersonOut
from ..security import get_current_user, get_verified_user
from ..storage import public_url

router = APIRouter(prefix="/requests", tags=["requests & chat"])

SAFETY_TIP = (
    "Safety tip: never pay before you've seen the book in person. "
    "Meet in a public place on campus, check the book, then pay."
)
OPEN_STATUSES = (RequestStatus.pending, RequestStatus.accepted)


# ---------------------------------------------------------------- helpers
def add_system_message(db: Session, request_id: int, text: str) -> None:
    db.add(Message(request_id=request_id, sender_id=None, body=text))


def get_my_request(db: Session, request_id: int, user: User) -> BuyRequest:
    """
    Only the buyer and seller may see a conversation.
    Everyone else gets 404 (not 403), so they can't even learn that it exists.
    """
    req = db.get(BuyRequest, request_id)
    if req is None or user.id not in (req.buyer_id, req.seller_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return req


def to_message_out(m: Message, viewer: User) -> MessageOut:
    return MessageOut(
        id=m.id,
        body=m.body,
        created_at=m.created_at,
        sender_id=m.sender_id,
        is_mine=m.sender_id == viewer.id,
        is_system=m.sender_id is None,
    )


def to_request_out(db: Session, req: BuyRequest, viewer: User) -> BuyRequestOut:
    # Note: a few small queries per conversation. A person's inbox is short, so this is fine;
    # if inboxes ever get long we'd batch these like books.to_book_outs does.
    book = db.get(Book, req.book_id)
    buyer = db.get(User, req.buyer_id)
    seller = db.get(User, req.seller_id)
    first_image = db.exec(
        select(BookImage).where(BookImage.book_id == book.id).order_by(BookImage.position, BookImage.id)
    ).first()
    last = db.exec(
        select(Message).where(Message.request_id == req.id).order_by(col(Message.id).desc())
    ).first()

    my_role = "buyer" if viewer.id == req.buyer_id else "seller"
    last_read = req.buyer_last_read_at if my_role == "buyer" else req.seller_last_read_at
    unread_q = select(func.count()).select_from(Message).where(
        Message.request_id == req.id,
        or_(Message.sender_id.is_(None), Message.sender_id != viewer.id),  # not sent by me
    )
    if last_read is not None:
        unread_q = unread_q.where(Message.created_at > last_read)
    unread = db.exec(unread_q).one()

    return BuyRequestOut(
        id=req.id,
        status=req.status,
        my_role=my_role,
        book=BookSummaryOut(
            id=book.id, title=book.title, author=book.author, price=book.price, status=book.status,
            image_url=public_url(first_image.url) if first_image else None,
        ),
        buyer=PersonOut(id=buyer.id, name=buyer.name),
        seller=PersonOut(id=seller.id, name=seller.name),
        last_message=to_message_out(last, viewer) if last else None,
        unread_count=unread,
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


def reject_other_pending(db: Session, book_id: int, except_request_id: Optional[int], reason: str) -> None:
    """When a book is sold, every other waiting buyer is told politely and their request closes."""
    others = db.exec(
        select(BuyRequest).where(
            BuyRequest.book_id == book_id,
            BuyRequest.status == RequestStatus.pending,
            BuyRequest.id != (except_request_id or -1),
        )
    ).all()
    for other in others:
        other.status = RequestStatus.rejected
        other.updated_at = utcnow()
        db.add(other)
        add_system_message(db, other.id, reason)


def _touch(db: Session, req: BuyRequest) -> None:
    req.updated_at = utcnow()  # moves this conversation to the top of the inbox
    db.add(req)


def mark_read(db: Session, req: BuyRequest, user: User) -> None:
    """Everything in this chat up to now counts as seen by `user`."""
    if user.id == req.buyer_id:
        req.buyer_last_read_at = utcnow()
    else:
        req.seller_last_read_at = utcnow()
    db.add(req)


# ---------------------------------------------------------------- create + inbox
@router.post("", response_model=BuyRequestOut, status_code=status.HTTP_201_CREATED)
def create_request(data: BuyRequestCreate, user: User = Depends(get_verified_user), db: Session = Depends(get_session)):
    check_rate_limit(f"request:{user.id}", *REQUEST_LIMIT, "You've sent a lot of requests. Please try again later.")

    book = db.get(Book, data.book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Book not found.")
    if book.seller_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't request your own book.")
    if book.status != BookStatus.available:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This book is {book.status.value} and can't be requested.")
    if is_blocked_between(db, user.id, book.seller_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't contact this seller.")
    already = db.exec(
        select(BuyRequest).where(
            BuyRequest.book_id == book.id,
            BuyRequest.buyer_id == user.id,
            col(BuyRequest.status).in_(OPEN_STATUSES),
        )
    ).first()
    if already:
        raise HTTPException(status.HTTP_409_CONFLICT, "You've already requested this book.")

    req = BuyRequest(book_id=book.id, buyer_id=user.id, seller_id=book.seller_id)
    db.add(req)
    db.flush()  # gives req an id now, so messages can point to it (still one commit)
    add_system_message(db, req.id, SAFETY_TIP)
    if data.message and data.message.strip():
        db.add(Message(request_id=req.id, sender_id=user.id, body=data.message.strip()))
    mark_read(db, req, user)
    db.commit()
    db.refresh(req)
    return to_request_out(db, req, user)


@router.get("", response_model=list[BuyRequestOut])
def inbox(
    role: Literal["all", "buyer", "seller"] = "all",
    only_open: bool = Query(False, description="Only pending/accepted conversations"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    q = select(BuyRequest)
    if role == "buyer":
        q = q.where(BuyRequest.buyer_id == user.id)
    elif role == "seller":
        q = q.where(BuyRequest.seller_id == user.id)
    else:
        q = q.where(or_(BuyRequest.buyer_id == user.id, BuyRequest.seller_id == user.id))
    if only_open:
        q = q.where(col(BuyRequest.status).in_(OPEN_STATUSES))
    rows = db.exec(q.order_by(col(BuyRequest.updated_at).desc(), col(BuyRequest.id).desc())).all()
    return [to_request_out(db, r, user) for r in rows]


@router.get("/{request_id}", response_model=BuyRequestOut)
def get_request(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    return to_request_out(db, get_my_request(db, request_id, user), user)


# ---------------------------------------------------------------- the deal
@router.post("/{request_id}/accept", response_model=BuyRequestOut)
def accept(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    req = get_my_request(db, request_id, user)
    if user.id != req.seller_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the seller can accept.")
    if req.status != RequestStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This request is already {req.status.value}.")
    book = db.get(Book, req.book_id)
    if book.status != BookStatus.available:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This book is already reserved for another buyer. Cancel that deal first if it fell through.",
        )
    # Request and book change together, in one commit.
    req.status = RequestStatus.accepted
    _touch(db, req)
    book.status = BookStatus.reserved
    book.buyer_id = req.buyer_id
    book.updated_at = utcnow()
    db.add(book)
    add_system_message(db, req.id, "The seller accepted. The book is reserved for you. Agree on a time and place to meet.")
    mark_read(db, req, user)
    db.commit()
    db.refresh(req)
    return to_request_out(db, req, user)


@router.post("/{request_id}/reject", response_model=BuyRequestOut)
def reject(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    req = get_my_request(db, request_id, user)
    if user.id != req.seller_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the seller can reject.")
    if req.status != RequestStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This request is already {req.status.value}.")
    req.status = RequestStatus.rejected
    _touch(db, req)
    add_system_message(db, req.id, "The seller declined this request.")
    mark_read(db, req, user)
    db.commit()
    db.refresh(req)
    return to_request_out(db, req, user)


@router.post("/{request_id}/cancel", response_model=BuyRequestOut)
def cancel(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    """
    Buyer: withdraw a pending request, or back out of an accepted deal.
    Seller: back out of an accepted deal (for a pending one, use reject).
    If the deal was accepted, the book goes back to available.
    """
    req = get_my_request(db, request_id, user)
    is_seller = user.id == req.seller_id
    if req.status not in OPEN_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This request is already {req.status.value}.")
    if is_seller and req.status == RequestStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "To turn down a pending request, use reject.")

    was_accepted = req.status == RequestStatus.accepted
    req.status = RequestStatus.cancelled
    _touch(db, req)
    if was_accepted:
        book = db.get(Book, req.book_id)
        book.status = BookStatus.available
        book.buyer_id = None
        book.updated_at = utcnow()
        db.add(book)
    who = "The seller" if is_seller else "The buyer"
    add_system_message(
        db, req.id, f"{who} cancelled." + (" The book is available again." if was_accepted else "")
    )
    mark_read(db, req, user)
    db.commit()
    db.refresh(req)
    return to_request_out(db, req, user)


@router.post("/{request_id}/complete", response_model=BuyRequestOut)
def complete(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    req = get_my_request(db, request_id, user)
    if user.id != req.seller_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the seller can mark the deal complete.")
    if req.status != RequestStatus.accepted:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an accepted request can be completed.")
    req.status = RequestStatus.completed
    _touch(db, req)
    book = db.get(Book, req.book_id)
    book.status = BookStatus.sold
    book.buyer_id = req.buyer_id
    book.updated_at = utcnow()
    db.add(book)
    add_system_message(db, req.id, "Deal completed. The book is marked as sold. Happy reading!")
    reject_other_pending(db, book.id, req.id, "Sorry, this book has been sold to someone else.")
    mark_read(db, req, user)
    db.commit()
    db.refresh(req)
    return to_request_out(db, req, user)


# ---------------------------------------------------------------- chat
@router.get("/{request_id}/messages", response_model=list[MessageOut])
def read_messages(
    request_id: int,
    after_id: Optional[int] = Query(None, description="Only return messages newer than this id (for polling)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    POLLING: the app calls this every few seconds with the id of the newest message it already has.
    Usually the answer is an empty list - tiny and fast. New messages show up within seconds.
    """
    req = get_my_request(db, request_id, user)
    q = select(Message).where(Message.request_id == req.id)
    if after_id is not None:
        q = q.where(Message.id > after_id)
    messages = db.exec(q.order_by(col(Message.id).asc()).limit(200)).all()

    mark_read(db, req, user)  # opening the chat = reading it; resets my unread counter
    db.commit()
    return [to_message_out(m, user) for m in messages]


@router.post("/{request_id}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def send_message(
    request_id: int,
    data: MessageCreate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    req = get_my_request(db, request_id, user)
    if req.status not in OPEN_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "This conversation is closed.")
    other_id = req.seller_id if user.id == req.buyer_id else req.buyer_id
    if is_blocked_between(db, user.id, other_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't message this person.")
    body = data.body.strip()
    if not body:
        raise HTTPException(422, "Message can't be empty.")
    check_rate_limit(f"message:{user.id}", *MESSAGE_LIMIT, "You're sending messages too fast. Slow down a little.")

    msg = Message(request_id=req.id, sender_id=user.id, body=body)
    db.add(msg)
    _touch(db, req)
    mark_read(db, req, user)  # sending a message means I've seen everything before it
    db.commit()
    db.refresh(msg)
    return to_message_out(msg, user)
