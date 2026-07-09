"""Async SQLAlchemy 2.0 database engine, session factory, and base model.

Lazy initialisation — engine is created on first use, not at import time.
Uses the repository pattern — no direct ``db.session`` calls outside repositories.
"""

from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=1)
def _get_engine_url() -> str:
    """Return the database URL, ensuring an async driver is used for dev SQLite."""
    url = settings.database_url
    if url.startswith('sqlite://'):
        url = url.replace('sqlite://', 'sqlite+aiosqlite://', 1)
    return url


@lru_cache(maxsize=1)
def get_engine():
    """Create (or return cached) async SQLAlchemy engine."""
    return create_async_engine(
        _get_engine_url(),
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout,
        pool_pre_ping=settings.database_pool_pre_ping,
    )


@lru_cache(maxsize=1)
def get_session_factory():
    """Create (or return cached) async session factory bound to the engine."""
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


# ── Base Model ─────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    """Declarative base for all ORM models.

    All models should inherit from this and set ``__tablename__``.
    """


# ── Lifecycle ──────────────────────────────────────────────────────────


async def initialize_database() -> None:
    """Create all tables defined by models that inherit from ``Base``.

    Call once during application startup.
    In production, use Alembic migrations instead.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info('database_tables_created')


async def dispose_database() -> None:
    """Dispose of the connection pool. Call during application shutdown."""
    engine = get_engine()
    await engine.dispose()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    log.info('database_disposed')


# ── Session Dependency ─────────────────────────────────────────────────


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session.

    Usage::

        @router.get('/items')
        async def list_items(db: AsyncSession = Depends(get_db_session)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
