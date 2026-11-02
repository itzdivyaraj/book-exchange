"""
Block helpers, shared by the books and conversations routers.

A block works in BOTH directions: if A blocks B, neither can message
the other, and they don't see each other's listings.
"""
from sqlmodel import Session, and_, or_, select

from .models import Block


def is_blocked_between(db: Session, user_a: int, user_b: int) -> bool:
    row = db.exec(
        select(Block).where(
            or_(
                and_(Block.blocker_id == user_a, Block.blocked_id == user_b),
                and_(Block.blocker_id == user_b, Block.blocked_id == user_a),
            )
        )
    ).first()
    return row is not None


def hidden_user_ids(db: Session, viewer_id: int) -> set[int]:
    """Everyone this viewer blocked, plus everyone who blocked this viewer."""
    rows = db.exec(
        select(Block).where(or_(Block.blocker_id == viewer_id, Block.blocked_id == viewer_id))
    ).all()
    return {r.blocked_id if r.blocker_id == viewer_id else r.blocker_id for r in rows}
