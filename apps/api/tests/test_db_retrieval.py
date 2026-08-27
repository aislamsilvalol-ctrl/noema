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

CONVERGENCE = b"""# Convergence

The sequence converges when the step size is small enough.
"""

MOLECULAR_BIOLOGY = b"""# Molecular Biology

## Amplification

PCR amplifies a target DNA sequence exponentially. Each PCR cycle doubles the
amount of DNA present, so thirty cycles of PCR yield roughly a billion copies.
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


#: The mock embedder is a hashed bag of words: semantically ordered, but with much
#: smaller magnitudes than a trained model, where related passages sit around 0.7.
#: Tests that need the dense half to fire say so rather than pretending the
#: production default is calibrated for a toy embedder.
MOCK_DENSE = RetrievalSettings(min_similarity=0.02, min_score=0.0)


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
        settings=MOCK_DENSE,
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

    results = await retrieve(
        db, "momentum", owner_id=user.id, gateway=gateway, settings=MOCK_DENSE
    )

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

    question = "chain rule derivative"

    # The material exists, and an unscoped search finds it.
    unscoped = await retrieve(db, question, owner_id=user.id)
    assert any("composition" in r.content for r in unscoped)

    # Scoped to the notebook that holds it, it is still found.
    in_calculus = await retrieve(db, question, owner_id=user.id, notebook_id=calculus.id)
    assert any("composition" in r.content for r in in_calculus)

    # Scoped to a notebook that does not, the honest answer is nothing — not the
    # nearest paragraph from somewhere else.
    in_optimization = await retrieve(
        db, question, owner_id=user.id, notebook_id=optimization.id
    )
    assert in_optimization == []


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


async def test_prefix_matching_finds_an_inflected_word(
    db: AsyncSession, user: User, storage: LocalStorage, settings: Settings
) -> None:
    """The 'simple' configuration does no stemming, so 'converge' would otherwise
    miss 'converges' — and a natural question would match nothing at all."""
    notebook = await make_notebook(db, user, "Optimization")
    await ingest(db, user, notebook, storage, settings, CONVERGENCE, gateway=None)

    assert await retrieve(db, "when does it converge", owner_id=user.id)


async def test_a_short_acronym_is_still_searchable(
    db: AsyncSession, user: User, storage: LocalStorage, settings: Settings
) -> None:
    """A 3-letter term like "PCR" must not be dropped like a filler word —
    academic material is full of exact terms shorter than the 4-letter prefix
    threshold, and the whole point of the sparse half is to catch them."""
    notebook = await make_notebook(db, user, "Molecular Biology")
    await ingest(db, user, notebook, storage, settings, MOLECULAR_BIOLOGY, gateway=None)

    results = await retrieve(db, "how does PCR work", owner_id=user.id)

    assert results, "a 3-letter acronym must not be dropped like a function word"
    assert "PCR" in results[0].content


async def test_a_question_matches_without_containing_every_word(
    db: AsyncSession, user: User, storage: LocalStorage, settings: Settings
) -> None:
    """Terms are ORed and ranked, not ANDed: requiring every word of a question to
    appear in one chunk matches essentially nothing."""
    notebook = await make_notebook(db, user, "Optimization")
    await ingest(db, user, notebook, storage, settings, OPTIMIZATION, gateway=None)

    results = await retrieve(
        db, "how exactly does gradient descent behave", owner_id=user.id
    )

    assert results
    assert "Gradient descent" in results[0].content


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
