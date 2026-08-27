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
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import NotFound
from noema.db.base import OwnedEntity, utcnow


class OwnedRepository[ModelT: OwnedEntity]:
    """CRUD for a model with an ``owner_id`` column."""

    def __init__(
        self, session: AsyncSession, model: type[ModelT], owner_id: uuid.UUID
    ) -> None:
        self.session = session
        self.model = model
        self.owner_id = owner_id

    def _scoped(self) -> Select[tuple[ModelT]]:
        stmt = select(self.model).where(self.model.owner_id == self.owner_id)
        # Only some models are soft-deleted; the rest have no column to filter on.
        deleted_at = getattr(self.model, "deleted_at", None)
        if deleted_at is not None:
            stmt = stmt.where(deleted_at.is_(None))
        return stmt

    async def get(self, entity_id: uuid.UUID) -> ModelT:
        result = await self.session.execute(
            self._scoped().where(self.model.id == entity_id)
        )
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
            stmt = stmt.where(self.model.id > cursor)

        stmt = stmt.order_by(self.model.id).limit(limit + 1)
        rows = list((await self.session.execute(stmt)).scalars().all())

        next_cursor = rows[limit - 1].id if len(rows) > limit else None
        return rows[:limit], next_cursor

    async def create(self, **values: Any) -> ModelT:
        entity = self.model(owner_id=self.owner_id, **values)
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, entity_id: uuid.UUID, **values: Any) -> ModelT:
        """Apply every field in ``values``, including an explicit ``None``.

        Callers pass ``payload.model_dump(exclude_unset=True)``, which already
        drew the "was this field in the request" line — a key present with value
        ``None`` means the client explicitly asked to clear a nullable column, not
        that nothing should happen. Skipping ``None`` here would make that request
        a silent no-op, indistinguishable from the field never having been sent.
        """
        entity = await self.get(entity_id)
        for field, value in values.items():
            setattr(entity, field, value)
        await self.session.flush()
        return entity

    async def delete(self, entity_id: uuid.UUID) -> None:
        """Soft-deletes when the model supports it, so export and undo stay possible."""
        entity = await self.get(entity_id)
        if hasattr(entity, "deleted_at"):
            entity.deleted_at = utcnow()
        else:
            await self.session.delete(entity)
        await self.session.flush()
