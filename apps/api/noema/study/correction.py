"""Correcting a misconception, rather than repeating the question that caught it.

Rescheduling the question someone got wrong asks them the same thing again. If they
hold a coherent wrong model, they will answer it the same way, and eventually learn
the answer to that one question without the model ever changing.

So this names the belief their answer implies, and writes questions where the wrong
model and the right one disagree. A question both models answer identically cannot
tell anyone which one is in use — including us.

Resolution takes two correct, confident answers on different days. One lucky
correction proves nothing, and two in the same sitting prove only that the last five
minutes stuck.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import NotFound
from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.db.models import (
    Answer,
    Concept,
    Difficulty,
    Mistake,
    Question,
    QuestionType,
)
from noema.prompts import PROMPT_DIR, load
from noema.providers.base import (
    Message,
    ProviderError,
    Role,
    StructuredRequest,
    TaskClass,
)
from noema.providers.gateway import AIGateway
from noema.study.feynman import source_context

log = get_logger(__name__)

__all__ = ["CONFIDENT", "REQUIRED_CORRECTIONS", "build_drills", "resolve_if_earned"]

#: Two correct answers, on different days.
REQUIRED_CORRECTIONS = 2
#: What counts as answering confidently — the same bar that flags a misconception
#: in the first place, so resolving one requires the state that created it.
CONFIDENT = 4
#: The gap that makes the second correction evidence of memory rather than of the
#: first correction still being in the room.
SPACING = timedelta(hours=20)

MAX_DRILLS = 3

SCHEMA: dict[str, Any] = json.loads(
    (PROMPT_DIR / "correct.misconception.schema.json").read_text(encoding="utf-8")
)


@dataclass(frozen=True, slots=True)
class Drills:
    belief: str
    questions: list[Question]


async def build_drills(
    session: AsyncSession,
    mistake_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    gateway: AIGateway | None = None,
    model: str | None = None,
) -> Drills:
    """Name the belief and write questions that break it."""
    mistake = await session.scalar(
        select(Mistake).where(Mistake.id == mistake_id, Mistake.owner_id == owner_id)
    )
    if mistake is None:
        raise NotFound("Mistake not found")

    original = await session.scalar(
        select(Question).where(Question.id == mistake.question_id)
    )
    answer = await session.scalar(select(Answer).where(Answer.id == mistake.answer_id))
    if original is None or answer is None:
        raise NotFound("The question behind this mistake is gone")

    if gateway is None:
        # Without a model there is nothing to write. Saying so beats returning an
        # empty list that looks like "no drills were needed".
        raise NotFound(
            "No model is configured, so correction questions cannot be written"
        )

    concept = (
        await session.scalar(select(Concept).where(Concept.id == mistake.concept_id))
        if mistake.concept_id
        else None
    )
    context = await source_context(session, concept, owner_id) if concept else ""

    payload = await _write(original, answer, concept, context, gateway, model)
    belief = str(payload.get("belief", "")).strip()

    questions = [
        stored
        for stored in (
            _build(item, original, mistake, owner_id)
            for item in payload.get("questions", [])[:MAX_DRILLS]
            if isinstance(item, dict)
        )
        if stored is not None
    ]
    for question in questions:
        session.add(question)

    # Kept on the mistake so the learner is told what they appear to believe, not
    # merely that they were wrong.
    mistake.summary = belief or mistake.summary
    await session.flush()

    log.info(
        "misconception.drills_written",
        mistake_id=str(mistake_id),
        count=len(questions),
    )
    return Drills(belief=belief, questions=questions)


async def resolve_if_earned(
    session: AsyncSession,
    concept_id: uuid.UUID | None,
    *,
    owner_id: uuid.UUID,
    now: datetime | None = None,
) -> int:
    """Close misconceptions the learner has demonstrably stopped holding.

    Two correct answers at confidence >= 4, at least a day apart. One correct
    answer is a coin landing the right way; two in the same session is the last
    explanation still echoing.
    """
    if concept_id is None:
        return 0
    now = now or utcnow()

    open_mistakes = (
        await session.scalars(
            select(Mistake).where(
                Mistake.owner_id == owner_id,
                Mistake.concept_id == concept_id,
                Mistake.resolved_at.is_(None),
                Mistake.is_misconception.is_(True),
            )
        )
    ).all()
    if not open_mistakes:
        return 0

    resolved = 0
    for mistake in open_mistakes:
        moments = (
            await session.scalars(
                select(Answer.answered_at)
                .where(
                    Answer.owner_id == owner_id,
                    Answer.concept_id == concept_id,
                    Answer.is_correct.is_(True),
                    Answer.confidence >= CONFIDENT,
                    # Only what came after the mistake: answers from before it say
                    # nothing about whether the belief has changed.
                    Answer.answered_at > mistake.created_at,
                )
                .order_by(Answer.answered_at)
            )
        ).all()

        if _spaced_enough(list(moments)):
            mistake.resolved_at = now
            resolved += 1

    if resolved:
        await session.flush()
        log.info("misconception.resolved", concept_id=str(concept_id), count=resolved)
    return resolved


def _spaced_enough(moments: list[datetime]) -> bool:
    """Whether these corrections are far enough apart to mean anything."""
    if len(moments) < REQUIRED_CORRECTIONS:
        return False

    first = moments[0]
    return any(later - first >= SPACING for later in moments[1:])


def _build(
    item: dict[str, Any],
    original: Question,
    mistake: Mistake,
    owner_id: uuid.UUID,
) -> Question | None:
    """One generated drill, or nothing if it cannot be graded."""
    kind = str(item.get("type", ""))
    prompt = str(item.get("prompt", "")).strip()
    if not prompt:
        return None

    payload: dict[str, Any] = {
        "explanation": str(item.get("explanation", "")).strip(),
        # Kept so a human reviewing the deck can see the question's whole reason
        # for existing.
        "discriminates": str(item.get("discriminates", "")).strip(),
    }

    if kind == "mcq":
        options = [str(o) for o in item.get("options", []) if str(o).strip()]
        index = item.get("correct_index")
        if (
            len(options) < 2
            or not isinstance(index, int)
            or not 0 <= index < len(options)
        ):
            return None
        payload |= {"options": options, "correct_index": index}
        question_type = QuestionType.MCQ
    elif kind == "true_false":
        if not isinstance(item.get("answer"), bool):
            return None
        payload |= {"answer": bool(item["answer"])}
        question_type = QuestionType.TRUE_FALSE
    else:
        return None

    return Question(
        owner_id=owner_id,
        notebook_id=original.notebook_id,
        concept_id=mistake.concept_id,
        type=question_type,
        # Harder than the question that caught them: a discriminating case is
        # meant to be uncomfortable for the wrong model.
        difficulty=Difficulty.HARD,
        prompt=prompt,
        payload=payload,
        rubric={},
        source_chunk_ids=list(original.source_chunk_ids or []),
    )


async def _write(
    original: Question,
    answer: Answer,
    concept: Concept | None,
    context: str,
    gateway: AIGateway,
    model: str | None,
) -> dict[str, Any]:
    prompt = load("correct.misconception")
    given = json.dumps(answer.response, ensure_ascii=False)
    correct = json.dumps(original.payload, ensure_ascii=False)

    try:
        return await gateway.structured(
            StructuredRequest(
                messages=[
                    Message(role=Role.SYSTEM, content=prompt.body),
                    Message(
                        role=Role.USER,
                        content=(
                            f"<CONCEPT>\n{concept.name if concept else 'unknown'}\n"
                            "</CONCEPT>\n\n"
                            f"<SOURCE>\n{context or 'No source material available.'}\n"
                            "</SOURCE>\n\n"
                            f"<QUESTION>\n{original.prompt}\n</QUESTION>\n\n"
                            f"<CORRECT>\n{correct}\n"
                            "</CORRECT>\n\n"
                            f"<THEIR_ANSWER>\n{given}\n</THEIR_ANSWER>"
                        ),
                    ),
                ],
                json_schema=SCHEMA,
                task=TaskClass.GENERATE_QUESTIONS,
                model=model,
            )
        )
    except ProviderError as exc:
        log.warning("misconception.drills_failed", error=str(exc))
        return {"belief": "", "questions": []}
