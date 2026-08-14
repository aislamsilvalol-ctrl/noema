"""The retrieval eval, run as a test with thresholds.

This is the guard the project did not have. Unit tests prove the citation filter
drops an uncited sentence; none of them could tell you whether the chunk that
answers the question was found at all, or whether a question the corpus cannot
answer quietly got the nearest paragraph instead.

The thresholds are deliberately below what the corpus currently scores. They are
a floor to catch regressions, not a target to tune against — a threshold set at
today's exact number turns every unrelated change into a red build.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import User
from noema.evals import run
from noema.providers.gateway import AIGateway
from noema.providers.mock import MockProvider

pytestmark = pytest.mark.asyncio

#: A missed answerable query is a real failure; one in five is where this stops
#: being a search engine.
MIN_RECALL = 0.8

#: The one that decays silently. Loosening a floor to fix a missed match turns
#: refusals into nearest-paragraph guesses, and nothing else in the suite notices.
MIN_REFUSAL = 0.8


async def test_retrieval_finds_the_chunk_that_answers_the_question(
    db: AsyncSession, user: User
) -> None:
    report = await run(db, owner_id=user.id, gateway=AIGateway(MockProvider()))

    assert report.recall_at_k >= MIN_RECALL, (
        f"{report.summary()} — missed: {report.missed}"
    )


async def test_a_question_the_corpus_cannot_answer_is_refused(
    db: AsyncSession, user: User
) -> None:
    """ "Not in your materials" is a feature, and it is the first one to rot."""
    report = await run(db, owner_id=user.id, gateway=AIGateway(MockProvider()))

    assert report.refusal_rate >= MIN_REFUSAL, (
        f"{report.summary()} — answered anyway: {report.false_answers}"
    )


async def test_the_report_names_what_failed(db: AsyncSession, user: User) -> None:
    """A score with no list of failures cannot be acted on."""
    report = await run(db, owner_id=user.id, gateway=AIGateway(MockProvider()))

    assert report.answerable + report.unanswerable == 7
    assert "recall@k" in report.summary()
    # Whatever the numbers, the failures are enumerated rather than counted.
    assert isinstance(report.missed, list)
    assert isinstance(report.false_answers, list)
