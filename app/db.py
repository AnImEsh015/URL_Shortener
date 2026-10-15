"""Database connection and session management.

Provides sync SQLAlchemy 2.x engine, SessionLocal factory, Declarative Base,
and the get_db dependency for FastAPI endpoints.
"""

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# pool_pre_ping=True checks connection health before issuing queries to prevent stale connection errors
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""
    pass


def get_db() -> Generator[Session, None, None]:
    """Dependency that provides a database session per request and guarantees closure."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
