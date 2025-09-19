"""Database engine and session management utilities."""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import get_settings


Base = declarative_base()


def build_postgres_url(
    *,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
) -> str:
    return f"postgresql+psycopg://{username}:{password}@{host}:{port}/{database}"


def _build_engine(database_url: str) -> Engine:
    return create_engine(database_url, echo=False, future=True, pool_pre_ping=True)


@lru_cache
def get_engine(database_url: str | None = None) -> Engine:
    """Return a cached SQLAlchemy engine."""

    if database_url is None:
        database_url = get_settings().database_url
    return _build_engine(database_url)


@lru_cache
def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    """Return a session factory bound to the configured engine."""

    engine = get_engine(database_url)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(database_url: str | None = None) -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""

    session_factory = get_session_factory(database_url)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
