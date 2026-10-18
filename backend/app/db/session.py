"""SQLAlchemy session and engine.

The engine is created once at import time and reused. For SQLite we enable
``check_same_thread=False`` because FastAPI may use the same connection
across request threads when the pool is small.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

_engine_kwargs: dict[str, object] = {"future": True, "pool_pre_ping": True}
if _settings.database_url.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine: Engine = create_engine(_settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a SQLAlchemy session and ensures close."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
