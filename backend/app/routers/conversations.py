"""
Conversations (chat between a buyer and a seller about one book).

  POST /conversations                          message a seller (starts the chat, or reopens it)
  GET  /conversations                          my inbox (as buyer and/or seller)
  GET  /conversations/{id}                     one conversation's details
  GET  /conversations/{id}/messages?after_id=  read the chat (only messages newer than after_id)
  POST /conversations/{id}/messages            send a message

Book Exchange is a listing site: it connects people, and they agree on price, place
and payment themselves in here. So there's no accept / reject / reserve step.
A chat only stops working if one person blocks the other or deletes their account.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session, col, func, or_, select

from ..blocking import is_blocked_between
from ..db import get_session
from ..models import Book, BookImage, BookStatus, Conversation, Message, User, utcnow
from ..ratelimit import CONVERSATION_LIMIT, MESSAGE_LIMIT, check_rate_limit
from ..schemas import BookSummaryOut, ConversationCreate, ConversationOut, MessageCreate, MessageOut, PersonOut
from ..security import get_current_user, get_verified_user
from ..storage import public_url

router = APIRouter(prefix="/conversations", tags=["conversations"])

WELCOME_NOTE = (
    "Book Exchange only connects you. Agree on the price, pickup and payment between yourselves, "
    "and never pay before you've seen the book. Share your phone number only if you're comfortable."
)


# ---------------------------------------------------------------- helpers
def add_system_message(db: Session, conversation_id: int, text: str) -> None:
    db.add(Message(conversation_id=conversation_id, sender_id=None, body=text))


def get_my_conversation(db: Session, conversation_id: int, user: User) -> Conversation:
    """
    Only the buyer and seller may see a conversation.
    Everyone else gets 404 (not 403), so they can't even learn that it exists.
    """
    conv = db.get(Conversation, conversation_id)
    if conv is None or user.id not in (conv.buyer_id, conv.seller_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return conv


def mark_read(db: Session, conv: Conversation, user: User) -> None:
    """Everything in this chat up to now counts as seen by `user`."""
    if user.id == conv.buyer_id:
        conv.buyer_last_read_at = utcnow()
    else:
        conv.seller_last_read_at = utcnow()
    db.add(conv)


def to_message_out(m: Message, viewer: User) -> MessageOut:
    return MessageOut(
        id=m.id,
        body=m.body,
        created_at=m.created_at,
        sender_id=m.sender_id,
        is_mine=m.sender_id == viewer.id,
        is_system=m.sender_id is None,
    )


def to_conversation_out(db: Session, conv: Conversation, viewer: User) -> ConversationOut:
    # A few small queries per conversation. Inboxes are short, so this is fine;
    # if they ever get long we'd batch these like books.to_book_outs does.
    book = db.get(Book, conv.book_id)
    buyer = db.get(User, conv.buyer_id)
    seller = db.get(User, conv.seller_id)
    first_image = db.exec(
        select(BookImage).where(BookImage.book_id == book.id).order_by(BookImage.position, BookImage.id)
    ).first()
    last = db.exec(
        select(Message).where(Message.conversation_id == conv.id).order_by(col(Message.id).desc())
    ).first()

    my_role = "buyer" if viewer.id == conv.buyer_id else "seller"
    last_read = conv.buyer_last_read_at if my_role == "buyer" else conv.seller_last_read_at
    unread_q = select(func.count()).select_from(Message).where(
        Message.conversation_id == conv.id,
        or_(Message.sender_id.is_(None), Message.sender_id != viewer.id),  # not sent by me
    )
    if last_read is not None:
        unread_q = unread_q.where(Message.created_at > last_read)

    return ConversationOut(
        id=conv.id,
        my_role=my_role,
        book=BookSummaryOut(
            id=book.id, title=book.title, author=book.author, price=book.price, city=book.city,
            status=book.status, image_url=public_url(first_image.url) if first_image else None,
        ),
        buyer=PersonOut(id=buyer.id, name=buyer.name),
        seller=PersonOut(id=seller.id, name=seller.name),
        last_message=to_message_out(last, viewer) if last else None,
        unread_count=db.exec(unread_q).one(),
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


# ---------------------------------------------------------------- start / inbox
@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def message_seller(
    data: ConversationCreate,
    response: Response,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    book = db.get(Book, data.book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Book not found.")
    if book.seller_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This is your own listing.")
    if is_blocked_between(db, user.id, book.seller_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't contact this seller.")

    conv = db.exec(
        select(Conversation).where(Conversation.book_id == book.id, Conversation.buyer_id == user.id)
    ).first()
    if conv is not None:
        response.status_code = status.HTTP_200_OK  # already chatting about this book: reopen it
    else:
        if book.status == BookStatus.sold:
            raise HTTPException(status.HTTP_409_CONFLICT, "This book has already been sold.")
        check_rate_limit(f"conv:{user.id}", *CONVERSATION_LIMIT, "You've messaged a lot of sellers. Please try again later.")
        conv = Conversation(book_id=book.id, buyer_id=user.id, seller_id=book.seller_id)
        db.add(conv)
        db.flush()  # gives conv an id now, so messages can point to it (still one commit)
        add_system_message(db, conv.id, WELCOME_NOTE)

    if data.message and data.message.strip():
        check_rate_limit(f"message:{user.id}", *MESSAGE_LIMIT, "You're sending messages too fast. Slow down a little.")
        db.add(Message(conversation_id=conv.id, sender_id=user.id, body=data.message.strip()))
        conv.updated_at = utcnow()
    mark_read(db, conv, user)
    db.commit()
    db.refresh(conv)
    return to_conversation_out(db, conv, user)


@router.get("", response_model=list[ConversationOut])
def inbox(
    role: Literal["all", "buyer", "seller"] = "all",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    q = select(Conversation)
    if role == "buyer":
        q = q.where(Conversation.buyer_id == user.id)
    elif role == "seller":
        q = q.where(Conversation.seller_id == user.id)
    else:
        q = q.where(or_(Conversation.buyer_id == user.id, Conversation.seller_id == user.id))
    rows = db.exec(q.order_by(col(Conversation.updated_at).desc(), col(Conversation.id).desc())).all()
    return [to_conversation_out(db, c, user) for c in rows]


@router.get("/{conversation_id}", response_model=ConversationOut)
def get_conversation(conversation_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    return to_conversation_out(db, get_my_conversation(db, conversation_id, user), user)


# ---------------------------------------------------------------- chat
@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def read_messages(
    conversation_id: int,
    after_id: Optional[int] = Query(None, description="Only return messages newer than this id (for polling)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    POLLING: the app calls this every few seconds with the id of the newest message it already has.
    Usually the answer is an empty list - tiny and fast. New messages show up within seconds.
    """
    conv = get_my_conversation(db, conversation_id, user)
    q = select(Message).where(Message.conversation_id == conv.id)
    if after_id is not None:
        q = q.where(Message.id > after_id)
    messages = db.exec(q.order_by(col(Message.id).asc()).limit(200)).all()
    mark_read(db, conv, user)  # opening the chat = reading it; resets my unread counter
    db.commit()
    return [to_message_out(m, user) for m in messages]


@router.post("/{conversation_id}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def send_message(
    conversation_id: int,
    data: MessageCreate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    conv = get_my_conversation(db, conversation_id, user)
    other = db.get(User, conv.seller_id if user.id == conv.buyer_id else conv.buyer_id)
    if other.is_deleted:
        raise HTTPException(status.HTTP_409_CONFLICT, "This person deleted their account.")
    if is_blocked_between(db, user.id, other.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't message this person.")
    body = data.body.strip()
    if not body:
        raise HTTPException(422, "Message can't be empty.")
    check_rate_limit(f"message:{user.id}", *MESSAGE_LIMIT, "You're sending messages too fast. Slow down a little.")

    msg = Message(conversation_id=conv.id, sender_id=user.id, body=body)
    db.add(msg)
    conv.updated_at = utcnow()  # moves this chat to the top of both inboxes
    mark_read(db, conv, user)   # sending a message means I've seen everything before it
    db.commit()
    db.refresh(msg)
    return to_message_out(msg, user)
