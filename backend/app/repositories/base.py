from __future__ import annotations

"""Base repository with async CRUD operations.

Every repository inherits from ``BaseRepository`` which provides:

  - ``create()`` — insert one record
  - ``create_many()`` — bulk insert
  - ``get()`` — fetch by primary key
  - ``get_by()`` — fetch first matching a filter
  - ``list()`` — paginated list with ordering
  - ``list_by()`` — filtered paginated list
  - ``update()`` — partial update by primary key
  - ``upsert()`` — insert or update by unique constraint
  - ``delete()`` — soft/hard delete by primary key
  - ``count()`` — total matching rows
  - ``exists()`` — boolean existence check
  - ``paginate()`` — page metadata helper

All operations use SQLAlchemy 2.0 async sessions. All return
proper ORM instances. No raw SQL leaks into services.
"""

import math
from collections.abc import Sequence
from typing import Any, Generic, Optional, TypeVar

from sqlalchemy import Select, UnaryExpression, asc, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import delete as sa_delete

from app.core.database import Base
from app.core.exceptions import NotFoundError
from app.core.logger import get_logger

log = get_logger(__name__)

ModelT = TypeVar('ModelT', bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic async repository with standard CRUD operations.

    Usage::

        class UserRepository(BaseRepository[User]):
            model_class = User

        repo = UserRepository(db_session)
        user = await repo.create({"email": "a@b.com"})
        users = await repo.list(page=1, page_size=20)
    """

    model_class: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        if not hasattr(self, 'model_class') or self.model_class is None:  # type: ignore[has-type]
            raise TypeError(f'{self.__class__.__name__} must define model_class')
        self.session = session

    # ── Create ─────────────────────────────────────────────────────────

    async def create(self, data: dict[str, Any]) -> ModelT:
        """Create and return a new record."""
        instance = self.model_class(**data)
        self.session.add(instance)
        await self.session.flush()
        log.debug('repository_create', model=self.model_class.__name__, id=getattr(instance, 'id', None))
        return instance

    async def create_many(self, items: list[dict[str, Any]]) -> list[ModelT]:
        """Bulk-create multiple records."""
        instances = [self.model_class(**data) for data in items]
        self.session.add_all(instances)
        await self.session.flush()
        log.debug('repository_create_many', model=self.model_class.__name__, count=len(instances))
        return instances

    # ── Read ───────────────────────────────────────────────────────────

    async def get(self, id: str) -> ModelT:
        """Fetch a record by primary key.

        Raises:
            NotFoundError: If no record with that ID exists.
        """
        instance = await self.session.get(self.model_class, id)
        if instance is None:
            raise NotFoundError(resource=self.model_class.__name__, identifier=id)
        return instance

    async def get_or_none(self, id: str) -> Optional[ModelT]:
        """Fetch by primary key, returning None if not found."""
        return await self.session.get(self.model_class, id)

    async def get_by(self, **filters: Any) -> Optional[ModelT]:
        """Fetch the first record matching all filter conditions.

        Example::

            user = await repo.get_by(email='a@b.com')
        """
        stmt = select(self.model_class).filter_by(**filters).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        order_by: Optional[str] = None,
        descending: bool = False,
    ) -> tuple[Sequence[ModelT], int]:
        """Paginated list of records.

        Args:
            page: 1-indexed page number.
            page_size: Records per page.
            order_by: Column name to sort by (defaults to primary key).
            descending: Sort descending if True.

        Returns:
            Tuple of (records, total_count).
        """
        base_query = select(self.model_class)
        total = await self._count(base_query)
        order_col = self._resolve_order_column(order_by, descending)
        if order_col is not None:
            base_query = base_query.order_by(order_col)
        offset = (page - 1) * page_size
        base_query = base_query.offset(offset).limit(page_size)
        result = await self.session.execute(base_query)
        records = result.scalars().all()
        return records, total

    async def list_by(
        self,
        page: int = 1,
        page_size: int = 20,
        order_by: Optional[str] = None,
        descending: bool = False,
        **filters: Any,
    ) -> tuple[Sequence[ModelT], int]:
        """Paginated filtered list.

        Example::

            records, total = await repo.list_by(subject='math', page=1)
        """
        base_query = select(self.model_class).filter_by(**filters)
        total = await self._count(base_query)
        order_col = self._resolve_order_column(order_by, descending)
        if order_col is not None:
            base_query = base_query.order_by(order_col)
        offset = (page - 1) * page_size
        base_query = base_query.offset(offset).limit(page_size)
        result = await self.session.execute(base_query)
        records = result.scalars().all()
        return records, total

    async def find(self, **filters: Any) -> Sequence[ModelT]:
        """Unpaginated filtered list. Use sparingly — prefer ``list_by``."""
        stmt = select(self.model_class).filter_by(**filters)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    # ── Update ─────────────────────────────────────────────────────────

    async def update(self, id: str, data: dict[str, Any]) -> ModelT:
        """Partial update by primary key.

        Raises:
            NotFoundError: If no record with that ID exists.
        """
        instance = await self.get(id)
        for key, value in data.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        await self.session.flush()
        log.debug('repository_update', model=self.model_class.__name__, id=id, fields=list(data.keys()))
        return instance

    async def upsert(
        self,
        data: dict[str, Any],
        constraint: list[str],
    ) -> ModelT:
        """Insert or update based on unique constraint columns.

        Checks if a record matching ``constraint`` columns exists.
        If found, updates it with ``data``. Otherwise creates new.

        Args:
            data: Full field values for create/update.
            constraint: Column names that define uniqueness.

        Returns:
            The existing or newly created instance.
        """
        filters = {col: data[col] for col in constraint if col in data}
        existing = await self.get_by(**filters)
        if existing:
            for key, value in data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            await self.session.flush()
            return existing
        return await self.create(data)

    # ── Delete ─────────────────────────────────────────────────────────

    async def delete(self, id: str, hard: bool = False) -> None:
        """Delete a record by primary key.

        Args:
            id: Primary key value.
            hard: If True, performs a hard delete. Otherwise expects
                  the model to have an ``is_active`` boolean for soft delete.
        """
        instance = await self.get(id)
        if hard:
            await self.session.delete(instance)
        else:
            if hasattr(instance, 'is_active'):
                instance.is_active = False  # type: ignore[assignment]
            else:
                await self.session.delete(instance)
        await self.session.flush()
        log.debug('repository_delete', model=self.model_class.__name__, id=id, hard=hard)

    async def delete_by(self, **filters: Any) -> int:
        """Delete all records matching filters.

        Returns the number of deleted rows.
        """
        stmt = sa_delete(self.model_class).filter_by(**filters)
        result = await self.session.execute(stmt)
        await self.session.flush()
        log.debug('repository_delete_by', model=self.model_class.__name__, filters=filters, deleted=result.rowcount)
        return result.rowcount

    # ── Aggregates ────────────────────────────────────────────────────

    async def count(self, **filters: Any) -> int:
        """Count records matching filters (or all if no filters)."""
        stmt = select(func.count()).select_from(self.model_class)
        if filters:
            stmt = stmt.filter_by(**filters)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def exists(self, **filters: Any) -> bool:
        """Check if any record matches the given filters."""
        stmt = select(self.model_class).filter_by(**filters).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    def paginate(self, page: int, page_size: int, total: int) -> dict[str, Any]:
        """Return pagination metadata.

        Returns::

            {
                "page": 1,
                "page_size": 20,
                "total": 100,
                "total_pages": 5,
                "has_next": True,
                "has_previous": False,
            }
        """
        total_pages = max(1, math.ceil(total / max(page_size, 1)))
        return {
            'page': page,
            'page_size': page_size,
            'total': total,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_previous': page > 1,
        }

    # ── Internal ──────────────────────────────────────────────────────

    async def _count(self, query: Select) -> int:
        """Count total rows for a select query."""
        count_query = select(func.count()).select_from(query.subquery())
        result = await self.session.execute(count_query)
        return result.scalar_one()

    def _resolve_order_column(
        self,
        order_by: Optional[str],
        descending: bool,
    ) -> Optional[UnaryExpression]:
        """Resolve an order column name to a SQLAlchemy expression."""
        if order_by is None:
            return None
        if hasattr(self.model_class, order_by):
            column = getattr(self.model_class, order_by)
            return desc(column) if descending else asc(column)
        log.warning('repository_order_column_not_found', model=self.model_class.__name__, column=order_by)
        return None
