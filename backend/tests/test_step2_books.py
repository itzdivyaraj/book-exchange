"""
Step 2 checks: books, ownership, search/filters/pages, status rules, photos.
`client` and `make_user` come from conftest.py.
"""
import io
from pathlib import Path

from PIL import Image

BOOK = {
    "city": "Delhi",
    "title": "Concepts of Physics Vol 1",
    "author": "H C Verma",
    "edition": "2022",
    "subject": "Physics",
    "semester": 1,
    "condition": "good",
    "price": 250,
    "description": "Some pencil notes in chapter 3.",
}


def create_book(client, headers, **overrides):
    r = client.post("/books", json={**BOOK, **overrides}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def jpeg_bytes(size=(800, 600), with_gps=False) -> bytes:
    img = Image.new("RGB", size, (200, 120, 40))
    buf = io.BytesIO()
    if with_gps:
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"                    # camera make
        exif.get_ifd(0x8825)[2] = (28.0, 38.0, 0.0)    # GPS latitude (somewhere in Delhi)
        img.save(buf, format="JPEG", exif=exif)
    else:
        img.save(buf, format="JPEG")
    return buf.getvalue()


def upload(client, headers, book_id, data: bytes, name="photo.jpg", mime="image/jpeg"):
    return client.post(f"/books/{book_id}/images", headers=headers, files={"file": (name, data, mime)})


# ---------------------------------------------------------------- create + view
def test_must_be_logged_in_to_list_a_book(client):
    assert client.post("/books", json=BOOK).status_code == 401


def test_create_and_view_book(client, make_user):
    headers, user = make_user()
    book = create_book(client, headers)
    assert book["status"] == "available"
    assert book["seller"] == {"id": user["id"], "name": user["name"]}
    assert book["college"]["id"] == user["college"]["id"]  # copied from the seller
    assert book["is_mine"] is True

    # A visitor (no token) can view it, but it's not theirs, and no private details leak.
    public = client.get(f"/books/{book['id']}").json()
    assert public["is_mine"] is False
    assert "email" not in str(public["seller"])


def test_book_validation(client, make_user):
    headers, _ = make_user()
    assert client.post("/books", json={**BOOK, "price": -10}, headers=headers).status_code == 422
    assert client.post("/books", json={**BOOK, "semester": 13}, headers=headers).status_code == 422
    assert client.post("/books", json={**BOOK, "condition": "brand new!!"}, headers=headers).status_code == 422
    assert client.post("/books", json={**BOOK, "title": ""}, headers=headers).status_code == 422


def test_missing_book_is_404(client):
    assert client.get("/books/999999").status_code == 404


# ---------------------------------------------------------------- authorization
def test_only_the_seller_can_change_a_book(client, make_user):
    owner, _ = make_user()
    stranger, _ = make_user()
    book = create_book(client, owner)
    bid = book["id"]

    assert client.patch(f"/books/{bid}", json={"price": 1}, headers=stranger).status_code == 403
    assert client.patch(f"/books/{bid}/status", json={"status": "sold"}, headers=stranger).status_code == 403
    assert client.delete(f"/books/{bid}", headers=stranger).status_code == 403
    assert upload(client, stranger, bid, jpeg_bytes()).status_code == 403
    # ...and nothing changed
    assert client.get(f"/books/{bid}").json()["price"] == BOOK["price"]


def test_partial_update_changes_only_what_was_sent(client, make_user):
    headers, _ = make_user()
    book = create_book(client, headers)
    r = client.patch(f"/books/{book['id']}", json={"price": 199}, headers=headers)
    assert r.status_code == 200
    assert r.json()["price"] == 199
    assert r.json()["title"] == BOOK["title"]  # untouched
    # Required fields can't be blanked out
    assert client.patch(f"/books/{book['id']}", json={"title": None}, headers=headers).status_code == 422


# ---------------------------------------------------------------- status rules
def test_status_available_and_sold(client, make_user):
    headers, _ = make_user()
    bid = create_book(client, headers)["id"]
    url = f"/books/{bid}/status"

    assert client.patch(url, json={"status": "reserved"}, headers=headers).status_code == 422  # no such status
    assert client.patch(url, json={"status": "sold"}, headers=headers).json()["status"] == "sold"
    assert client.patch(f"/books/{bid}", json={"price": 10}, headers=headers).status_code == 409  # can't edit while sold
    assert client.patch(url, json={"status": "available"}, headers=headers).json()["status"] == "available"
    assert client.patch(f"/books/{bid}", json={"price": 10}, headers=headers).status_code == 200


def test_city_is_required_tidied_and_filterable(client, make_user):
    headers, user = make_user(college_q="Jadavpur University")
    assert client.post("/books", json={**BOOK, "city": ""}, headers=headers).status_code == 422
    no_city = {k: v for k, v in BOOK.items() if k != "city"}
    assert client.post("/books", json=no_city, headers=headers).status_code == 422
    b = create_book(client, headers, city="  kolkata ", title="Kolkata book")
    assert b["city"] == "Kolkata"
    create_book(client, headers, city="Siliguri", title="Siliguri book")
    cid = user["college"]["id"]
    found = client.get("/books", params={"college_id": cid, "city": "KOLKATA"}).json()["items"]
    assert [x["title"] for x in found] == ["Kolkata book"]


def test_my_books_include_sold_ones(client, make_user):
    headers, _ = make_user()
    a = create_book(client, headers, title="Book A")
    b = create_book(client, headers, title="Book B")
    client.patch(f"/books/{b['id']}/status", json={"status": "sold"}, headers=headers)
    mine = client.get("/books/mine", headers=headers).json()
    assert {x["id"] for x in mine} == {a["id"], b["id"]}
    assert client.get("/books/mine").status_code == 401


# ---------------------------------------------------------------- browse
def test_search_filters_sorting_and_pages(client, make_user):
    # Use a college nobody else in the tests uses, so results are predictable.
    headers, user = make_user(college_q="Anna University")
    cid = user["college"]["id"]
    create_book(client, headers, title="Organic Chemistry", author="Morrison", subject="Chemistry", price=400, semester=2)
    create_book(client, headers, title="Physical Chemistry", author="Atkins", subject="Chemistry", price=150, semester=2)
    create_book(client, headers, title="Calculus", author="Thomas", subject="Maths", price=300, semester=1)
    sold = create_book(client, headers, title="Chemistry Lab Manual", author="Anon", subject="Chemistry", price=50)
    client.patch(f"/books/{sold['id']}/status", json={"status": "sold"}, headers=headers)

    def titles(**params):
        r = client.get("/books", params={"college_id": cid, **params})
        assert r.status_code == 200, r.text
        return [b["title"] for b in r.json()["items"]]

    # Search is case-insensitive and looks at title, author and subject. Sold books hidden by default.
    assert sorted(titles(q="chemistry")) == ["Organic Chemistry", "Physical Chemistry"]
    assert titles(q="ATKINS") == ["Physical Chemistry"]
    # Filters combine
    assert titles(subject="chemistry", max_price=200) == ["Physical Chemistry"]
    assert titles(semester=1) == ["Calculus"]
    assert titles(status="sold") == ["Chemistry Lab Manual"]
    # Sorting
    assert titles(sort="price_low") == ["Physical Chemistry", "Calculus", "Organic Chemistry"]
    assert titles(sort="price_high")[0] == "Organic Chemistry"
    # Pages: 3 available books, 2 per page -> 2 pages
    p1 = client.get("/books", params={"college_id": cid, "page_size": 2, "sort": "price_low"}).json()
    p2 = client.get("/books", params={"college_id": cid, "page_size": 2, "page": 2, "sort": "price_low"}).json()
    assert (p1["total"], p1["pages"], len(p1["items"]), len(p2["items"])) == (3, 2, 2, 1)
    assert p2["items"][0]["title"] == "Organic Chemistry"
    # Bad parameter values are rejected
    assert client.get("/books", params={"sort": "cheapest"}).status_code == 422
    assert client.get("/books", params={"page_size": 500}).status_code == 422


def test_search_treats_percent_literally(client, make_user):
    headers, user = make_user(college_q="Gujarat University")
    create_book(client, headers, title="Score 100% in Maths")
    create_book(client, headers, title="Maths Made Easy")
    r = client.get("/books", params={"college_id": user["college"]["id"], "q": "100%"}).json()
    assert [b["title"] for b in r["items"]] == ["Score 100% in Maths"]


# ---------------------------------------------------------------- photos
def test_photo_upload_is_resized_and_location_stripped(client, make_user):
    headers, _ = make_user()
    bid = create_book(client, headers)["id"]

    r = upload(client, headers, bid, jpeg_bytes(size=(4000, 3000), with_gps=True))
    assert r.status_code == 201, r.text
    image = r.json()["images"][0]

    # The photo can be loaded from its URL
    path = image["url"].split("8000", 1)[1]  # "/uploads/xxxx.jpg"
    served = client.get(path)
    assert served.status_code == 200
    saved = Image.open(io.BytesIO(served.content))
    assert max(saved.size) == 1200          # shrunk from 4000px
    assert len(saved.getexif()) == 0         # camera + GPS data removed


def test_bad_uploads_are_rejected(client, make_user):
    headers, _ = make_user()
    bid = create_book(client, headers)["id"]
    assert upload(client, headers, bid, b"definitely not an image", name="virus.jpg").status_code == 400
    too_big = b"\xff" * (5 * 1024 * 1024 + 10)
    assert upload(client, headers, bid, too_big).status_code == 400


def test_max_three_photos_and_delete(client, make_user):
    headers, _ = make_user()
    bid = create_book(client, headers)["id"]
    for _ in range(3):
        assert upload(client, headers, bid, jpeg_bytes()).status_code == 201
    assert upload(client, headers, bid, jpeg_bytes()).status_code == 409

    images = client.get(f"/books/{bid}").json()["images"]
    assert [i["position"] for i in images] == [0, 1, 2]
    first_path = images[0]["url"].split("8000", 1)[1]

    r = client.delete(f"/books/{bid}/images/{images[0]['id']}", headers=headers)
    assert r.status_code == 200 and len(r.json()["images"]) == 2
    assert client.get(first_path).status_code == 404  # the file itself is gone


def test_deleting_a_book_deletes_its_photos(client, make_user):
    import os

    headers, _ = make_user()
    bid = create_book(client, headers)["id"]
    upload(client, headers, bid, jpeg_bytes())
    upload(client, headers, bid, jpeg_bytes())
    before = len(list(Path(os.environ["UPLOAD_DIR"]).iterdir()))

    assert client.delete(f"/books/{bid}", headers=headers).status_code == 204
    assert client.get(f"/books/{bid}").status_code == 404
    after = len(list(Path(os.environ["UPLOAD_DIR"]).iterdir()))
    assert before - after == 2
