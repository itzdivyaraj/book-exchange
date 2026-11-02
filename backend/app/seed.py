"""
Loads the starter list of colleges (seed_colleges.json) into the database.

Safe to run every startup: it skips colleges and aliases that already exist.
To add more colleges later, edit the JSON file and restart the server.
"""
import json
from pathlib import Path

from sqlmodel import Session, select

from .college_matching import normalize
from .db import engine
from .models import College, CollegeAlias

SEED_FILE = Path(__file__).parent / "seed_colleges.json"


def seed_colleges() -> int:
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    added = 0
    with Session(engine) as db:
        for item in data:
            norm = normalize(item["name"])
            college = db.exec(select(College).where(College.normalized_name == norm)).first()
            if college is None:
                college = College(
                    name=item["name"],
                    city=item.get("city"),
                    state=item.get("state"),
                    normalized_name=norm,
                    is_verified=True,
                )
                db.add(college)
                db.commit()
                db.refresh(college)
                added += 1
            for alias in item.get("aliases", []):
                a_norm = normalize(alias)
                if a_norm == norm:
                    continue
                exists = db.exec(
                    select(CollegeAlias).where(CollegeAlias.normalized_alias == a_norm)
                ).first()
                if exists is None:
                    db.add(CollegeAlias(college_id=college.id, alias=alias, normalized_alias=a_norm))
            db.commit()
    return added
