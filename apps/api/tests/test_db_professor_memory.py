"""build_memory: selective mastery + open-misconception context for a notebook.

Mirrors ``test_db_session.py``'s own ``make_concept``/``make_card``/``make_question``
helpers rather than inventing a new fixture shape -- concepts are found the same way
this codebase already finds them elsewhere, through ``Card``/``Question``, since
``Concept`` itself carries no ``notebook_id``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.base import utcnow
from noema.db.models import (
    Answer,
    Card,
    CardOrigin,
    Concept,
    ConceptMastery,
    ConceptStatus,
    Difficulty,
    Grader,
    Mistake,
    Notebook,
    Question,
    QuestionType,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.services.professor_memory import (
    MAX_CONCEPTS,
    MAX_MISCONCEPTIONS,
    build_memory,
)

pytestmark = pytest.mark.asyncio


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


async def make_concept(
    db: AsyncSession, owner: User, notebook: Notebook, name: str
) -> Concept:
    subject = await db.get(Subject, notebook.subject_id)
    assert subject is not None
    concept = Concept(
        owner_id=owner.id,
        workspace_id=subject.workspace_id,
        name=name,
        normalized_name=name.lower(),
        status=ConceptStatus.ACTIVE,
        difficulty_prior=0.5,
        aliases=[],
        source_chunk_ids=[],
    )
    db.add(concept)
    await db.flush()
    return concept


async def make_card(
    db: AsyncSession, owner: User, notebook: Notebook, concept: Concept
) -> Card:
    card = Card(
        owner_id=owner.id,
        notebook_id=notebook.id,
        concept_id=concept.id,
        front_md="front",
        back_md="back",
        origin=CardOrigin.USER,
        source_chunk_ids=[],
    )
    db.add(card)
    await db.flush()
    return card


async def make_question(
    db: AsyncSession, owner: User, notebook: Notebook, concept: Concept
) -> Question:
    question = Question(
        owner_id=owner.id,
        notebook_id=notebook.id,
        concept_id=concept.id,
        type=QuestionType.MCQ,
        difficulty=Difficulty.MEDIUM,
        prompt="Which one?",
        payload={"correct_index": 1, "options": ["a", "b"]},
        source_chunk_ids=[],
    )
    db.add(question)
    await db.flush()
    return question


async def make_mastery(
    db: AsyncSession,
    owner: User,
    concept: Concept,
    *,
    mastery: float,
    last_evidence_at: datetime,
) -> None:
    db.add(
        ConceptMastery(
            owner_id=owner.id,
            concept_id=concept.id,
            mastery=mastery,
            evidence_count=3.0,
            last_evidence_at=last_evidence_at,
        )
    )
    await db.flush()


async def make_open_misconception(
    db: AsyncSession, owner: User, question: Question, concept: Concept, summary: str
) -> None:
    answer = Answer(
        owner_id=owner.id,
        question_id=question.id,
        concept_id=concept.id,
        response={},
        is_correct=False,
        grader=Grader.AI,
    )
    db.add(answer)
    await db.flush()
    db.add(
        Mistake(
            owner_id=owner.id,
            question_id=question.id,
            answer_id=answer.id,
            concept_id=concept.id,
            is_misconception=True,
            summary=summary,
            resolved_at=None,
        )
    )
    await db.flush()


async def test_a_notebook_with_no_concepts_yields_an_empty_snapshot(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    snapshot = await build_memory(db, owner_id=user.id, notebook_id=notebook.id)

    assert snapshot.is_empty
    assert snapshot.render() == ""


async def test_mastery_is_pulled_for_a_concept_touched_by_a_card(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Mitochondria")
    await make_card(db, user, notebook, concept)
    await make_mastery(db, user, concept, mastery=0.62, last_evidence_at=utcnow())

    snapshot = await build_memory(db, owner_id=user.id, notebook_id=notebook.id)

    assert len(snapshot.concepts) == 1
    assert snapshot.concepts[0].name == "Mitochondria"
    assert snapshot.concepts[0].mastery == 0.62
    assert "Mitochondria: 62% mastery" in snapshot.render()


async def test_mastery_is_pulled_for_a_concept_touched_only_by_a_question(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Ribosomes")
    await make_question(db, user, notebook, concept)
    await make_mastery(db, user, concept, mastery=0.3, last_evidence_at=utcnow())

    snapshot = await build_memory(db, owner_id=user.id, notebook_id=notebook.id)

    assert [c.name for c in snapshot.concepts] == ["Ribosomes"]


async def test_concepts_are_capped_and_ordered_by_most_recent_evidence(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    now = utcnow()
    for i in range(MAX_CONCEPTS + 2):
        concept = await make_concept(db, user, notebook, f"Concept {i}")
        await make_card(db, user, notebook, concept)
        # Concept 0 is the oldest evidence, the last index the most recent --
        # the cap should keep the most recent ones, not an arbitrary slice.
        await make_mastery(
            db, user, concept, mastery=0.5, last_evidence_at=now + timedelta(seconds=i)
        )

    snapshot = await build_memory(db, owner_id=user.id, notebook_id=notebook.id)

    assert len(snapshot.concepts) == MAX_CONCEPTS
    names = [c.name for c in snapshot.concepts]
    assert names == [f"Concept {i}" for i in range(MAX_CONCEPTS + 1, 1, -1)]


async def test_an_open_misconception_is_included(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Osmosis")
    question = await make_question(db, user, notebook, concept)
    await make_open_misconception(
        db, user, question, concept, "believes water always flows toward salt"
    )

    snapshot = await build_memory(db, owner_id=user.id, notebook_id=notebook.id)

    assert snapshot.misconceptions == ("believes water always flows toward salt",)
    assert "believes water always flows toward salt" in snapshot.render()


async def test_a_resolved_misconception_is_excluded(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Osmosis")
    question = await make_question(db, user, notebook, concept)
    await make_open_misconception(db, user, question, concept, "a resolved belief")
    mistake = (await db.execute(select(Mistake))).scalar_one()
    mistake.resolved_at = utcnow()
    await db.flush()

    snapshot = await build_memory(db, owner_id=user.id, notebook_id=notebook.id)

    assert snapshot.misconceptions == ()


async def test_misconceptions_are_capped(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Osmosis")
    for i in range(MAX_MISCONCEPTIONS + 2):
        question = await make_question(db, user, notebook, concept)
        await make_open_misconception(db, user, question, concept, f"belief {i}")

    snapshot = await build_memory(db, owner_id=user.id, notebook_id=notebook.id)

    assert len(snapshot.misconceptions) == MAX_MISCONCEPTIONS


async def test_another_users_mastery_never_leaks_through_a_shared_concept_id(
    db: AsyncSession, user: User, other_user: User, notebook: Notebook
) -> None:
    """The realistic guard (a notebook's owner_id) is checked by the caller
    (``professor_chat``'s own ``OwnedRepository(...).get(...)`` before this
    function is ever reached), not by ``build_memory`` itself -- so this
    isolates ``build_memory``'s *own* query correctness by giving ``other_user``
    legitimate access to their own notebook whose card happens to reference the
    same ``concept.id`` as ``user``'s mastery row. That specific id-sharing can't
    arise through the real app (``Concept`` is itself owner-scoped, so two
    users never see the same row), but constructing it directly proves the
    ``ConceptMastery``/``Mistake`` queries' own ``owner_id`` filters are what
    keeps this safe -- exactly the class of bug (a scoped-looking query missing
    its owner filter) this session found repeatedly elsewhere.
    """
    concept = await make_concept(db, user, notebook, "Photosynthesis")
    await make_mastery(db, user, concept, mastery=0.8, last_evidence_at=utcnow())

    other_workspace = await OwnedRepository(db, Workspace, other_user.id).create(
        title="Other", slug=f"other-{uuid.uuid4().hex[:8]}"
    )
    other_subject = await OwnedRepository(db, Subject, other_user.id).create(
        workspace_id=other_workspace.id, title="Other", slug=f"os-{uuid.uuid4().hex[:8]}"
    )
    other_notebook = await OwnedRepository(db, Notebook, other_user.id).create(
        subject_id=other_subject.id,
        title="Other",
        slug=f"on-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )
    db.add(
        Card(
            owner_id=other_user.id,
            notebook_id=other_notebook.id,
            concept_id=concept.id,
            front_md="front",
            back_md="back",
            origin=CardOrigin.USER,
            source_chunk_ids=[],
        )
    )
    await db.flush()

    snapshot = await build_memory(
        db, owner_id=other_user.id, notebook_id=other_notebook.id
    )

    assert snapshot.is_empty
