"""
Solving the "DU vs Delhi University vs University of Delhi" problem.

Three layers of defence:
  1. A curated list of real colleges (seed_colleges.json), each with known aliases.
     Users PICK from a search box instead of typing freely.
  2. normalize(): "Delhi Univ." and "delhi  university" become the same string,
     so exact duplicates are impossible (the DB column is unique).
  3. find_similar(): fuzzy matching + acronyms. Before creating a new college we show
     "Did you mean University of Delhi?". Only if the user insists do we create it,
     marked is_verified=False so an admin can merge it later.

All of this uses only Python's standard library (difflib, re) - no paid service.
"""
import re
from difflib import SequenceMatcher

from sqlmodel import Session, select

from .models import College, CollegeAlias

# Short forms people use, expanded so they compare equal to the long form.
ABBREVIATIONS = {
    "univ": "university", "uni": "university", "varsity": "university",
    "clg": "college", "coll": "college", "col": "college",
    "inst": "institute", "instt": "institute",
    "tech": "technology", "engg": "engineering", "eng": "engineering",
    "mgmt": "management", "sci": "science", "govt": "government",
    "natl": "national", "intl": "international",
}
# Words that don't help tell colleges apart.
STOP_WORDS = {"of", "the", "and", "for", "at", "in"}


def normalize(text: str) -> str:
    """Lowercase, '&' -> 'and', drop punctuation, squash spaces. 'Delhi Univ.' -> 'delhi univ'"""
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> list[str]:
    words = [ABBREVIATIONS.get(w, w) for w in normalize(text).split()]
    return [w for w in words if w not in STOP_WORDS]


def match_key(text: str) -> str:
    """
    Word-order-independent key: 'University of Delhi' and 'Delhi University'
    both become 'delhi university'.
    """
    return " ".join(sorted(_tokens(text)))


def acronym(text: str) -> str:
    """'Jawaharlal Nehru University' -> 'jnu'"""
    return "".join(w[0] for w in _tokens(text))


def similarity(a: str, b: str) -> float:
    """0.0 (nothing alike) to 1.0 (same)."""
    ka, kb = match_key(a), match_key(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    compact = normalize(a).replace(" ", "")
    if len(compact) >= 2 and compact == acronym(b):
        return 0.95  # user typed the initials
    # Compare the words that actually identify a college ("punjab" vs "panjab"),
    # ignoring words every college shares ("university"), otherwise
    # "Punjab University" looks 70% similar to "Gujarat University".
    da, db_ = _distinctive(ka), _distinctive(kb)
    if da and db_:
        return SequenceMatcher(None, da, db_).ratio()
    return SequenceMatcher(None, ka, kb).ratio()


GENERIC_WORDS = {
    "university", "college", "institute", "technology", "technological",
    "science", "sciences", "school", "academy", "education", "higher",
}


def _is_generic(word: str) -> bool:
    # Also catches typos: "univeristy" is still "university".
    return word in GENERIC_WORDS or any(
        SequenceMatcher(None, word, g).ratio() >= 0.85 for g in GENERIC_WORDS
    )


def _distinctive(key: str) -> str:
    return " ".join(w for w in key.split() if not _is_generic(w))


def find_exact(db: Session, text: str) -> College | None:
    """Same college already exists under this exact name or alias (after normalizing)?"""
    norm = normalize(text)
    college = db.exec(select(College).where(College.normalized_name == norm)).first()
    if college:
        return college
    alias = db.exec(select(CollegeAlias).where(CollegeAlias.normalized_alias == norm)).first()
    return db.get(College, alias.college_id) if alias else None


def find_similar(db: Session, text: str, limit: int = 5, threshold: float = 0.8) -> list[College]:
    """
    Compare against every college name and alias and return the closest ones.
    Fine for a few thousand colleges. (Later, Postgres's pg_trgm extension can do this in the DB.)
    """
    scores: dict[int, float] = {}
    for c in db.exec(select(College)).all():
        scores[c.id] = similarity(text, c.name)
    for a in db.exec(select(CollegeAlias)).all():
        scores[a.college_id] = max(scores.get(a.college_id, 0.0), similarity(text, a.alias))
    best = sorted(
        (cid for cid, s in scores.items() if s >= threshold),
        key=lambda cid: scores[cid],
        reverse=True,
    )[:limit]
    return [db.get(College, cid) for cid in best]


def search(db: Session, query: str, limit: int = 10) -> list[College]:
    """
    Powers the search-as-you-type box on the signup page.
    Ranking: exact alias/name > name starts with query > contains query > fuzzy match.
    """
    q = normalize(query)
    if not q:
        return []
    ranked: dict[int, float] = {}  # college_id -> rank (lower is better)

    def bump(cid: int, rank: float) -> None:
        ranked[cid] = min(ranked.get(cid, 99), rank)

    # Very short queries like "du" appear inside lots of words ("Hindu", "education"),
    # so for those we only match the start of a name/nickname, not the middle.
    allow_contains = len(q) >= 3
    allow_fuzzy = len(q) >= 4

    for c in db.exec(select(College)).all():
        if c.normalized_name == q:
            bump(c.id, 0)
        elif c.normalized_name.startswith(q):
            bump(c.id, 1)
        elif allow_contains and q in c.normalized_name:
            bump(c.id, 2)
    for a in db.exec(select(CollegeAlias)).all():
        if a.normalized_alias == q:
            bump(a.college_id, 0)
        elif a.normalized_alias.startswith(q):
            bump(a.college_id, 1)
        elif allow_contains and q in a.normalized_alias:
            bump(a.college_id, 2)
    if allow_fuzzy and len(ranked) < limit:
        # find_similar returns best match first; keep that order (3.00, 3.01, ...)
        for i, c in enumerate(find_similar(db, query, limit=limit, threshold=0.75)):
            bump(c.id, 3 + i / 100)

    ids = sorted(ranked, key=lambda cid: ranked[cid])[:limit]
    colleges = [db.get(College, cid) for cid in ids]
    # Within the same rank, verified colleges first, then alphabetical.
    return sorted(colleges, key=lambda c: (ranked[c.id], not c.is_verified, c.name))
