"""Owner-scoped data access.

Every query is filtered by owner *here*, not by callers remembering to. That is the
difference between a tenancy bug being impossible and being one forgotten `.where()`
away.

Missing and forbidden both raise :class:`NotFound`. The existence of another user's
notebook is itself information we decline to leak.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import NotFound
from noema.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class OwnedRepository(Generic[ModelT]):
    """CRUD for a model with an ``owner_id`` column."""

    def __init__(self, session: AsyncSession, model: type[ModelT], owner_id: uuid.UUID) -> None:
        self.session = session
        self.model = model
        self.owner_id = owner_id

    def _scoped(self) -> Select[tuple[ModelT]]:
        stmt = select(self.model).where(self.model.owner_id == self.owner_id)  # type: ignore[attr-defined]
        if hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]
        return stmt

    async def get(self, entity_id: uuid.UUID) -> ModelT:
        result = await self.session.execute(self._scoped().where(self.model.id == entity_id))  # type: ignore[attr-defined]
        entity = result.scalar_one_or_none()
        if entity is None:
            raise NotFound(f"{self.model.__name__} not found")
        return entity

    async def list(
        self,
        *,
        limit: int = 50,
        cursor: uuid.UUID | None = None,
        **filters: Any,
    ) -> tuple[Sequence[ModelT], uuid.UUID | None]:
        """Cursor pagination on the id column, which is time-sortable (UUIDv7)."""
        stmt = self._scoped()
        for field, value in filters.items():
            if value is not None:
                stmt = stmt.where(getattr(self.model, field) == value)
        if cursor is not None:
            stmt = stmt.where(self.model.id > cursor)  # type: ignore[attr-defined]

        stmt = stmt.order_by(self.model.id).limit(limit + 1)  # type: ignore[attr-defined]
        rows = list((await self.session.execute(stmt)).scalars().all())

        next_cursor = rows[limit - 1].id if len(rows) > limit else None  # type: ignore[attr-defined]
        return rows[:limit], next_cursor

    async def create(self, **values: Any) -> ModelT:
        entity = self.model(owner_id=self.owner_id, **values)  # type: ignore[call-arg]
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, entity_id: uuid.UUID, **values: Any) -> ModelT:
        entity = await self.get(entity_id)
        for field, value in values.items():
            if value is not None:
                setattr(entity, field, value)
        await self.session.flush()
        return entity

    async def delete(self, entity_id: uuid.UUID) -> None:
        """Soft-deletes when the model supports it, so export and undo stay possible."""
        entity = await self.get(entity_id)
        if hasattr(entity, "deleted_at"):
            from noema.db.base import utcnow

            entity.deleted_at = utcnow()  # type: ignore[attr-defined]
        else:
            await self.session.delete(entity)
        await self.session.flush()
