"""
Step 4 checks: email verification, codes (expiry, attempts, one-use), forgot/reset/change
password, and account deletion. `client`, `make_user`, `latest_code` come from conftest.py.
"""
import io
from datetime import timedelta

from PIL import Image
from sqlmodel import Session, select

from app.db import engine
from app.emailer import OUTBOX
from app.models import EmailCode, utcnow
from conftest import latest_code

BOOK = {"city": "Delhi", "title": "Signals and Systems", "author": "Oppenheim", "price": 500}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def signup(client, email, password="secret123"):
    du = client.get("/colleges", params={"q": "DU"}).json()[0]["id"]
    r = client.post("/auth/signup", json={"name": "New Person", "email": email, "password": password, "college_id": du})
    assert r.status_code == 201, r.text
    return auth(r.json()["token"]), r.json()["user"]


# ---------------------------------------------------------------- verification
def test_signup_sends_code_and_unverified_users_are_limited(client, make_user):
    headers, user = signup(client, "fresh@example.com")
    assert user["email_verified"] is False
    mail = [m for m in OUTBOX if m.to == "fresh@example.com"][-1]
    assert "verification code" in mail.subject and latest_code("fresh@example.com") in mail.body

    # Can browse, but can't list, request or message
    assert client.get("/books").status_code == 200
    assert client.post("/books", json=BOOK, headers=headers).status_code == 403
    seller, _ = make_user()
    book = client.post("/books", json=BOOK, headers=seller).json()
    blocked = client.post("/conversations", json={"book_id": book["id"]}, headers=headers)
    assert blocked.status_code == 403 and "verify your email" in blocked.json()["detail"]

    # Wrong code -> told how many attempts are left; right code -> verified
    wrong = client.post("/auth/verify-email", json={"code": "000000" if latest_code("fresh@example.com") != "000000" else "111111"}, headers=headers)
    assert wrong.status_code == 400 and "4 attempts left" in wrong.json()["detail"]
    ok = client.post("/auth/verify-email", json={"code": latest_code("fresh@example.com")}, headers=headers)
    assert ok.status_code == 200 and ok.json()["email_verified"] is True
    assert client.post("/books", json=BOOK, headers=headers).status_code == 201
    # Badly-shaped codes never reach our code (Pydantic rejects them)
    assert client.post("/auth/verify-email", json={"code": "12ab56"}, headers=headers).status_code == 422


def test_code_dies_after_five_wrong_attempts(client):
    headers, _ = signup(client, "guesser@example.com")
    real = latest_code("guesser@example.com")
    wrong = "123456" if real != "123456" else "654321"
    for _ in range(5):
        assert client.post("/auth/verify-email", json={"code": wrong}, headers=headers).status_code == 400
    late = client.post("/auth/verify-email", json={"code": real}, headers=headers)
    assert late.status_code == 400 and "Too many wrong attempts" in late.json()["detail"]


def test_expired_code(client):
    headers, user = signup(client, "slow@example.com")
    with Session(engine) as db:  # fast-forward time: make the code 16 minutes old
        row = db.exec(select(EmailCode).where(EmailCode.user_id == user["id"])).first()
        row.expires_at = utcnow() - timedelta(minutes=1)
        db.add(row)
        db.commit()
    r = client.post("/auth/verify-email", json={"code": latest_code("slow@example.com")}, headers=headers)
    assert r.status_code == 400 and "expired" in r.json()["detail"]


def test_resend_replaces_old_code_and_is_rate_limited(client):
    headers, _ = signup(client, "resend@example.com")
    old = latest_code("resend@example.com")
    assert client.post("/auth/resend-verification", headers=headers).status_code == 200
    new = latest_code("resend@example.com")
    if old != new:  # (1 in a million they match by chance)
        assert client.post("/auth/verify-email", json={"code": old}, headers=headers).status_code == 400
    assert client.post("/auth/resend-verification", headers=headers).status_code == 429  # within a minute
    assert client.post("/auth/verify-email", json={"code": new}, headers=headers).status_code == 200


# ---------------------------------------------------------------- forgot / reset / change
def test_forgot_and_reset_password(client, make_user):
    headers, user = make_user()
    email = user["email"]
    before = len(OUTBOX)

    known = client.post("/auth/forgot-password", json={"email": email})
    unknown = client.post("/auth/forgot-password", json={"email": "nobody-here@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()           # identical answers
    assert [m.to for m in OUTBOX[before:]] == [email]  # but only the real account got an email

    code = latest_code(email)
    r = client.post("/auth/reset-password", json={"email": email, "code": code, "new_password": "brandnew123"})
    assert r.status_code == 200
    assert client.get("/auth/me", headers=headers).status_code == 401  # logged out everywhere
    assert client.post("/auth/login", json={"email": email, "password": "secret123"}).status_code == 401
    assert client.post("/auth/login", json={"email": email, "password": "brandnew123"}).status_code == 200
    # One use only
    again = client.post("/auth/reset-password", json={"email": email, "code": code, "new_password": "another123"})
    assert again.status_code == 400


def test_change_password_logs_out_other_devices(client, make_user):
    phone, user = make_user()
    laptop = auth(client.post("/auth/login", json={"email": user["email"], "password": "secret123"}).json()["token"])
    bad = client.post("/auth/change-password", json={"current_password": "nope", "new_password": "newpass123"}, headers=phone)
    assert bad.status_code == 400
    ok = client.post("/auth/change-password", json={"current_password": "secret123", "new_password": "newpass123"}, headers=phone)
    assert ok.status_code == 200
    assert client.get("/auth/me", headers=phone).status_code == 200    # this device stays in
    assert client.get("/auth/me", headers=laptop).status_code == 401   # the other is out


# ---------------------------------------------------------------- delete account
def _jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (300, 300), "navy").save(buf, format="JPEG")
    return buf.getvalue()


def test_delete_account_erases_personal_data(client, make_user):
    import os
    from pathlib import Path

    leaving, leaving_user = make_user()
    other, _ = make_user()

    # The leaving user has: an available book with a photo, a sold book, and a chat as a buyer.
    available = client.post("/books", json={**BOOK, "title": "Available one"}, headers=leaving).json()
    client.post(f"/books/{available['id']}/images", headers=leaving, files={"file": ("p.jpg", _jpeg(), "image/jpeg")})
    sold = client.post("/books", json={**BOOK, "title": "Sold one"}, headers=leaving).json()
    client.post("/conversations", json={"book_id": sold["id"], "message": "Is it available?"}, headers=other)
    client.patch(f"/books/{sold['id']}/status", json={"status": "sold"}, headers=leaving)

    others_book = client.post("/books", json=BOOK, headers=other).json()
    conv = client.post("/conversations", json={"book_id": others_book["id"], "message": "My number is 98xxxxxx"}, headers=leaving).json()
    photos_before = len(list(Path(os.environ["UPLOAD_DIR"]).iterdir()))

    assert client.post("/auth/delete-account", json={"password": "wrong"}, headers=leaving).status_code == 400
    assert client.post("/auth/delete-account", json={"password": "secret123"}, headers=leaving).status_code == 204

    # Logged out and can't log back in
    assert client.get("/auth/me", headers=leaving).status_code == 401
    assert client.post("/auth/login", json={"email": leaving_user["email"], "password": "secret123"}).status_code == 401
    # Available listing and its photo are gone; sold one stays as history under "Deleted user"
    assert client.get(f"/books/{available['id']}").status_code == 404
    assert len(list(Path(os.environ["UPLOAD_DIR"]).iterdir())) == photos_before - 1
    assert client.get(f"/books/{sold['id']}").json()["seller"]["name"] == "Deleted user"
    # The other person's chat shows what happened without the personal text, and can't be replied to
    msgs = client.get(f"/conversations/{conv['id']}/messages", headers=other).json()
    assert "98xxxxxx" not in str(msgs) and "[message deleted]" in [m["body"] for m in msgs]
    assert "deleted their account" in msgs[-1]["body"]
    assert client.get(f"/conversations/{conv['id']}", headers=other).json()["buyer"]["name"] == "Deleted user"
    assert client.post(f"/conversations/{conv['id']}/messages", json={"body": "hello?"}, headers=other).status_code == 409
    # The email is free again for a brand-new account
    signup(client, leaving_user["email"])
