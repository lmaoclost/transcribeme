"""Database setup and helpers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()


def _create_engine(database_url: str):
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


engine = _create_engine(_settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create database tables if they do not exist."""
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_sqlite_migrations()


def _apply_sqlite_migrations() -> None:
    """Apply lightweight migrations for SQLite deployments."""
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.connect() as connection:
        existing_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(jobs)").fetchall()
        }
        for col, ddl in [
            ("requested_format", "ALTER TABLE jobs ADD COLUMN requested_format VARCHAR(64)"),
            ("input_type", "ALTER TABLE jobs ADD COLUMN input_type VARCHAR(16) DEFAULT 'url'"),
            ("original_filename", "ALTER TABLE jobs ADD COLUMN original_filename TEXT"),
            ("source_lang", "ALTER TABLE jobs ADD COLUMN source_lang VARCHAR(16)"),
        ]:
            if col not in existing_columns:
                connection.execute(text(ddl))
                connection.commit()


@contextmanager
def session_scope() -> Generator:
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Generator:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
