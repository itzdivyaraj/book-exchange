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
| 4 | Email verification + forgot password + delete account | ✅ done |
| 5 | Backend ready to go online: migrations, Cloudinary, Brevo, `render.yaml` | ✅ code done |
| 6 | React website | ✅ done |
| 7 | Put it online (Neon + Cloudinary + Brevo + Render + Vercel) + LinkedIn launch | next: follow [DEPLOY.md](DEPLOY.md) |

---

## Run it on your laptop

You need **Python 3.11+** (`python3 --version`) and **Node.js 20+** (`node --version`; install from https://nodejs.org).
Use two Terminal tabs: one for the backend, one for the website.

### Tab 1: backend (http://127.0.0.1:8000/docs)
```bash
cd backend
python3 -m venv .venv            # first time only
source .venv/bin/activate        # every time
pip install -r requirements.txt  # first time, and when requirements.txt changes
cp .env.example .env             # first time only
uvicorn app.main:app --reload
```
Verification and reset codes are **printed in this tab** (no real emails are sent locally).

### Tab 2: website (http://localhost:5173)
```bash
cd frontend
npm install                      # first time, and when package.json changes
cp .env.example .env             # first time only
npm run dev
```

### Run the automatic tests
```bash
cd backend && source .venv/bin/activate && pytest -v
```
47 checks: login and colleges (step 1), books and photos (step 2), requests, chat and safety (step 3), verification, passwords and account deletion (step 4). They also pass on Postgres: set `TEST_DATABASE_URL` to an empty Postgres database.

---

## How the code is organised

```
render.yaml                  How Render builds and runs the backend
DEPLOY.md                    Step by step: putting it online for ₹0
frontend/                    The React website (see "Frontend" below)
backend/
├── app/
│   ├── main.py              Starts the app, CORS, plugs in routers, runs seeding on startup
│   ├── config.py            Settings from .env (database URL, session length, allowed sites)
│   ├── db.py                Database connection + get_session() for each request
│   ├── models.py            Database tables: College, CollegeAlias, User, AuthSession
│   ├── schemas.py           Shape of data in/out of the API (never exposes password_hash)
│   ├── security.py          bcrypt passwords + login tokens + get_current_user()
│   ├── college_matching.py  "DU" = "Delhi University" = "University of Delhi" logic
│   ├── storage.py           Photo safety (check, shrink, strip GPS) + save locally or to Cloudinary
│   ├── ratelimit.py         "Max N actions per M seconds" (login, requests, messages, reports)
│   ├── blocking.py          Block checks shared by books and requests
│   ├── codes.py             6-digit email codes: create, check, expiry, attempts
│   ├── emailer.py           Sending emails (prints to Terminal locally; Brevo when live)
│   ├── seed.py              Loads seed_colleges.json into the database
│   ├── seed_colleges.json   Starter list of colleges + their nicknames (edit to add more)
│   └── routers/
│       ├── auth.py          /auth/signup, /auth/login, /auth/me, /auth/logout
│       ├── colleges.py      /colleges search, get one, add new
│       ├── books.py         /books browse, create, edit, status, delete, photos
│       ├── requests.py      /requests buy requests (the deal) + chat
│       └── safety.py        /reports and /blocks
├── alembic.ini, migrations/ Database migrations (run automatically on startup)
├── tests/
│   ├── conftest.py          Shared test setup (temporary database + photo folder)
│   ├── test_step1.py        Login + college checks
│   ├── test_step2_books.py  Book, ownership, search and photo checks
│   ├── test_step3_requests.py  Deal flow, chat, unread, blocks, reports, rate limits
│   └── test_step4_account.py   Verification, codes, password reset/change, account deletion
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

## Email verification, passwords, account (step 4)

Locally, emails are **printed in the server's Terminal** (`EMAIL_BACKEND=console`), so no email account is needed for testing.

| Endpoint | Login? | Does |
|---|---|---|
| `POST /auth/verify-email` | yes | 6-digit code from the email → `email_verified: true` |
| `POST /auth/resend-verification` | yes | New code (max 1/minute, 5/hour); older codes stop working |
| `POST /auth/forgot-password` | no | Emails a reset code. Same answer whether or not the email exists |
| `POST /auth/reset-password` | no | Email + code + new password → logged out on every device |
| `POST /auth/change-password` | yes | Old + new password → other devices logged out |
| `POST /auth/delete-account` | yes | Password → personal data erased (see below) |

**Codes:** 6 random digits, stored only as a fingerprint, valid 15 minutes, one use, 5 wrong tries max.

**Unverified accounts** can log in and browse but can't list books, upload photos, request books or send messages (403).

**Deleting an account** keeps other people's history readable but removes the person: name → "Deleted user", email freed, password destroyed, their chat messages → "[message deleted]", unsold listings and all photos deleted, open deals cancelled (books released), sessions/blocks/codes removed.

## Frontend (step 6)

```
frontend/
├── index.html, vite.config.js, package.json   Setup (Vite + React + Tailwind)
├── vercel.json                                 Makes page links like /books/5 work on Vercel
├── .env.example                                VITE_API_URL = where the backend is
└── src/
    ├── main.jsx, App.jsx    Start-up + which page shows for which address
    ├── api.js               Every server call: adds the token, turns errors into readable text
    ├── auth.jsx             Who's logged in; RequireAuth for login-only pages
    ├── index.css            Colours and fonts
    ├── components/          Layout (top bar + unread badge), BookCard, CollegePicker,
    │                        ui (buttons, inputs, alerts…), Extras (pagination, report form)
    └── pages/               Browse, BookDetail, BookForm (sell/edit + photos), MyListings,
                             Messages (Inbox + Chat with polling), Account,
                             AuthPages (login, signup, verify, forgot, reset)
```

## Migrations (step 5)

Tables are created and updated by **migrations** in `backend/migrations/versions/`, which run automatically every time the server starts. After changing `models.py`:
```bash
cd backend && source .venv/bin/activate
alembic revision --autogenerate -m "what changed"   # writes a new migration file
```
Read the new file, restart the server, and the change is applied without losing data. Commit the file with your code.
