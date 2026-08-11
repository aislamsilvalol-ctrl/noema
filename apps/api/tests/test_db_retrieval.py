"""Hybrid retrieval against real Postgres.

Exercises the pgvector distance operator and the generated tsvector together — the
two halves that a unit test over fused ranks cannot reach.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.config import Settings
from noema.db.models import (
    Notebook,
    Source,
    SourceKind,
    SourceStatus,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.ingestion.pipeline import ingest_source
from noema.ingestion.storage import LocalStorage, storage_key
from noema.providers.gateway import AIGateway
from noema.providers.mock import MockProvider
from noema.retrieval.search import RetrievalSettings, retrieve

CALCULUS = b"""# Calculus

## The Chain Rule

The derivative of a composition is the product of the derivatives.

## Integration by Parts

The integral of a product can be rewritten using the product rule in reverse.
"""

OPTIMIZATION = b"""# Optimization

## Gradient Descent

Gradient descent minimises a loss function by stepping downhill.

## Momentum

Momentum accumulates velocity across steps and damps oscillation in narrow valleys.
"""


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(str(tmp_path))


@pytest.fixture
def gateway(settings: Settings) -> AIGateway:
    return AIGateway(MockProvider(dimensions=settings.noema_embedding_dim))


async def make_notebook(db: AsyncSession, user: User, title: str) -> Notebook:
    workspace = await OwnedRepository(db, Workspace, user.id).create(
        title=title, slug=f"w-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, user.id).create(
        workspace_id=workspace.id, title=title, slug=f"s-{uuid.uuid4().hex[:8]}"
    )
    return await OwnedRepository(db, Notebook, user.id).create(
        subject_id=subject.id,
        title=title,
        slug=f"n-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )


async def ingest(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    storage: LocalStorage,
    settings: Settings,
    data: bytes,
    *,
    gateway: AIGateway | None,
    filename: str = "notes.md",
) -> Source:
    source = await OwnedRepository(db, Source, user.id).create(
        notebook_id=notebook.id,
        kind=SourceKind.MD,
        original_filename=filename,
        byte_size=len(data),
        status=SourceStatus.PENDING,
        source_metadata={},
    )
    key = storage_key(user.id, source.id, "md")
    await storage.put(key, data)
    source.storage_key = key
    await db.flush()

    await ingest_source(
        db, source.id, storage=storage, gateway=gateway, settings=settings
    )
    return source


async def test_text_search_finds_a_chunk_by_its_words(
    db: AsyncSession, user: User, storage: LocalStorage, settings: Settings
) -> None:
    notebook = await make_notebook(db, user, "Optimization")
    await ingest(db, user, notebook, storage, settings, OPTIMIZATION, gateway=None)

    results = await retrieve(db, "momentum oscillation", owner_id=user.id)

    assert results, "the sparse half must work without any embeddings"
    assert "Momentum" in results[0].content


async def test_hybrid_retrieval_runs_both_halves(
    db: AsyncSession,
    user: User,
    storage: LocalStorage,
    settings: Settings,
    gateway: AIGateway,
) -> None:
    notebook = await make_notebook(db, user, "Optimization")
    await ingest(db, user, notebook, storage, settings, OPTIMIZATION, gateway=gateway)

    results = await retrieve(
        db,
        "gradient descent downhill",
        owner_id=user.id,
        gateway=gateway,
        settings=RetrievalSettings(min_score=0.0),
    )

    assert results
    assert any(r.found_by_both for r in results), (
        "with embeddings present, some chunk should be found by both retrievers"
    )


async def test_results_carry_everything_a_citation_needs(
    db: AsyncSession,
    user: User,
    storage: LocalStorage,
    settings: Settings,
    gateway: AIGateway,
) -> None:
    notebook = await make_notebook(db, user, "Optimization")
    await ingest(
        db,
        user,
        notebook,
        storage,
        settings,
        OPTIMIZATION,
        gateway=gateway,
        filename="boyd.md",
    )

    results = await retrieve(db, "momentum", owner_id=user.id, gateway=gateway)

    assert results
    hit = results[0]
    assert hit.heading_path[:1] == ["Optimization"]
    assert hit.source_title == "Optimization"  # the H1, preferred over the filename
    assert "Optimization" in hit.location


async def test_notebook_scoping_is_the_feature_not_a_filter(
    db: AsyncSession,
    user: User,
    storage: LocalStorage,
    settings: Settings,
    gateway: AIGateway,
) -> None:
    """'Explain this using my materials' must mean the ones in front of the user."""
    optimization = await make_notebook(db, user, "Optimization")
    calculus = await make_notebook(db, user, "Calculus")
    await ingest(db, user, optimization, storage, settings, OPTIMIZATION, gateway=gateway)
    await ingest(db, user, calculus, storage, settings, CALCULUS, gateway=gateway)

    scoped = await retrieve(
        db, "chain rule derivative", owner_id=user.id, notebook_id=optimization.id
    )
    assert scoped, "scoping must not empty the result set entirely"
    assert not any("composition" in r.content for r in scoped), (
        "a chunk from the other notebook leaked into a scoped search"
    )

    unscoped = await retrieve(db, "chain rule derivative", owner_id=user.id)
    assert any("composition" in r.content for r in unscoped)


async def test_another_users_material_is_never_retrieved(
    db: AsyncSession,
    user: User,
    other_user: User,
    storage: LocalStorage,
    settings: Settings,
    gateway: AIGateway,
) -> None:
    notebook = await make_notebook(db, user, "Optimization")
    await ingest(db, user, notebook, storage, settings, OPTIMIZATION, gateway=gateway)

    assert await retrieve(db, "gradient descent", owner_id=other_user.id) == []


async def test_a_question_the_material_does_not_answer_retrieves_nothing(
    db: AsyncSession,
    user: User,
    storage: LocalStorage,
    settings: Settings,
    gateway: AIGateway,
) -> None:
    """This empty list is what makes 'I could not find this' honest rather than a
    fallback phrase."""
    notebook = await make_notebook(db, user, "Optimization")
    await ingest(db, user, notebook, storage, settings, OPTIMIZATION, gateway=None)

    results = await retrieve(db, "photosynthesis chlorophyll thylakoid", owner_id=user.id)

    assert results == []


async def test_the_dense_floor_is_what_makes_a_refusal_possible(
    db: AsyncSession,
    user: User,
    storage: LocalStorage,
    settings: Settings,
    gateway: AIGateway,
) -> None:
    """Vector search always returns its nearest neighbours, however far away they
    are, and RRF fuses on rank — so without an absolute similarity floor there is no
    such thing as "nothing relevant here"."""
    notebook = await make_notebook(db, user, "Optimization")
    await ingest(db, user, notebook, storage, settings, OPTIMIZATION, gateway=gateway)

    question = "thylakoid chlorophyll photosynthesis"

    with_floor = await retrieve(db, question, owner_id=user.id, gateway=gateway)
    assert with_floor == []

    without_floor = await retrieve(
        db,
        question,
        owner_id=user.id,
        gateway=gateway,
        settings=RetrievalSettings(min_similarity=0.0, min_score=0.0),
    )
    assert without_floor, "the floor, not the query, is what produced the empty result"


async def test_an_empty_query_retrieves_nothing(
    db: AsyncSession, user: User, gateway: AIGateway
) -> None:
    assert await retrieve(db, "   ", owner_id=user.id, gateway=gateway) == []


async def test_the_score_threshold_filters_weak_matches(
    db: AsyncSession, user: User, storage: LocalStorage, settings: Settings
) -> None:
    notebook = await make_notebook(db, user, "Optimization")
    await ingest(db, user, notebook, storage, settings, OPTIMIZATION, gateway=None)

    permissive = await retrieve(
        db, "momentum", owner_id=user.id, settings=RetrievalSettings(min_score=0.0)
    )
    strict = await retrieve(
        db, "momentum", owner_id=user.id, settings=RetrievalSettings(min_score=1.0)
    )

    assert permissive
    assert strict == [], "nothing can score a perfect 1.0 from one retriever alone"
