"""Feynman mode.

The properties worth pinning: a missing model is not a bad grade, the evaluation
is judged against the learner's own material, the explanation is kept verbatim,
and it actually moves mastery — an explanation that changes nothing is a text box.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import ProviderUnavailable
from noema.db.models import Concept, ConceptMastery, Explanation, User, Workspace
from noema.db.repository import OwnedRepository
from noema.providers.base import StructuredRequest
from noema.study.feynman import evaluate_explanation

pytestmark = pytest.mark.asyncio


class Judge:
    """A grader that records what it was shown and returns a fixed verdict."""

    def __init__(self, score: float = 0.8) -> None:
        self.score = score
        self.seen: list[str] = []

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        self.seen.append(request.messages[-1].content)
        return {
            "score": self.score,
            "gaps": ["you never say why the diastole matters", ""],
            "oversimplifications": [],
            "assumed": ["cardiac output"],
            "contradictions": [],
            "next_step": "Say what perfusion depends on.",
        }


async def concept_for(db: AsyncSession, owner: User, definition: str) -> Concept:
    workspace = await OwnedRepository(db, Workspace, owner.id).create(
        title="Medicine", slug=f"med-{uuid.uuid4().hex[:8]}"
    )
    return await OwnedRepository(db, Concept, owner.id).create(
        workspace_id=workspace.id,
        name="Diastole",
        normalized_name="diastole",
        definition=definition,
    )


async def test_no_model_is_not_a_bad_grade(db: AsyncSession, user: User) -> None:
    """A missing grader is our problem, not evidence about the learner."""
    concept = await concept_for(db, user, "The filling phase.")

    with pytest.raises(ProviderUnavailable):
        await evaluate_explanation(
            db, concept.id, "Diastole is when the heart fills.", owner_id=user.id
        )

    stored = (await db.scalars(select(Explanation))).all()
    assert stored == [], "a zero was recorded for a grader that never ran"


async def test_it_is_judged_against_the_learners_material(
    db: AsyncSession, user: User
) -> None:
    """Otherwise the model marks people down for not matching a book it invented."""
    concept = await concept_for(db, user, "Diastole is two thirds of the cycle at rest.")
    judge = Judge()

    await evaluate_explanation(
        db,
        concept.id,
        "The heart relaxes and fills.",
        owner_id=user.id,
        gateway=judge,  # type: ignore[arg-type]
    )

    prompt = judge.seen[0]
    assert "two thirds of the cycle" in prompt, "the source material was not sent"
    assert "The heart relaxes and fills." in prompt


async def test_the_explanation_is_kept_and_cleaned(db: AsyncSession, user: User) -> None:
    """Verbatim text, and no empty findings reaching the screen."""
    concept = await concept_for(db, user, "The filling phase.")

    explanation = await evaluate_explanation(
        db,
        concept.id,
        "  The heart relaxes and fills.  ",
        owner_id=user.id,
        gateway=Judge(),  # type: ignore[arg-type]
    )

    assert explanation.text == "The heart relaxes and fills."
    assert explanation.findings["gaps"] == ["you never say why the diastole matters"], (
        "an empty string from the model was stored as a finding"
    )
    assert explanation.findings["next_step"]


async def test_explaining_moves_mastery(db: AsyncSession, user: User) -> None:
    """An explanation that changes nothing is just a text box."""
    concept = await concept_for(db, user, "The filling phase.")

    await evaluate_explanation(
        db,
        concept.id,
        "Diastole is the filling phase, and it is when the coronaries are perfused.",
        owner_id=user.id,
        gateway=Judge(score=0.9),  # type: ignore[arg-type]
    )

    row = await db.scalar(
        select(ConceptMastery).where(ConceptMastery.concept_id == concept.id)
    )
    assert row is not None, "explaining produced no mastery row"
    assert row.mastery > 0, "the explanation counted for nothing"
    assert row.components["effective_observations"] > 0
