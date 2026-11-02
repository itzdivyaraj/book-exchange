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

# Some providers hand out URLs starting with "postgres://"; SQLAlchemy needs "postgresql://".
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

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
# Where uploaded photos are saved on your laptop (later: Cloudinary instead).
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
# The address of THIS backend, used to build full photo links like
# http://127.0.0.1:8000/uploads/abc.jpg that the React site can load.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "5"))
MAX_IMAGES_PER_BOOK = 3
