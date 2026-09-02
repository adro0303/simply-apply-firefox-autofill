"""SQLite engine and session management.

Single-user, single-file. `check_same_thread=False` is required because FastAPI runs
sync endpoints in a threadpool, and SQLAlchemy hands connections across those threads.
WAL mode lets a read (a search) proceed while a write (an application log) is in flight,
which matters once tailoring and browsing overlap.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()

engine = create_engine(
    f"sqlite:///{_settings.db_path}",
    connect_args={"check_same_thread": False},
    future=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> str:
    """Create tables and ensure the extension auth token exists.

    Returns the token so the caller (main.py's lifespan) can log it once at startup —
    this is the only place it's ever surfaced in plaintext outside the DB.
    """
    from app import models  # noqa: F401
    from app.services import settings_store

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        return settings_store.extension_token(db)
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
