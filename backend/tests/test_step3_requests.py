"""
Step 3 checks: buy requests (the state machine), chat, unread counts,
blocking, reports, rate limits, duplicate listings.
`client` and `make_user` come from conftest.py.
"""
BOOK = {"title": "Engineering Mathematics", "author": "B S Grewal", "price": 300}


def list_book(client, headers, **extra):
    r = client.post("/books", json={**BOOK, **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def request_book(client, headers, book_id, message=None):
    return client.post("/requests", json={"book_id": book_id, "message": message}, headers=headers)


def act(client, headers, request_id, action):
    return client.post(f"/requests/{request_id}/{action}", headers=headers)


def book_status(client, book_id):
    return client.get(f"/books/{book_id}").json()["status"]


# ---------------------------------------------------------------- happy path
def test_full_deal_from_request_to_sold(client, make_user):
    seller, _ = make_user()
    buyer, buyer_user = make_user()
    book = list_book(client, seller)

    r = request_book(client, buyer, book["id"], "Hi! Is it still available?")
    assert r.status_code == 201, r.text
    req = r.json()
    assert req["status"] == "pending" and req["my_role"] == "buyer"
    assert req["unread_count"] == 0  # the buyer has seen their own request

    # The chat starts with the automatic safety tip, then the buyer's message.
    msgs = client.get(f"/requests/{req['id']}/messages", headers=buyer).json()
    assert msgs[0]["is_system"] and "never pay" in msgs[0]["body"].lower()
    assert msgs[1]["body"] == "Hi! Is it still available?" and msgs[1]["is_mine"]

    # Seller's inbox: 1 conversation, 2 unread (tip + buyer's message)
    inbox = client.get("/requests", headers=seller).json()
    assert len(inbox) == 1 and inbox[0]["my_role"] == "seller" and inbox[0]["unread_count"] == 2
    assert inbox[0]["buyer"]["name"] == buyer_user["name"]
    client.get(f"/requests/{req['id']}/messages", headers=seller)  # seller opens the chat
    assert client.get("/requests", headers=seller).json()[0]["unread_count"] == 0

    # Accept -> reserved for this buyer
    assert act(client, seller, req["id"], "accept").json()["status"] == "accepted"
    assert book_status(client, book["id"]) == "reserved"

    # Chat, then complete -> sold
    assert client.post(f"/requests/{req['id']}/messages", json={"body": "Library, 4pm?"}, headers=seller).status_code == 201
    assert act(client, seller, req["id"], "complete").json()["status"] == "completed"
    assert book_status(client, book["id"]) == "sold"

    # Conversation is closed now
    assert client.post(f"/requests/{req['id']}/messages", json={"body": "thanks"}, headers=buyer).status_code == 409


# ---------------------------------------------------------------- rules
def test_request_rules(client, make_user):
    seller, _ = make_user()
    buyer, _ = make_user()
    stranger, _ = make_user()
    book = list_book(client, seller)

    assert request_book(client, seller, book["id"]).status_code == 400   # own book
    assert request_book(client, buyer, 999999).status_code == 404        # no such book
    req = request_book(client, buyer, book["id"]).json()
    assert request_book(client, buyer, book["id"]).status_code == 409    # already requested

    # Outsiders can't see the conversation at all (404, not 403: don't reveal it exists)
    assert client.get(f"/requests/{req['id']}", headers=stranger).status_code == 404
    assert client.get(f"/requests/{req['id']}/messages", headers=stranger).status_code == 404
    assert client.post(f"/requests/{req['id']}/messages", json={"body": "hi"}, headers=stranger).status_code == 404

    # Only the seller decides
    assert act(client, buyer, req["id"], "accept").status_code == 403
    assert act(client, buyer, req["id"], "complete").status_code == 403
    assert act(client, seller, req["id"], "complete").status_code == 409  # must be accepted first
    assert act(client, seller, req["id"], "cancel").status_code == 409    # seller uses reject for pending

    assert act(client, seller, req["id"], "reject").json()["status"] == "rejected"
    assert act(client, seller, req["id"], "accept").status_code == 409    # already decided
    assert client.post(f"/requests/{req['id']}/messages", json={"body": "why?"}, headers=buyer).status_code == 409
    # After a rejection the buyer may ask again later
    assert request_book(client, buyer, book["id"]).status_code == 201


def test_two_buyers_and_a_deal_that_falls_through(client, make_user):
    seller, _ = make_user()
    a, _ = make_user()
    b, _ = make_user()
    c, _ = make_user()
    book = list_book(client, seller)
    ra = request_book(client, a, book["id"]).json()
    rb = request_book(client, b, book["id"]).json()

    act(client, seller, ra["id"], "accept")
    assert act(client, seller, rb["id"], "accept").status_code == 409     # already reserved for A
    assert request_book(client, c, book["id"]).status_code == 409         # reserved books can't be requested

    # A backs out -> book is available again
    assert act(client, a, ra["id"], "cancel").json()["status"] == "cancelled"
    assert book_status(client, book["id"]) == "available"
    last = client.get(f"/requests/{ra['id']}/messages", headers=seller).json()[-1]
    assert last["is_system"] and "available again" in last["body"]

    # C requests now, seller accepts B and completes -> C is told it's sold
    rc = request_book(client, c, book["id"]).json()
    act(client, seller, rb["id"], "accept")
    act(client, seller, rb["id"], "complete")
    assert client.get(f"/requests/{rc['id']}", headers=c).json()["status"] == "rejected"
    assert "sold" in client.get(f"/requests/{rc['id']}/messages", headers=c).json()[-1]["body"]


def test_polling_only_returns_new_messages(client, make_user):
    seller, _ = make_user()
    buyer, _ = make_user()
    req = request_book(client, buyer, list_book(client, seller)["id"]).json()
    first = client.get(f"/requests/{req['id']}/messages", headers=buyer).json()
    newest_id = first[-1]["id"]

    assert client.get(f"/requests/{req['id']}/messages", params={"after_id": newest_id}, headers=buyer).json() == []
    client.post(f"/requests/{req['id']}/messages", json={"body": "Can you do 250?"}, headers=seller)
    new = client.get(f"/requests/{req['id']}/messages", params={"after_id": newest_id}, headers=buyer).json()
    assert [m["body"] for m in new] == ["Can you do 250?"] and new[0]["is_mine"] is False
    assert client.post(f"/requests/{req['id']}/messages", json={"body": "   "}, headers=buyer).status_code == 422


def test_inbox_filters(client, make_user):
    seller, _ = make_user()
    buyer, _ = make_user()
    mine = list_book(client, buyer, title="My own book")
    other = list_book(client, seller)
    request_book(client, buyer, other["id"])
    request_book(client, seller, mine["id"])
    assert [r["my_role"] for r in client.get("/requests", params={"role": "buyer"}, headers=buyer).json()] == ["buyer"]
    assert [r["my_role"] for r in client.get("/requests", params={"role": "seller"}, headers=buyer).json()] == ["seller"]
    assert len(client.get("/requests", headers=buyer).json()) == 2


# ---------------------------------------------------------------- books + requests together
def test_manual_sold_closes_waiting_requests(client, make_user):
    seller, _ = make_user()
    buyer, _ = make_user()
    book = list_book(client, seller)
    req = request_book(client, buyer, book["id"]).json()
    assert client.patch(f"/books/{book['id']}/status", json={"status": "sold"}, headers=seller).status_code == 200
    assert client.get(f"/requests/{req['id']}", headers=buyer).json()["status"] == "rejected"


def test_cant_manually_sell_a_reserved_book(client, make_user):
    seller, _ = make_user()
    buyer, _ = make_user()
    book = list_book(client, seller)
    act(client, seller, request_book(client, buyer, book["id"]).json()["id"], "accept")
    assert client.patch(f"/books/{book['id']}/status", json={"status": "sold"}, headers=seller).status_code == 409


def test_deleting_books_with_conversations(client, make_user):
    seller, _ = make_user()
    buyer, _ = make_user()
    # Pending request only -> delete allowed, conversation removed
    b1 = list_book(client, seller, title="Book one")
    r1 = request_book(client, buyer, b1["id"]).json()
    assert client.delete(f"/books/{b1['id']}", headers=seller).status_code == 204
    assert client.get(f"/requests/{r1['id']}", headers=buyer).status_code == 404
    # Accepted deal -> must cancel first
    b2 = list_book(client, seller, title="Book two")
    act(client, seller, request_book(client, buyer, b2["id"]).json()["id"], "accept")
    assert client.delete(f"/books/{b2['id']}", headers=seller).status_code == 409


def test_duplicate_listing_needs_confirmation(client, make_user):
    seller, _ = make_user()
    list_book(client, seller)
    again = client.post("/books", json={**BOOK, "title": "  engineering MATHEMATICS "}, headers=seller)
    assert again.status_code == 409 and "already have this book" in again.json()["detail"]
    assert client.post("/books", json={**BOOK, "allow_duplicate": True}, headers=seller).status_code == 201
    other_seller, _ = make_user()
    assert client.post("/books", json=BOOK, headers=other_seller).status_code == 201  # different person: fine


# ---------------------------------------------------------------- safety
def test_blocking(client, make_user):
    seller, seller_user = make_user(college_q="Osmania University")
    buyer, buyer_user = make_user(college_q="Osmania University")
    cid = seller_user["college"]["id"]
    book = list_book(client, seller)
    req = request_book(client, buyer, book["id"]).json()

    def visible_to(headers):
        return [b["id"] for b in client.get("/books", params={"college_id": cid}, headers=headers).json()["items"]]

    assert book["id"] in visible_to(buyer)
    assert client.post(f"/blocks/{buyer_user['id']}", headers=seller).status_code == 201
    # Works both ways: blocked buyer can't message, can't request, doesn't see the listing
    assert client.post(f"/requests/{req['id']}/messages", json={"body": "hello?"}, headers=buyer).status_code == 403
    assert client.post(f"/requests/{req['id']}/messages", json={"body": "hi"}, headers=seller).status_code == 403
    second = list_book(client, seller, title="Another book")
    assert request_book(client, buyer, second["id"]).status_code == 403
    assert book["id"] not in visible_to(buyer)
    assert client.get("/books", params={"college_id": cid}).json()["total"] >= 2  # visitors still see them

    assert [b["id"] for b in client.get("/blocks", headers=seller).json()] == [buyer_user["id"]]
    assert client.post(f"/blocks/{seller_user['id']}", headers=seller).status_code == 400  # not yourself
    assert client.delete(f"/blocks/{buyer_user['id']}", headers=seller).status_code == 204
    assert book["id"] in visible_to(buyer)


def test_reports(client, make_user):
    seller, seller_user = make_user()
    reporter, reporter_user = make_user()
    book = list_book(client, seller)
    ok = client.post("/reports", json={"book_id": book["id"], "reason": "scam", "details": "Asked for UPI first"}, headers=reporter)
    assert ok.status_code == 201
    assert client.post("/reports", json={"user_id": seller_user["id"], "reason": "spam"}, headers=reporter).status_code == 201
    assert client.post("/reports", json={"reason": "spam"}, headers=reporter).status_code == 400
    assert client.post("/reports", json={"user_id": reporter_user["id"], "reason": "spam"}, headers=reporter).status_code == 400
    assert client.post("/reports", json={"book_id": book["id"], "reason": "because"}, headers=reporter).status_code == 422
    # Deleting a reported book keeps the report (it just loses the link)
    assert client.delete(f"/books/{book['id']}", headers=seller).status_code == 204


def test_rate_limits(client, make_user):
    seller, _ = make_user()
    buyer, buyer_user = make_user()
    req = request_book(client, buyer, list_book(client, seller)["id"]).json()
    url = f"/requests/{req['id']}/messages"
    for i in range(20):
        assert client.post(url, json={"body": f"msg {i}"}, headers=buyer).status_code == 201
    too_many = client.post(url, json={"body": "one more"}, headers=buyer)
    assert too_many.status_code == 429 and "Retry-After" in too_many.headers

    # 10 wrong passwords allowed, the 11th attempt is refused even with the RIGHT password
    for _ in range(10):
        assert client.post("/auth/login", json={"email": buyer_user["email"], "password": "wrongpass"}).status_code == 401
    assert client.post("/auth/login", json={"email": buyer_user["email"], "password": "secret123"}).status_code == 429
