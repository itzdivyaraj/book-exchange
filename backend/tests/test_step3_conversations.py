"""
Step 3 checks: messaging sellers (conversations), chat, unread counts,
blocking, reports, rate limits, duplicate listings.
`client` and `make_user` come from conftest.py.
"""
BOOK = {"city": "Delhi", "title": "Engineering Mathematics", "author": "B S Grewal", "price": 300}


def list_book(client, headers, **extra):
    r = client.post("/books", json={**BOOK, **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def message_seller(client, headers, book_id, message=None):
    return client.post("/conversations", json={"book_id": book_id, "message": message}, headers=headers)


# ---------------------------------------------------------------- the main flow
def test_message_seller_chat_and_unread(client, make_user):
    seller, _ = make_user()
    buyer, buyer_user = make_user()
    book = list_book(client, seller)

    r = message_seller(client, buyer, book["id"], "Hi! Is it still available?")
    assert r.status_code == 201, r.text
    conv = r.json()
    assert conv["my_role"] == "buyer" and conv["unread_count"] == 0 and conv["book"]["city"] == "Delhi"

    # The chat starts with the automatic note, then the buyer's message.
    msgs = client.get(f"/conversations/{conv['id']}/messages", headers=buyer).json()
    assert msgs[0]["is_system"] and "only connects you" in msgs[0]["body"]
    assert msgs[1]["body"] == "Hi! Is it still available?" and msgs[1]["is_mine"]

    # Seller's inbox: 1 chat, 2 unread (note + message); opening it clears the count
    inbox = client.get("/conversations", headers=seller).json()
    assert len(inbox) == 1 and inbox[0]["my_role"] == "seller" and inbox[0]["unread_count"] == 2
    assert inbox[0]["buyer"]["name"] == buyer_user["name"]
    client.get(f"/conversations/{conv['id']}/messages", headers=seller)
    assert client.get("/conversations", headers=seller).json()[0]["unread_count"] == 0

    # They arrange things themselves; the seller marks it sold; the chat still works
    assert client.post(f"/conversations/{conv['id']}/messages", json={"body": "Yes! Call me on 98xxxxxx"}, headers=seller).status_code == 201
    assert client.patch(f"/books/{book['id']}/status", json={"status": "sold"}, headers=seller).status_code == 200
    assert client.post(f"/conversations/{conv['id']}/messages", json={"body": "Thanks!"}, headers=buyer).status_code == 201


def test_messaging_again_reopens_the_same_chat(client, make_user):
    seller, _ = make_user()
    buyer, _ = make_user()
    book = list_book(client, seller)
    first = message_seller(client, buyer, book["id"], "Hello").json()
    again = message_seller(client, buyer, book["id"], "Hello again")
    assert again.status_code == 200 and again.json()["id"] == first["id"]
    bodies = [m["body"] for m in client.get(f"/conversations/{first['id']}/messages", headers=buyer).json()]
    assert bodies[-2:] == ["Hello", "Hello again"] and len(bodies) == 3  # one welcome note only


def test_rules(client, make_user):
    seller, _ = make_user()
    buyer, _ = make_user()
    stranger, _ = make_user()
    book = list_book(client, seller)

    assert message_seller(client, seller, book["id"]).status_code == 400   # own listing
    assert message_seller(client, buyer, 999999).status_code == 404        # no such book
    conv = message_seller(client, buyer, book["id"]).json()

    # Outsiders can't see the conversation at all (404, not 403: don't reveal it exists)
    assert client.get(f"/conversations/{conv['id']}", headers=stranger).status_code == 404
    assert client.get(f"/conversations/{conv['id']}/messages", headers=stranger).status_code == 404
    assert client.post(f"/conversations/{conv['id']}/messages", json={"body": "hi"}, headers=stranger).status_code == 404

    # A sold book can't get NEW chats, but the existing one still opens
    client.patch(f"/books/{book['id']}/status", json={"status": "sold"}, headers=seller)
    assert message_seller(client, stranger, book["id"]).status_code == 409
    assert message_seller(client, buyer, book["id"]).status_code == 200


def test_polling_only_returns_new_messages(client, make_user):
    seller, _ = make_user()
    buyer, _ = make_user()
    conv = message_seller(client, buyer, list_book(client, seller)["id"]).json()
    first = client.get(f"/conversations/{conv['id']}/messages", headers=buyer).json()
    newest_id = first[-1]["id"]

    assert client.get(f"/conversations/{conv['id']}/messages", params={"after_id": newest_id}, headers=buyer).json() == []
    client.post(f"/conversations/{conv['id']}/messages", json={"body": "Can you do 250?"}, headers=seller)
    new = client.get(f"/conversations/{conv['id']}/messages", params={"after_id": newest_id}, headers=buyer).json()
    assert [m["body"] for m in new] == ["Can you do 250?"] and new[0]["is_mine"] is False
    assert client.post(f"/conversations/{conv['id']}/messages", json={"body": "   "}, headers=buyer).status_code == 422


def test_inbox_filters(client, make_user):
    seller, _ = make_user()
    buyer, _ = make_user()
    mine = list_book(client, buyer, title="My own book")
    other = list_book(client, seller)
    message_seller(client, buyer, other["id"])
    message_seller(client, seller, mine["id"])
    assert [r["my_role"] for r in client.get("/conversations", params={"role": "buyer"}, headers=buyer).json()] == ["buyer"]
    assert [r["my_role"] for r in client.get("/conversations", params={"role": "seller"}, headers=buyer).json()] == ["seller"]
    assert len(client.get("/conversations", headers=buyer).json()) == 2


def test_deleting_a_book_removes_its_chats(client, make_user):
    seller, _ = make_user()
    buyer, _ = make_user()
    book = list_book(client, seller)
    conv = message_seller(client, buyer, book["id"]).json()
    assert client.delete(f"/books/{book['id']}", headers=seller).status_code == 204
    assert client.get(f"/conversations/{conv['id']}", headers=buyer).status_code == 404


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
    conv = message_seller(client, buyer, book["id"]).json()

    def visible_to(headers):
        return [b["id"] for b in client.get("/books", params={"college_id": cid}, headers=headers).json()["items"]]

    assert book["id"] in visible_to(buyer)
    assert client.post(f"/blocks/{buyer_user['id']}", headers=seller).status_code == 201
    # Works both ways: neither can message, buyer can't start new chats, listing hidden
    assert client.post(f"/conversations/{conv['id']}/messages", json={"body": "hello?"}, headers=buyer).status_code == 403
    assert client.post(f"/conversations/{conv['id']}/messages", json={"body": "hi"}, headers=seller).status_code == 403
    second = list_book(client, seller, title="Another book")
    assert message_seller(client, buyer, second["id"]).status_code == 403
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
    assert client.delete(f"/books/{book['id']}", headers=seller).status_code == 204  # report is kept


def test_rate_limits(client, make_user):
    seller, _ = make_user()
    buyer, buyer_user = make_user()
    conv = message_seller(client, buyer, list_book(client, seller)["id"]).json()
    url = f"/conversations/{conv['id']}/messages"
    for i in range(20):
        assert client.post(url, json={"body": f"msg {i}"}, headers=buyer).status_code == 201
    too_many = client.post(url, json={"body": "one more"}, headers=buyer)
    assert too_many.status_code == 429 and "Retry-After" in too_many.headers

    # 10 wrong passwords allowed, the 11th attempt is refused even with the RIGHT password
    for _ in range(10):
        assert client.post("/auth/login", json={"email": buyer_user["email"], "password": "wrongpass"}).status_code == 401
    assert client.post("/auth/login", json={"email": buyer_user["email"], "password": "secret123"}).status_code == 429
