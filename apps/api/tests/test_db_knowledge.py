"""Building the knowledge graph against a real database."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.config import Settings
from noema.db.models import (
    Concept,
    ConceptEdge,
    ConceptStatus,
    EdgeKind,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.knowledge.extraction import ExtractedConcept, Relation
from noema.knowledge.graph import GraphUpdate, apply_extraction
from noema.providers.gateway import AIGateway
from noema.providers.mock import MockProvider


@pytest.fixture
async def workspace(db: AsyncSession, user: User) -> Workspace:
    space = await OwnedRepository(db, Workspace, user.id).create(
        title="Computer Science", slug=f"cs-{uuid.uuid4().hex[:8]}"
    )
    await OwnedRepository(db, Subject, user.id).create(
        workspace_id=space.id, title="ML", slug=f"ml-{uuid.uuid4().hex[:8]}"
    )
    return space


@pytest.fixture
def gateway(settings: Settings) -> AIGateway:
    return AIGateway(MockProvider(dimensions=settings.noema_embedding_dim))


def concept(
    name: str,
    *,
    definition: str = "",
    prerequisites: list[str] | None = None,
    relations: list[Relation] | None = None,
    chunks: int = 2,
) -> ExtractedConcept:
    return ExtractedConcept(
        name=name,
        definition=definition,
        difficulty=0.5,
        prerequisites=prerequisites or [],
        relations=relations or [],
        source_chunk_ids=[str(uuid.uuid4()) for _ in range(chunks)],
    )


async def apply(
    db: AsyncSession,
    user: User,
    workspace: Workspace,
    concepts: list[ExtractedConcept],
    gateway: AIGateway | None = None,
) -> GraphUpdate:
    return await apply_extraction(
        db, concepts, owner_id=user.id, workspace_id=workspace.id, gateway=gateway
    )


async def concepts_in(db: AsyncSession, workspace: Workspace) -> list[Concept]:
    return list(
        (
            await db.scalars(
                select(Concept)
                .where(Concept.workspace_id == workspace.id)
                .order_by(Concept.name)
            )
        ).all()
    )


async def test_concepts_are_stored_with_their_provenance(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    update = await apply(db, user, workspace, [concept("Backpropagation")])

    assert update.created == 1
    stored = (await concepts_in(db, workspace))[0]
    assert stored.name == "Backpropagation"
    assert stored.normalized_name == "backpropagation"
    assert len(stored.source_chunk_ids) == 2


async def test_a_concept_seen_once_stays_a_candidate(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    """One mention is an extraction artefact as often as it is a concept."""
    await apply(db, user, workspace, [concept("Backpropagation", chunks=1)])

    stored = (await concepts_in(db, workspace))[0]
    assert stored.status is ConceptStatus.CANDIDATE


async def test_corroboration_promotes_a_candidate(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    await apply(db, user, workspace, [concept("Backpropagation", chunks=2)])

    stored = (await concepts_in(db, workspace))[0]
    assert stored.status is ConceptStatus.ACTIVE


async def test_the_same_concept_named_differently_is_not_duplicated(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    await apply(db, user, workspace, [concept("Chain Rule")])
    update = await apply(db, user, workspace, [concept("the chain rule")])

    assert update.merged == 1
    assert len(await concepts_in(db, workspace)) == 1


async def test_merging_accumulates_provenance_and_records_the_alias(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    await apply(db, user, workspace, [concept("Chain Rule", chunks=2)])
    await apply(db, user, workspace, [concept("Chain Rules", chunks=3)])

    stored = (await concepts_in(db, workspace))[0]
    assert len(stored.source_chunk_ids) == 5
    assert "Chain Rules" in stored.aliases


async def test_an_existing_definition_is_never_overwritten(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    """It may have been written by the user, and silently replacing it is exactly
    the undo the graph promises not to do."""
    await apply(db, user, workspace, [concept("Chain Rule", definition="The good one.")])
    await apply(db, user, workspace, [concept("chain rule", definition="A worse one.")])

    assert (await concepts_in(db, workspace))[0].definition == "The good one."


async def test_a_missing_definition_is_filled_in_later(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    await apply(db, user, workspace, [concept("Chain Rule", definition="")])
    await apply(db, user, workspace, [concept("chain rule", definition="Now defined.")])

    assert (await concepts_in(db, workspace))[0].definition == "Now defined."


async def test_distinct_concepts_stay_distinct(
    db: AsyncSession, user: User, workspace: Workspace, gateway: AIGateway
) -> None:
    await apply(
        db,
        user,
        workspace,
        [concept("Gradient Descent"), concept("Fourier Transform")],
        gateway,
    )
    assert len(await concepts_in(db, workspace)) == 2


async def test_prerequisites_become_edges_pointing_backwards(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    await apply(
        db,
        user,
        workspace,
        [concept("Chain Rule"), concept("Backpropagation", prerequisites=["Chain Rule"])],
    )

    edge = (await db.scalars(select(ConceptEdge))).one()
    src = await db.get(Concept, edge.src_id)
    dst = await db.get(Concept, edge.dst_id)

    assert edge.kind is EdgeKind.PREREQUISITE_OF
    assert src is not None and src.name == "Chain Rule"
    assert dst is not None and dst.name == "Backpropagation"


async def test_a_prerequisite_naming_an_unknown_concept_is_skipped(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    await apply(
        db, user, workspace, [concept("Backpropagation", prerequisites=["Topology"])]
    )
    assert (await db.scalars(select(ConceptEdge))).all() == []


async def test_a_circular_prerequisite_is_rejected(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    """An extraction error, not a modelling nuance: left in, the prerequisite engine
    would recurse forever looking for where to start."""
    update = await apply(
        db,
        user,
        workspace,
        [
            concept("A", prerequisites=["B"]),
            concept("B", prerequisites=["A"]),
        ],
    )

    assert update.cycles_rejected >= 1
    assert update.edges_added == 1

    edges = (await db.scalars(select(ConceptEdge))).all()
    assert len(edges) == 1


async def test_relations_are_stored_with_their_kind(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    await apply(
        db,
        user,
        workspace,
        [
            concept(
                "Gradient Descent", relations=[Relation("Optimization", EdgeKind.PART_OF)]
            ),
            concept("Optimization"),
        ],
    )

    edge = (await db.scalars(select(ConceptEdge))).one()
    assert edge.kind is EdgeKind.PART_OF


async def test_re_running_extraction_does_not_duplicate_edges(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    batch = [
        concept("Chain Rule"),
        concept("Backpropagation", prerequisites=["Chain Rule"]),
    ]

    first = await apply(db, user, workspace, batch)
    second = await apply(db, user, workspace, batch)

    assert first.edges_added == 1
    assert second.edges_added == 0
    assert len((await db.scalars(select(ConceptEdge))).all()) == 1


async def test_concepts_are_scoped_to_their_workspace(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    """Canonical at workspace scope: the same idea in two notebooks is one concept,
    but two workspaces are two separate maps."""
    other = await OwnedRepository(db, Workspace, user.id).create(
        title="Biology", slug=f"bio-{uuid.uuid4().hex[:8]}"
    )

    await apply(db, user, workspace, [concept("Chain Rule")])
    await apply(db, user, other, [concept("Chain Rule")])

    assert len(await concepts_in(db, workspace)) == 1
    assert len(await concepts_in(db, other)) == 1


async def test_extraction_without_embeddings_still_deduplicates_by_name(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    await apply(db, user, workspace, [concept("Chain Rule")], gateway=None)
    update = await apply(db, user, workspace, [concept("The Chain Rule")], gateway=None)

    assert update.merged == 1
    assert len(await concepts_in(db, workspace)) == 1


async def test_an_empty_extraction_changes_nothing(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    update = await apply(db, user, workspace, [])
    assert update.created == 0
    assert await concepts_in(db, workspace) == []
