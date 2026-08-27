"""The knowledge graph.

Everything a user decides here is permanent: renames, merges and prerequisite edits
are never overwritten by a later ingest. A graph that quietly undoes your
corrections is one you stop correcting, and then it is worse than no graph.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

# ruff: noqa: B008 — Query() in defaults is FastAPI's documented signature style
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator
from sqlalchemy import or_, select

from noema.api.v1 import deps
from noema.api.v1.schemas import reject_explicit_null
from noema.core.errors import Conflict, NotFound
from noema.db.models import Concept, ConceptEdge, ConceptStatus, EdgeKind, EdgeOrigin
from noema.knowledge.resolution import normalize_name, would_create_cycle

router = APIRouter(
    prefix="/concepts", tags=["concepts"], dependencies=[Depends(deps.require_csrf)]
)

MAX_GRAPH_DEPTH = 3


class ConceptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    definition: str | None
    difficulty_prior: float
    status: ConceptStatus
    aliases: list[str]
    source_chunk_ids: list[uuid.UUID]
    created_at: datetime


class ConceptUpdate(BaseModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None
    definition: str | None = None
    status: Literal["candidate", "active", "rejected"] | None = None

    @model_validator(mode="after")
    def _no_null_required_fields(self) -> ConceptUpdate:
        # `definition` is genuinely nullable (Concept.definition has no NOT NULL
        # constraint) and must stay clearable — only name/status back a NOT NULL
        # column.
        reject_explicit_null(self, "name", "status")
        return self


class MergeRequest(BaseModel):
    source_ids: list[uuid.UUID]
    target_id: uuid.UUID


class EdgeIn(BaseModel):
    src_id: uuid.UUID
    dst_id: uuid.UUID
    kind: EdgeKind
    weight: float = 0.8


class EdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    src_id: uuid.UUID
    dst_id: uuid.UUID
    kind: EdgeKind
    weight: float
    origin: EdgeOrigin


class GraphOut(BaseModel):
    nodes: list[ConceptOut]
    edges: list[EdgeOut]


@router.get("", response_model=list[ConceptOut])
async def list_concepts(
    user: deps.CurrentUser,
    db: deps.SessionDep,
    workspace_id: uuid.UUID | None = None,
    status_filter: ConceptStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, le=500),
) -> list[ConceptOut]:
    """List concepts.

    Candidates are included only when explicitly asked for: an unproven concept in
    the default view is noise the user has to mentally filter every time.
    """
    stmt = select(Concept).where(Concept.owner_id == user.id)
    if workspace_id is not None:
        stmt = stmt.where(Concept.workspace_id == workspace_id)
    stmt = stmt.where(
        Concept.status == status_filter
        if status_filter is not None
        else Concept.status == ConceptStatus.ACTIVE
    )

    rows = (await db.scalars(stmt.order_by(Concept.name).limit(limit))).all()
    return [ConceptOut.model_validate(row) for row in rows]


@router.get("/{concept_id}", response_model=ConceptOut)
async def get_concept(
    concept_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> ConceptOut:
    return ConceptOut.model_validate(await _get(db, user.id, concept_id))


@router.patch("/{concept_id}", response_model=ConceptOut)
async def update_concept(
    concept_id: uuid.UUID,
    payload: ConceptUpdate,
    user: deps.CurrentUser,
    db: deps.SessionDep,
) -> ConceptOut:
    concept = await _get(db, user.id, concept_id)
    fields = payload.model_fields_set

    if "name" in fields:
        assert payload.name is not None  # reject_explicit_null already ruled out None
        normalized = normalize_name(payload.name)
        clash = await db.scalar(
            select(Concept).where(
                Concept.workspace_id == concept.workspace_id,
                Concept.normalized_name == normalized,
                Concept.id != concept.id,
            )
        )
        if clash is not None:
            raise Conflict(
                f"{clash.name!r} already exists in this workspace. Merge them instead."
            )
        concept.name = payload.name
        concept.normalized_name = normalized

    # Explicit null is a real request to clear the definition, not "leave it
    # alone" — `definition` has no NOT NULL constraint, unlike name/status.
    if "definition" in fields:
        concept.definition = payload.definition or None
    if "status" in fields:
        assert payload.status is not None  # reject_explicit_null already ruled out None
        concept.status = ConceptStatus(payload.status)

    await db.flush()
    return ConceptOut.model_validate(concept)


@router.post("/merge", response_model=ConceptOut)
async def merge_concepts(
    payload: MergeRequest, user: deps.CurrentUser, db: deps.SessionDep
) -> ConceptOut:
    """Fold concepts into one, keeping their provenance and their edges.

    The sources are marked merged rather than deleted, so a wrong merge can be
    understood after the fact instead of leaving a hole where a concept was.
    """
    target = await _get(db, user.id, payload.target_id)

    for source_id in payload.source_ids:
        if source_id == target.id:
            continue
        source = await _get(db, user.id, source_id)
        if source.workspace_id != target.workspace_id:
            raise Conflict("Concepts from different workspaces cannot be merged.")

        target.source_chunk_ids = sorted(
            set(target.source_chunk_ids) | set(source.source_chunk_ids)
        )
        target.aliases = sorted({*target.aliases, source.name, *source.aliases})
        if not target.definition:
            target.definition = source.definition

        edges = (
            await db.scalars(
                select(ConceptEdge).where(
                    or_(ConceptEdge.src_id == source.id, ConceptEdge.dst_id == source.id)
                )
            )
        ).all()
        for edge in edges:
            other = edge.dst_id if edge.src_id == source.id else edge.src_id
            if other == target.id:
                # The merge would turn this into a self-loop.
                await db.delete(edge)
                continue
            if edge.src_id == source.id:
                edge.src_id = target.id
            else:
                edge.dst_id = target.id

        source.status = ConceptStatus.MERGED
        source.merged_into_id = target.id

    target.status = ConceptStatus.ACTIVE
    await db.flush()
    return ConceptOut.model_validate(target)


@router.get("/{concept_id}/graph", response_model=GraphOut)
async def concept_graph(
    concept_id: uuid.UUID,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    depth: int = Query(default=2, ge=1, le=MAX_GRAPH_DEPTH),
) -> GraphOut:
    """The neighbourhood around a concept, for the visualiser.

    Bounded by depth rather than returning the workspace: a graph view that renders
    everything is a hairball nobody can read.
    """
    root = await _get(db, user.id, concept_id)

    seen: dict[uuid.UUID, Concept] = {root.id: root}
    frontier = {root.id}
    edges: dict[uuid.UUID, ConceptEdge] = {}

    for _ in range(depth):
        if not frontier:
            break
        rows = (
            await db.scalars(
                select(ConceptEdge).where(
                    ConceptEdge.owner_id == user.id,
                    or_(
                        ConceptEdge.src_id.in_(frontier),
                        ConceptEdge.dst_id.in_(frontier),
                    ),
                )
            )
        ).all()

        next_frontier: set[uuid.UUID] = set()
        for edge in rows:
            edges[edge.id] = edge
            for node_id in (edge.src_id, edge.dst_id):
                if node_id not in seen:
                    next_frontier.add(node_id)
        frontier = next_frontier

        for node_id in frontier:
            concept = await db.get(Concept, node_id)
            if concept is not None and concept.owner_id == user.id:
                seen[node_id] = concept

    return GraphOut(
        nodes=[ConceptOut.model_validate(c) for c in seen.values()],
        edges=[EdgeOut.model_validate(e) for e in edges.values()],
    )


@router.post("/edges", response_model=EdgeOut, status_code=status.HTTP_201_CREATED)
async def create_edge(
    payload: EdgeIn, user: deps.CurrentUser, db: deps.SessionDep
) -> EdgeOut:
    src = await _get(db, user.id, payload.src_id)
    dst = await _get(db, user.id, payload.dst_id)

    if src.id == dst.id:
        raise Conflict("A concept cannot relate to itself.")
    if src.workspace_id != dst.workspace_id:
        raise Conflict("Concepts from different workspaces cannot be linked.")

    if payload.kind is EdgeKind.PREREQUISITE_OF:
        existing = [
            (str(a), str(b))
            for a, b in (
                await db.execute(
                    select(ConceptEdge.src_id, ConceptEdge.dst_id)
                    .join(Concept, Concept.id == ConceptEdge.src_id)
                    .where(
                        Concept.workspace_id == src.workspace_id,
                        ConceptEdge.kind == EdgeKind.PREREQUISITE_OF,
                    )
                )
            ).all()
        ]
        if would_create_cycle(existing, str(src.id), str(dst.id)):
            raise Conflict(
                f"{src.name!r} already depends on {dst.name!r}, directly or through "
                "other concepts. Prerequisites have to point one way."
            )

    edge = ConceptEdge(
        owner_id=user.id,
        src_id=src.id,
        dst_id=dst.id,
        kind=payload.kind,
        weight=payload.weight,
        # A user's edge outranks an extracted one and is never overwritten.
        origin=EdgeOrigin.USER,
    )
    db.add(edge)
    await db.flush()
    return EdgeOut.model_validate(edge)


@router.delete("/edges/{edge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_edge(
    edge_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> None:
    edge = await db.scalar(
        select(ConceptEdge).where(
            ConceptEdge.id == edge_id, ConceptEdge.owner_id == user.id
        )
    )
    if edge is None:
        raise NotFound("Edge not found")
    await db.delete(edge)
    await db.flush()


async def _get(
    db: deps.SessionDep, owner_id: uuid.UUID, concept_id: uuid.UUID
) -> Concept:
    concept = await db.scalar(
        select(Concept).where(Concept.id == concept_id, Concept.owner_id == owner_id)
    )
    if concept is None:
        raise NotFound("Concept not found")
    return concept


__all__ = ["router"]
