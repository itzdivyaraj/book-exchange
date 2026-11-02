"""
College endpoints:
  GET  /colleges?q=du      search-as-you-type for the signup page
  GET  /colleges/{id}      one college
  POST /colleges           "My college isn't listed" (with duplicate protection)
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from ..college_matching import find_exact, find_similar, normalize, search
from ..db import get_session
from ..models import College
from ..schemas import CollegeCreate, CollegeCreateResult, CollegeOut

router = APIRouter(prefix="/colleges", tags=["colleges"])


@router.get("", response_model=list[CollegeOut])
def search_colleges(
    q: str = Query(min_length=1, max_length=100, description="What the user typed"),
    db: Session = Depends(get_session),
):
    return search(db, q)


@router.get("/{college_id}", response_model=CollegeOut)
def get_college(college_id: int, db: Session = Depends(get_session)):
    college = db.get(College, college_id)
    if college is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "College not found.")
    return college


@router.post("", response_model=CollegeCreateResult)
def add_college(data: CollegeCreate, db: Session = Depends(get_session)):
    """
    Not logged in on purpose: people add their college DURING signup, before they have an account.

    1. Same name/alias already exists          -> return it, create nothing.
    2. Similar ones exist and user hasn't confirmed -> return suggestions, create nothing.
    3. Otherwise                                -> create it as unverified.
    """
    existing = find_exact(db, data.name)
    if existing:
        return CollegeCreateResult(created=False, college=CollegeOut.model_validate(existing))

    if not data.confirm_new:
        similar = find_similar(db, data.name)
        if similar:
            return CollegeCreateResult(
                created=False, suggestions=[CollegeOut.model_validate(c) for c in similar]
            )

    college = College(
        name=" ".join(data.name.split()),  # tidy extra spaces
        city=data.city.strip() if data.city else None,
        state=data.state.strip() if data.state else None,
        normalized_name=normalize(data.name),
        is_verified=False,
    )
    db.add(college)
    db.commit()
    db.refresh(college)
    return CollegeCreateResult(created=True, college=CollegeOut.model_validate(college))
