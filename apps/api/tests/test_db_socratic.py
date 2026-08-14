"""Socratic mode.

What makes it an evaluation rather than a themed chat: it ends, it records what
the learner reached, and the record is of their reasoning rather than ours.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import (
    Concept,
    ConceptMastery,
    Explanation,
    ExplanationKind,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.providers.base import StructuredRequest
from noema.study.socratic import MAX_EXCHANGES, next_turn

pytestmark = pytest.mark.asyncio


class Tutor:
    def __init__(self, reached: bool, question: str = "And why is that?") -> None:
        self.reached = reached
        self.question = question

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        return {
            "question": "" if self.reached else self.question,
            "reached": self.reached,
            "score": 0.7,
            "assessment": "You got to the perfusion argument yourself.",
        }


async def concept_for(db: AsyncSession, owner: User) -> Concept:
    workspace = await OwnedRepository(db, Workspace, owner.id).create(
        title="Medicine", slug=f"med-{uuid.uuid4().hex[:8]}"
    )
    return await OwnedRepository(db, Concept, owner.id).create(
        workspace_id=workspace.id,
        name="Diastole",
        normalized_name="diastole",
        definition="The filling phase, when the coronaries are perfused.",
    )


async def test_an_unfinished_dialogue_records_nothing(
    db: AsyncSession, user: User
) -> None:
    """Mid-conversation there is no verdict to store, only a next question."""
    concept = await concept_for(db, user)

    turn = await next_turn(
        db,
        concept.id,
        [{"role": "learner", "content": "It is when the heart relaxes."}],
        owner_id=user.id,
        gateway=Tutor(reached=False),  # type: ignore[arg-type]
    )

    assert turn.question and turn.explanation_id is None
    assert (await db.scalars(select(Explanation))).all() == []


async def test_reaching_it_records_the_learners_words_only(
    db: AsyncSession, user: User
) -> None:
    """The record is of their reasoning; keeping our questions would flatter it."""
    concept = await concept_for(db, user)
    transcript = [
        {"role": "tutor", "content": "When are the coronaries perfused?"},
        {"role": "learner", "content": "During diastole, because the muscle relaxes."},
    ]

    turn = await next_turn(
        db,
        concept.id,
        transcript,
        owner_id=user.id,
        gateway=Tutor(reached=True),  # type: ignore[arg-type]
    )

    assert turn.explanation_id is not None
    stored = await db.scalar(select(Explanation))
    assert stored is not None
    assert stored.kind is ExplanationKind.SOCRATIC
    assert stored.text == "During diastole, because the muscle relaxes."
    assert "When are the coronaries perfused?" not in stored.text
    # The dialogue is kept whole, separately from what is scored.
    assert len(stored.transcript) == 2


async def test_it_ends_rather_than_questioning_forever(
    db: AsyncSession, user: User
) -> None:
    """A session that never concludes records nothing at all.

    The learner who ran out of road still earned the credit for what they showed.
    """
    concept = await concept_for(db, user)
    transcript = [
        {"role": "learner", "content": f"attempt {i}"} for i in range(MAX_EXCHANGES)
    ]

    turn = await next_turn(
        db,
        concept.id,
        transcript,
        owner_id=user.id,
        gateway=Tutor(reached=False),  # type: ignore[arg-type]
    )

    assert turn.explanation_id is not None, "the dialogue was abandoned unrecorded"
    assert turn.exhausted is True
    assert turn.reached is False


async def test_being_questioned_counts_for_less_than_explaining_cold(
    db: AsyncSession, user: User
) -> None:
    """Real understanding, with a hand on your elbow.

    Same score through both routes must not produce the same evidence weight, or
    the cheaper route quietly becomes the better one.
    """
    from noema.study.mastery import EXPLANATION_DIFFICULTY

    assert (
        EXPLANATION_DIFFICULTY[ExplanationKind.SOCRATIC]
        < EXPLANATION_DIFFICULTY[ExplanationKind.FEYNMAN]
    )

    concept = await concept_for(db, user)
    await next_turn(
        db,
        concept.id,
        [{"role": "learner", "content": "Because the muscle relaxes."}],
        owner_id=user.id,
        gateway=Tutor(reached=True),  # type: ignore[arg-type]
    )

    row = await db.scalar(
        select(ConceptMastery).where(ConceptMastery.concept_id == concept.id)
    )
    assert row is not None and row.mastery > 0
