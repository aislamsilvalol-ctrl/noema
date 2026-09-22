"""Keeping a question's observed difficulty current from the answers log.

The maths is in ``noema.engines.difficulty``; this module only counts the rows
and stores the result. It is recomputed from scratch rather than incremented,
so a re-run over history gives the same number as the live path did.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import Answer, Question
from noema.engines.difficulty import smoothed_difficulty
from noema.study.grading import difficulty_weight

__all__ = ["recompute_observed_difficulty"]


async def recompute_observed_difficulty(
    session: AsyncSession, question: Question
) -> None:
    """Recount this one question's answers and store what they say.

    One count query per call, so it is cheap enough to run every time an answer
    is recorded. The prior is the declared difficulty's weight: until the data
    outweighs the author, the observed number stays close to what was declared.
    """
    total, wrong = (
        await session.execute(
            select(
                func.count(Answer.id),
                func.count(Answer.id).filter(Answer.is_correct.is_(False)),
            ).where(Answer.question_id == question.id)
        )
    ).one()

    question.observed_count = int(total)
    question.observed_difficulty = smoothed_difficulty(
        int(wrong), int(total), prior=difficulty_weight(question.difficulty)
    )
    await session.flush()
