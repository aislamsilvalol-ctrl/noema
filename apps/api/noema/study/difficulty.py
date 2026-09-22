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

    "Wrong" here is ``not is_correct``, which deliberately ignores the partial
    credit stored alongside it in ``answers.score``. This is the classical
    reading of item difficulty — the share of learners who failed it — and it is
    the one the smoothing and the threshold were chosen for. Using the mean
    score instead would be a different and arguably better estimator, but it is
    a different estimator, not a refinement: an item where everyone scores 0.5
    is not the same item as one half the learners fail outright, and the two
    readings would need their own prior and their own bar. Worth measuring
    against each other once there is enough history to tell them apart.
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
