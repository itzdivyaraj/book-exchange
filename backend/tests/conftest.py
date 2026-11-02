"""
Shared test setup. pytest loads this file automatically BEFORE any test file.

It points the app at a throwaway database and a throwaway photo folder,
so running tests never touches your real books.db or uploads/.
"""
import os
import tempfile

_tmp = tempfile.mkdtemp()
# Normally a throwaway SQLite file. To test against Postgres instead, set TEST_DATABASE_URL
# to an EMPTY Postgres database before running pytest.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["UPLOAD_DIR"] = f"{_tmp}/uploads"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    """A fake browser shared by all tests. 'with' runs startup (tables + college list)."""
    with TestClient(app) as c:
        yield c


_counter = {"n": 0}


def latest_code(email: str) -> str:
    """The 6-digit code from the newest email sent to `email` (console email backend)."""
    import re

    from app.emailer import OUTBOX

    for mail in reversed(OUTBOX):
        if mail.to == email:
            return re.search(r"\b(\d{6})\b", mail.subject).group(1)
    raise AssertionError(f"No email found for {email}")


@pytest.fixture
def make_user(client):
    """Creates a brand-new user and returns (auth headers, user json). Call it as many times as you like."""

    def _make(college_q: str = "DU", verified: bool = True):
        _counter["n"] += 1
        college_id = client.get("/colleges", params={"q": college_q}).json()[0]["id"]
        r = client.post("/auth/signup", json={
            "name": f"Student {_counter['n']}",
            "email": f"student{_counter['n']}@example.com",
            "password": "secret123",
            "college_id": college_id,
        })
        assert r.status_code == 201, r.text
        headers = {"Authorization": f"Bearer {r.json()['token']}"}
        if verified:  # read the code from the console outbox, like a user reading their inbox
            code = latest_code(f"student{_counter['n']}@example.com")
            v = client.post("/auth/verify-email", json={"code": code}, headers=headers)
            assert v.status_code == 200, v.text
        user = client.get("/auth/me", headers=headers).json()
        return headers, user

    return _make


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    """Each test starts with clean rate-limit counters (autouse = applies to every test automatically)."""
    from app.ratelimit import reset_rate_limits

    reset_rate_limits()
    yield
