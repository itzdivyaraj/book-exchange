"""
Database connection.

WHY: every request needs to talk to the database. This file creates ONE "engine"
(the connection manager) and a helper that gives each request its own session
(a short conversation with the database) and closes it afterwards.
"""
from sqlmodel import Session, SQLModel, create_engine

from .config import DATABASE_URL

# SQLite needs this flag because FastAPI may use the connection from different threads.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# pool_pre_ping: before using a connection, check it's still alive.
# Important for Neon, which closes idle connections when it sleeps.
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)


def run_migrations() -> None:
    """
    Bring the database's tables up to date by running any migrations it hasn't had yet
    (the scripts in migrations/versions/). Safe to run on every startup: already-applied
    migrations are skipped. Works the same on SQLite (laptop) and Postgres (Neon).
    """
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    from . import models  # noqa: F401  (importing registers the tables)

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    command.upgrade(cfg, "head")


def get_session():
    """FastAPI dependency: opens a DB session for one request, then closes it."""
    with Session(engine) as session:
        yield session
