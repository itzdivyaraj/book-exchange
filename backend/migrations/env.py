"""
Alembic's connection to our app: which database (DATABASE_URL from config.py)
and what the tables SHOULD look like (the classes in models.py).
"""
from alembic import context
from sqlmodel import SQLModel

from app import models  # noqa: F401  (importing registers all tables)
from app.config import DATABASE_URL
from app.db import engine

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = context.config.attributes.get("connection")
    if connection is None:
        with engine.connect() as connection:
            _run(connection)
    else:
        _run(connection)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite can't change columns in place; "batch" mode copies the table instead.
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
