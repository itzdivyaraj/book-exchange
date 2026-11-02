"""
Automatic checks. Run with:  pytest -v
Each test pretends to be a browser calling the API, using a throwaway test database.
"""
import pytest

from app.college_matching import similarity

# The temporary database and the `client` fake browser come from conftest.py.


def college_id(client, q):
    return client.get("/colleges", params={"q": q}).json()[0]["id"]


# ---------- Colleges ----------
@pytest.mark.parametrize("typed", ["DU", "du", "Delhi University", "delhi univ.", "University of Delhi"])
def test_all_ways_of_writing_du_find_the_same_college(client, typed):
    results = client.get("/colleges", params={"q": typed}).json()
    assert results[0]["name"] == "University of Delhi"


def test_acronym_and_word_order_matching():
    assert similarity("JNU", "Jawaharlal Nehru University") >= 0.9
    assert similarity("Delhi University", "University of Delhi") == 1.0


def test_adding_existing_college_by_alias_returns_existing(client):
    r = client.post("/colleges", json={"name": "Delhi University", "city": "Delhi"}).json()
    assert r["created"] is False
    assert r["college"]["name"] == "University of Delhi"


def test_adding_near_duplicate_gives_suggestions(client):
    r = client.post("/colleges", json={"name": "Univ of Dehli", "city": "Delhi"}).json()  # typo on purpose
    assert r["created"] is False
    assert any(s["name"] == "University of Delhi" for s in r["suggestions"])


def test_adding_truly_new_college(client):
    r = client.post("/colleges", json={"name": "Maharaja Agrasen Institute of Technology", "city": "Delhi"}).json()
    assert r["created"] is True
    assert r["college"]["is_verified"] is False
    # Same name again (different spacing/case) does NOT create a second copy.
    again = client.post("/colleges", json={"name": "maharaja  agrasen institute of technology", "city": "delhi"}).json()
    assert again["created"] is False
    assert again["college"]["id"] == r["college"]["id"]


# ---------- Auth ----------
def test_signup_login_me_logout(client):
    du = college_id(client, "DU")
    r = client.post("/auth/signup", json={
        "name": "Test Student", "email": "Test@Example.com", "password": "secret123", "college_id": du,
    })
    assert r.status_code == 201
    token = r.json()["token"]
    assert r.json()["user"]["email"] == "test@example.com"  # stored lowercase
    assert "password" not in str(r.json())  # never leaks password or hash

    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["college"]["name"] == "University of Delhi"

    # Log in again (e.g. on a second device) -> a new, different token
    r2 = client.post("/auth/login", json={"email": "test@example.com", "password": "secret123"})
    assert r2.status_code == 200 and r2.json()["token"] != token

    # Log out the first device; its token stops working, the second still works
    assert client.post("/auth/logout", headers=headers).status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {r2.json()['token']}"}).status_code == 200


def test_duplicate_email_rejected(client):
    du = college_id(client, "DU")
    body = {"name": "A", "email": "dup@example.com", "password": "secret123", "college_id": du}
    body["name"] = "Aa"
    assert client.post("/auth/signup", json=body).status_code == 201
    assert client.post("/auth/signup", json=body).status_code == 409


def test_wrong_password_and_unknown_email_look_the_same(client):
    a = client.post("/auth/login", json={"email": "dup@example.com", "password": "wrongpass"})
    b = client.post("/auth/login", json={"email": "nobody@example.com", "password": "wrongpass"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_validation(client):
    du = college_id(client, "DU")
    short = client.post("/auth/signup", json={"name": "Ab", "email": "x@example.com", "password": "123", "college_id": du})
    assert short.status_code == 422
    bad_email = client.post("/auth/signup", json={"name": "Ab", "email": "not-an-email", "password": "secret123", "college_id": du})
    assert bad_email.status_code == 422
    bad_college = client.post("/auth/signup", json={"name": "Ab", "email": "y@example.com", "password": "secret123", "college_id": 99999})
    assert bad_college.status_code == 400


def test_no_token_or_fake_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer made-up-token"}).status_code == 401


def test_new_college_needs_a_city(client):
    assert client.post("/colleges", json={"name": "Some Brand New College Of Arts"}).status_code == 422
