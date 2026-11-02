# Book Exchange

A marketplace for used college textbooks. Students list the books they no longer need, others at their college find them, chat in the app, and meet on campus to hand them over.

Every semester a lot of perfectly good textbooks end up on shelves while juniors buy the same titles new. Book Exchange tries to keep those books moving between students, at student prices.

![Browse page](docs/browse.png)

## Features

- **Accounts:** sign up with email verification (6-digit code), forgot/reset password, change password, delete account
- **Colleges:** search-as-you-type picker. "DU", "Delhi University" and "University of Delhi" all resolve to the same college, and new colleges can be added with a "did you mean…?" check to avoid duplicates
- **Listings:** title, author, edition, subject, semester, condition and price, with up to 3 photos per book. Photos are resized and stripped of location data on upload
- **Browse:** search by title, author, subject or ISBN; filter by college, semester, condition and price; sort and paginate
- **Deals:** request a book → seller accepts (book is reserved) → meet up → seller marks it sold. Either side can cancel, which releases the book
- **Chat:** a conversation per request, with an unread badge and new messages showing up without a refresh
- **Safety:** report listings or users, block users (works both ways), rate limits on login, requests and messages, and a pay-only-after-you-see-it reminder in every chat
- **Dark mode:** follows the system setting, with a toggle in the top bar

<img src="docs/chat-dark.png" alt="Chat in dark mode" width="720">

## Tech stack

| Part | Tech |
|---|---|
| Frontend | React 19, Vite, React Router, Tailwind CSS |
| Backend | Python, FastAPI, SQLModel (SQLAlchemy + Pydantic), Alembic |
| Database | SQLite in development, PostgreSQL (Neon) in production |
| Auth | bcrypt password hashing, opaque session tokens stored as SHA-256 hashes |
| Files & email | Cloudinary for photos, Brevo for transactional email |
| Hosting | Render (API), Vercel (frontend), free tiers |
| Tests | pytest: 47 API tests, run against both SQLite and Postgres |

## How it fits together

```
React (Vercel)  ──HTTPS + Bearer token──▶  FastAPI (Render)  ──▶  PostgreSQL (Neon)
                                              │
                                              ├──▶ Cloudinary (photos)
                                              └──▶ Brevo (verification / reset emails)
```

The API is the only thing that talks to the database. Every write checks two things: who you are (session token → user) and whether you're allowed (e.g. only a book's seller can edit it or accept a request). Accepting or completing a deal updates the request and the book in a single transaction, so they can't get out of sync.

## Running it locally

Requires Python 3.11+ and Node.js 20+.

**Backend** (http://127.0.0.1:8000/docs)
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```
Locally, emails aren't sent: verification and reset codes are printed in this terminal.

**Frontend** (http://localhost:5173)
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

**Tests**
```bash
cd backend
pytest
```
To run them against Postgres, point `TEST_DATABASE_URL` at an empty database.

## Project structure

```
backend/
  app/
    main.py              app setup, CORS, routers
    models.py            database tables
    schemas.py           request/response shapes
    security.py          password hashing, sessions, auth dependencies
    routers/             auth, colleges, books, requests (deals + chat), safety
    college_matching.py  normalising and fuzzy-matching college names
    storage.py           photo processing; local folder or Cloudinary
    emailer.py           console (dev) or Brevo
    ratelimit.py, codes.py, blocking.py
  migrations/            Alembic migrations (run on startup)
  tests/
frontend/
  src/
    api.js               API client
    auth.jsx             auth context
    pages/               Browse, BookDetail, BookForm, MyListings, Messages, Account, auth pages
    components/          layout, book card, college picker, UI pieces
render.yaml              Render config
```

Changing a table means editing `models.py` and generating a migration:
```bash
cd backend
alembic revision --autogenerate -m "describe the change"

```

## Deployment

The whole stack runs on free tiers: Neon (Postgres), Render (API), Vercel (frontend), Cloudinary (photos) and Brevo (email).

## What's next

- Ratings after a completed deal
- "Notify me" when a wanted book gets listed
- ISBN lookup to auto-fill title and author
- An admin view for reports and merging duplicate colleges
- Installable mobile app (PWA)
