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


def create_db_and_tables() -> None:
    """Create any tables that don't exist yet (based on the classes in models.py)."""
    from . import models  # noqa: F401  (importing registers the tables)

    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency: opens a DB session for one request, then closes it."""
    with Session(engine) as session:
        yield session
