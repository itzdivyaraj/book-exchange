"""
The entry point. `uvicorn app.main:app --reload` starts the server from here.

It:
  - creates the FastAPI app
  - allows your React site to call it (CORS)
  - creates tables + loads the college list on startup
  - plugs in the routers (auth, colleges, books)
  - serves uploaded photos at /uploads/... (local only; Cloudinary when live)
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_ORIGINS, UPLOAD_DIR
from .db import create_db_and_tables
from .routers import auth, books, colleges
from .seed import seed_colleges


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Runs once when the server starts.
    create_db_and_tables()
    seed_colleges()
    yield


app = FastAPI(title="Book Exchange API", version="0.2.0", lifespan=lifespan)

# CORS: browsers block a website from calling a different address unless the server allows it.
# React (localhost:5173) and this API (localhost:8000) count as different addresses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(colleges.router)
app.include_router(books.router)

# Photos saved in the uploads/ folder become viewable at http://127.0.0.1:8000/uploads/<name>.jpg
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/", tags=["health"])
def health():
    """Quick check that the server is up."""
    return {"status": "ok"}
