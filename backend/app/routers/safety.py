"""
Safety tools.

  POST   /reports              report a listing or a person
  POST   /blocks/{user_id}     block someone
  DELETE /blocks/{user_id}     unblock
  GET    /blocks               people I've blocked

What a block does (both directions, see blocking.py):
  - no new buy requests between the two people
  - no messages in existing chats
  - their listings are hidden from each other when browsing
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, col, select

from ..db import get_session
from ..models import Block, Book, Report, User
from ..ratelimit import REPORT_LIMIT, check_rate_limit
from ..schemas import BlockedUserOut, ReportCreate
from ..security import get_current_user

router = APIRouter(tags=["safety"])


@router.post("/reports", status_code=status.HTTP_201_CREATED)
def create_report(data: ReportCreate, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    if data.book_id is None and data.user_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Say which listing or person you're reporting.")
    check_rate_limit(f"report:{user.id}", *REPORT_LIMIT, "You've sent a lot of reports. Please try again later.")

    reported_user_id = data.user_id
    if data.book_id is not None:
        book = db.get(Book, data.book_id)
        if book is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Book not found.")
        reported_user_id = reported_user_id or book.seller_id  # reporting a listing also flags its seller
    if reported_user_id is not None and db.get(User, reported_user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    if reported_user_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't report yourself.")

    db.add(Report(
        reporter_id=user.id,
        reported_user_id=reported_user_id,
        book_id=data.book_id,
        reason=data.reason,
        details=data.details.strip() if data.details else None,
    ))
    db.commit()
    # We don't tell the reported person anything. The admin dashboard (later) reviews reports.
    return {"detail": "Thanks. We've received your report."}


@router.post("/blocks/{user_id}", status_code=status.HTTP_201_CREATED)
def block_user(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    if user_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't block yourself.")
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    exists = db.exec(select(Block).where(Block.blocker_id == user.id, Block.blocked_id == user_id)).first()
    if exists is None:  # blocking twice is harmless: same result
        db.add(Block(blocker_id=user.id, blocked_id=user_id))
        db.commit()
    return {"detail": "Blocked. You won't see each other's listings or messages."}


@router.delete("/blocks/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def unblock_user(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    row = db.exec(select(Block).where(Block.blocker_id == user.id, Block.blocked_id == user_id)).first()
    if row:
        db.delete(row)
        db.commit()


@router.get("/blocks", response_model=list[BlockedUserOut])
def my_blocks(user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    rows = db.exec(
        select(Block).where(Block.blocker_id == user.id).order_by(col(Block.created_at).desc())
    ).all()
    out = []
    for b in rows:
        other = db.get(User, b.blocked_id)
        out.append(BlockedUserOut(id=other.id, name=other.name, blocked_at=b.created_at))
    return out
