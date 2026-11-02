# Book Exchange

A web app where college students list their used textbooks and other students buy them (meeting up offline to hand over the book), with in-app messages.

**Stack:** React (frontend) · FastAPI + Python (backend) · SQLite locally, Postgres when live

---

## Where we are

| Step | What | Status |
|---|---|---|
| 1 | Backend: login system + college list | ✅ done |
| 2 | Backend: books (list, search, filter, photos, status) | ✅ done |
| 3 | Backend: buy requests + chat + report/block + rate limits | ✅ done |
| 4 | Email verification + forgot password + delete account | next |
| 5 | Backend online (Render + Neon + Cloudinary) | |
| 6 | React frontend | |
| 7 | Frontend online (Vercel) + LinkedIn launch | |

---

## Run it on your laptop

You need **Python 3.11 or newer**. Check with `python3 --version`. If you don't have it: https://www.python.org/downloads/

Open a terminal **inside the `backend` folder**, then:

**Mac**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

What each line does:
- `python -m venv .venv`: creates a private box (a "virtual environment") for this project's packages, so they don't mix with other Python projects on your laptop.
- `activate`: switches into that box. Your prompt will show `(.venv)`. Do this every time you open a new terminal.
- `pip install -r requirements.txt`: installs everything listed in requirements.txt.
- `copy .env.example .env`: creates your settings file.
- `uvicorn app.main:app --reload`: starts the server. `--reload` restarts it automatically whenever you save a file.

When you see `Uvicorn running on http://127.0.0.1:8000`, open **http://127.0.0.1:8000/docs** in your browser.

### Try step 1 in /docs (no frontend needed yet)

The `/docs` page is generated automatically by FastAPI. Every endpoint has a **Try it out** button.

1. **GET /colleges**, then set `q` to `DU` and click Execute. University of Delhi comes back. Try `delhi univ`, `jnu` and `Mumbai Univeristy` (with the typo) too.
2. **POST /auth/signup** with this body (use the `id` from step 1 for `college_id`):
   ```json
   {"name": "Shobhit", "email": "shobhit@test.com", "password": "secret123", "college_id": 1}
   ```
   The response contains a `token`. Copy it.
3. Click the **Authorize 🔒** button at the top of the page, paste the token, and click Authorize.
4. **GET /auth/me** shows your profile. Click Authorize → Logout and try again: you get a 401.
5. **POST /colleges** with `{"name": "Delhi University"}` returns the existing college instead of creating a duplicate.

### Run the automatic tests
```bash
pytest -v
```
There are 40 checks: 14 for login and colleges (step 1), 14 for books and photos (step 2), 12 for requests, chat and safety (step 3). Run them after every change, so you know you haven't broken anything.

---

## How the code is organised

```
backend/
├── app/
│   ├── main.py              Starts the app, CORS, plugs in routers, runs seeding on startup
│   ├── config.py            Settings from .env (database URL, session length, allowed sites)
│   ├── db.py                Database connection + get_session() for each request
│   ├── models.py            Database tables: College, CollegeAlias, User, AuthSession
│   ├── schemas.py           Shape of data in/out of the API (never exposes password_hash)
│   ├── security.py          bcrypt passwords + login tokens + get_current_user()
│   ├── college_matching.py  "DU" = "Delhi University" = "University of Delhi" logic
│   ├── storage.py           Photo safety (check, shrink, strip GPS) + where photos are saved
│   ├── ratelimit.py         "Max N actions per M seconds" (login, requests, messages, reports)
│   ├── blocking.py          Block checks shared by books and requests
│   ├── seed.py              Loads seed_colleges.json into the database
│   ├── seed_colleges.json   Starter list of colleges + their nicknames (edit to add more)
│   └── routers/
│       ├── auth.py          /auth/signup, /auth/login, /auth/me, /auth/logout
│       ├── colleges.py      /colleges search, get one, add new
│       ├── books.py         /books browse, create, edit, status, delete, photos
│       ├── requests.py      /requests buy requests (the deal) + chat
│       └── safety.py        /reports and /blocks
├── tests/
│   ├── conftest.py          Shared test setup (temporary database + photo folder)
│   ├── test_step1.py        Login + college checks
│   ├── test_step2_books.py  Book, ownership, search and photo checks
│   └── test_step3_requests.py  Deal flow, chat, unread, blocks, reports, rate limits
├── uploads/                 Photos saved locally (created automatically, not in Git)
├── requirements.txt         Python packages
└── .env.example             Settings template
```

## How login works (short version)

1. **Signup/login**: the password is checked with bcrypt. Only a one-way scramble of it is ever stored.
2. The server creates a random **token**, stores a fingerprint of it in `AuthSession`, and gives the token to the browser.
3. The browser sends `Authorization: Bearer <token>` with every request.
4. Any route with `Depends(get_current_user)` is login-only. No valid token means 401.
5. **Logout** deletes that token's row, so it stops working immediately.

## How duplicate colleges are prevented

1. **Pick, don't type**: signup uses search-as-you-type over a curated list with nicknames (`DU`, `JNU`, `SRCC`…).
2. **Normalising**: `"Delhi  Univ."` and `"delhi univ"` are stored and compared as the same text. The database refuses exact duplicates.
3. **Fuzzy "did you mean?"**: before a new college is added, the server compares it with every existing name and nickname. It ignores word order, expands short forms (`univ` → `university`, `clg` → `college`), checks initials (`jnu`) and tolerates typos (`Dehli`). If something is close, the user gets suggestions instead of a new entry.
4. **Unverified flag**: colleges added by users get `is_verified = false`, so an admin screen (later) can merge any duplicates that still slip through.

## Books (step 2)

| Endpoint | Login? | Does |
|---|---|---|
| `GET /books` | public | Browse: `q`, `college_id`, `subject`, `semester`, `condition`, `min_price`, `max_price`, `status`, `sort`, `page`, `page_size` |
| `GET /books/{id}` | public | One book with photos, seller name and college (never email) |
| `GET /books/mine` | login | Your listings, including sold |
| `POST /books` | login | Create a listing (college is taken from your account; same title+author twice needs `allow_duplicate: true`) |
| `PATCH /books/{id}` | owner | Edit only the fields you send |
| `PATCH /books/{id}/status` | owner | Mark **sold** outside the app (reserved/sold otherwise come from buy requests) |
| `DELETE /books/{id}` | owner | Delete listing and its photo files |
| `POST /books/{id}/images` | owner | Upload a photo (max 3, max 5 MB) |
| `DELETE /books/{id}/images/{image_id}` | owner | Remove a photo |

**Authentication vs authorization:** `get_current_user` answers "who are you?" (401 if unknown). `get_own_book` answers "is this yours?" (403 if not).

**Photos:** every upload is checked to be a real image, rotated upright, shrunk to max 1200px, saved as JPEG, and stripped of hidden EXIF data (including GPS location). Only `storage.py` knows where files go, so switching to Cloudinary later touches one file.

## Buy requests and chat (step 3)

```
pending --accept--> accepted --complete--> completed   (book: available -> reserved -> sold)
   |                    |
 reject / cancel      cancel                            (book goes back to available)
```

| Endpoint | Who | Does |
|---|---|---|
| `POST /requests` | buyer | Request a book; opens a chat starting with an automatic safety tip |
| `GET /requests` | both | Inbox: `role=all/buyer/seller`, `only_open`; each row has last message + unread count |
| `GET /requests/{id}` | both | One conversation |
| `POST /requests/{id}/accept` | seller | Book becomes **reserved** for this buyer |
| `POST /requests/{id}/reject` | seller | Decline a pending request |
| `POST /requests/{id}/cancel` | buyer (any open) / seller (accepted) | Withdraw or "deal fell through"; book becomes available again |
| `POST /requests/{id}/complete` | seller | Book becomes **sold**; other waiting buyers are told |
| `GET /requests/{id}/messages?after_id=N` | both | Read chat; `after_id` returns only newer messages (polling) |
| `POST /requests/{id}/messages` | both | Send a message (only while pending/accepted) |

People outside a conversation get **404**, so they can't even tell it exists.

## Safety (step 3)

| Endpoint | Does |
|---|---|
| `POST /reports` | Report a listing (`book_id`) or person (`user_id`) with a reason: scam, spam, inappropriate, wrong_info, other |
| `POST /blocks/{user_id}` · `DELETE /blocks/{user_id}` · `GET /blocks` | Block / unblock / list. Blocks work both ways: no requests, no messages, listings hidden |

**Rate limits** (answer **429** with a `Retry-After` header): 10 logins per 5 min per email · 10 buy requests per hour · 20 messages per minute · 10 reports per hour. Counters live in server memory (fine for one server; Redis if we ever run several).
