"""
Settings for the app, read from environment variables (or a .env file).

WHY: the same code must run on your laptop (SQLite) and online (Postgres on Neon).
Instead of editing code when you deploy, you only change DATABASE_URL.
"""
import os

from dotenv import load_dotenv

load_dotenv()  # reads backend/.env if it exists

# Local default: a file called books.db inside the backend folder.
# Online: set DATABASE_URL to the Postgres URL Neon gives you.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./books.db")

# Neon/Render hand out URLs like "postgresql://..." or "postgres://...".
# SQLAlchemy needs to be told which driver to use: we installed psycopg (version 3).
for prefix in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(prefix):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len(prefix):]
        break

# How long a login lasts before the user must log in again.
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "30"))

# Which websites are allowed to call this API from a browser (your React app).
# Comma-separated. Locally React runs on http://localhost:5173.
FRONTEND_ORIGINS = [
    o.strip()
    for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]

# ---------- Step 2: photos ----------
# "local" = save in the uploads/ folder (laptop). "cloudinary" = save online (live site).
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")
# Copy this from your Cloudinary dashboard ("API environment variable"). Looks like
# cloudinary://API_KEY:API_SECRET@CLOUD_NAME   <- a SECRET: only in .env / Render settings.
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL", "")
# Where uploaded photos are saved on your laptop (STORAGE_BACKEND=local).
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
# The address of THIS backend, used to build full photo links like
# http://127.0.0.1:8000/uploads/abc.jpg that the React site can load.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "5"))
MAX_IMAGES_PER_BOOK = 3

# ---------- Step 4: email ----------
# "console" = print emails in the Terminal (laptop). "brevo" = really send them (live site).
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "console")
EMAIL_FROM = os.getenv("EMAIL_FROM", "Book Exchange <no-reply@example.com>")
# Brevo: the API key from Brevo -> SMTP & API -> API Keys. A SECRET.
# EMAIL_FROM must use a sender address you've verified in Brevo (e.g. your Gmail).
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
CODE_MINUTES = 15        # how long a code stays valid
CODE_MAX_ATTEMPTS = 5    # wrong guesses allowed per code
