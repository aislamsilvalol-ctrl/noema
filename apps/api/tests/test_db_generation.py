"""Generating and storing cards from a notebook's chunks, against a real database.

``parse_cards`` is covered as a pure function in ``test_generation.py``. What's
tested here is the wiring around it: chunks are batched and turned into a real
gateway call, a failed batch does not abort the rest, and storage dedupes against
what's already in the notebook and links to concepts that already exist — none of
which a mocked gateway or an in-memory list could prove.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import (
    Card,
    CardOrigin,
    Chunk,
    Concept,
    ConceptStatus,
    Notebook,
    Source,
    SourceKind,
    SourceStatus,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.providers.base import (
    Capabilities,
    ChatRequest,
    ChatResponse,
    EmbedRequest,
    EmbedResponse,
    HealthReport,
    ProviderError,
    StructuredRequest,
)
from noema.providers.gateway import AIGateway
from noema.study.generation import BATCH_SIZE, generate_cards

pytestmark = pytest.mark.asyncio


class FakeProvider:
    """An ``AIProvider`` whose ``structured()`` responses are scripted per call.

    Not ``MockProvider``: its schema-skeleton response gives every card an
    identical front and back, which ``parse_cards`` itself discards as a
    self-testing card — useless for proving what storage does with real cards.
    """

    name = "fake"
    capabilities = Capabilities(structured_output="native")

    def __init__(self, responses: list[dict[str, Any] | Exception]) -> None:
        self._queue = list(responses)
        self.calls = 0

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        self.calls += 1
        response = self._queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def chat(self, request: ChatRequest) -> ChatResponse:
        raise NotImplementedError

    def stream(self, request: ChatRequest) -> Any:
        raise NotImplementedError

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        raise NotImplementedError

    async def health(self) -> HealthReport:
        raise NotImplementedError


def cards_payload(*pairs: tuple[str, str], concept: str = "") -> dict[str, Any]:
    return {
        "cards": [
            {"front": front, "back": back, "type": "basic", "concept": concept}
            for front, back in pairs
        ]
    }


@pytest.fixture
async def notebook(db: AsyncSession, user: User) -> Notebook:
    workspace = await OwnedRepository(db, Workspace, user.id).create(
        title="Bio", slug=f"bio-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, user.id).create(
        workspace_id=workspace.id, title="Cells", slug=f"cells-{uuid.uuid4().hex[:8]}"
    )
    return await OwnedRepository(db, Notebook, user.id).create(
        subject_id=subject.id,
        title="Organelles",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )


async def make_chunks(
    db: AsyncSession, user: User, notebook: Notebook, count: int
) -> list[Chunk]:
    source = await OwnedRepository(db, Source, user.id).create(
        notebook_id=notebook.id,
        kind=SourceKind.MD,
        original_filename="notes.md",
        byte_size=0,
        status=SourceStatus.READY,
    )
    chunks = []
    for i in range(count):
        chunk = await OwnedRepository(db, Chunk, user.id).create(
            source_id=source.id,
            notebook_id=notebook.id,
            ordinal=i,
            content=f"Passage {i} about organelles.",
            token_count=5,
            heading_path=[],
        )
        chunks.append(chunk)
    await db.flush()
    return chunks


async def test_a_notebook_with_no_chunks_produces_no_cards(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    provider = FakeProvider([ProviderError("should not be called", provider="fake")])
    gateway = AIGateway(provider)

    cards = await generate_cards(db, notebook.id, owner_id=user.id, gateway=gateway)

    assert cards == []
    assert provider.calls == 0


async def test_generated_cards_are_stored_unapproved_with_ai_origin(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    await make_chunks(db, user, notebook, 2)
    provider = FakeProvider(
        [cards_payload(("What is the mitochondria?", "The powerhouse of the cell."))]
    )
    gateway = AIGateway(provider)

    cards = await generate_cards(db, notebook.id, owner_id=user.id, gateway=gateway)

    assert len(cards) == 1
    assert cards[0].origin is CardOrigin.AI
    assert cards[0].approved_at is None
    assert cards[0].notebook_id == notebook.id
    assert cards[0].owner_id == user.id


async def test_a_provider_error_on_one_batch_does_not_abort_the_rest(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """Two batches worth of chunks; the first batch's call fails outright."""
    await make_chunks(db, user, notebook, BATCH_SIZE + 1)
    provider = FakeProvider(
        [
            ProviderError("rate limited", provider="fake", retryable=False),
            cards_payload(("Q from batch two", "A from batch two")),
        ]
    )
    gateway = AIGateway(provider)

    cards = await generate_cards(db, notebook.id, owner_id=user.id, gateway=gateway)

    assert provider.calls == 2
    assert len(cards) == 1
    assert cards[0].front_md == "Q from batch two"


async def test_a_card_matching_an_existing_front_is_not_stored_again(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    await make_chunks(db, user, notebook, 1)
    existing = Card(
        owner_id=user.id,
        notebook_id=notebook.id,
        front_md="What is the mitochondria?",
        back_md="Already here.",
        origin=CardOrigin.USER,
    )
    db.add(existing)
    await db.flush()

    provider = FakeProvider(
        [
            cards_payload(
                ("what is the MITOCHONDRIA?", "Duplicate, different casing."),
                ("What is the Golgi apparatus?", "Packages proteins."),
            )
        ]
    )
    gateway = AIGateway(provider)

    cards = await generate_cards(db, notebook.id, owner_id=user.id, gateway=gateway)

    assert len(cards) == 1
    assert cards[0].front_md == "What is the Golgi apparatus?"


async def test_a_card_is_linked_to_a_matching_concept(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    subject = await db.get(Subject, notebook.subject_id)
    assert subject is not None
    concept = Concept(
        owner_id=user.id,
        workspace_id=subject.workspace_id,
        name="Mitochondria",
        normalized_name="mitochondria",
        status=ConceptStatus.ACTIVE,
        difficulty_prior=0.5,
        aliases=[],
        source_chunk_ids=[],
    )
    db.add(concept)
    await db.flush()

    await make_chunks(db, user, notebook, 1)
    provider = FakeProvider(
        [
            cards_payload(
                ("What is the mitochondria?", "The powerhouse of the cell."),
                ("What is a ribosome?", "Synthesizes proteins."),
                concept="Mitochondria",
            )
        ]
    )
    gateway = AIGateway(provider)

    cards = await generate_cards(db, notebook.id, owner_id=user.id, gateway=gateway)

    by_front = {card.front_md: card for card in cards}
    assert by_front["What is the mitochondria?"].concept_id == concept.id
    assert by_front["What is a ribosome?"].concept_id is None


async def test_limit_caps_how_many_cards_are_stored(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    await make_chunks(db, user, notebook, 1)
    provider = FakeProvider(
        [
            cards_payload(
                ("Q1", "A1"),
                ("Q2", "A2"),
                ("Q3", "A3"),
            )
        ]
    )
    gateway = AIGateway(provider)

    cards = await generate_cards(
        db, notebook.id, owner_id=user.id, gateway=gateway, limit=2
    )

    assert len(cards) == 2
