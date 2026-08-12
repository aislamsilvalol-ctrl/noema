"""Generating questions and grading answers to them.

Where card generation drafts recall prompts, this drafts questions with a stated
difficulty — which is what lets the mastery model tell someone who finds a topic easy
from someone who is only ever asked easy things about it.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import NotFound
from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.db.models import (
    Answer,
    CardOrigin,
    Chunk,
    Concept,
    ConceptStatus,
    Difficulty,
    Grader,
    Mistake,
    Question,
    QuestionType,
)
from noema.knowledge.resolution import normalize_name
from noema.prompts import PROMPT_DIR, load
from noema.providers.base import (
    Message,
    ProviderError,
    Role,
    StructuredRequest,
    TaskClass,
)
from noema.providers.gateway import AIGateway
from noema.study.grading import Grade, grade_deterministic, is_gradeable_locally
from noema.study.mastery import recompute_for_review

log = get_logger(__name__)

__all__ = ["answer_question", "generate_questions", "parse_questions"]

BATCH_SIZE = 4
MAX_PROMPT = 1_000
MAX_QUESTIONS_PER_BATCH = 10

QUESTION_SCHEMA: dict[str, Any] = json.loads(
    (PROMPT_DIR / "generate.questions.schema.json").read_text(encoding="utf-8")
)
GRADE_SCHEMA: dict[str, Any] = json.loads(
    (PROMPT_DIR / "grade.open.schema.json").read_text(encoding="utf-8")
)

#: A wrong answer given with this much confidence is a misconception candidate, not
#: a slip. See docs/learning-engine.md §6.
MISCONCEPTION_CONFIDENCE = 4

GENERATABLE = {
    "mcq": QuestionType.MCQ,
    "true_false": QuestionType.TRUE_FALSE,
    "open": QuestionType.OPEN,
    "fill_blank": QuestionType.FILL_BLANK,
    "ordering": QuestionType.ORDERING,
}


@dataclass(frozen=True, slots=True)
class ParsedQuestion:
    type: QuestionType
    difficulty: Difficulty
    prompt: str
    concept_name: str
    payload: dict[str, Any] = field(default_factory=dict)
    rubric: dict[str, Any] | None = None


async def generate_questions(
    session: AsyncSession,
    notebook_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    gateway: AIGateway,
    limit: int = 10,
    model: str | None = None,
) -> list[Question]:
    chunks = (
        await session.execute(
            select(Chunk.id, Chunk.content)
            .where(Chunk.notebook_id == notebook_id, Chunk.owner_id == owner_id)
            .order_by(Chunk.ordinal)
            .limit(40)
        )
    ).all()
    if not chunks:
        return []

    prompt = load("generate.questions")
    parsed: list[tuple[ParsedQuestion, list[str]]] = []

    for start in range(0, len(chunks), BATCH_SIZE):
        if len(parsed) >= limit:
            break

        batch = chunks[start : start + BATCH_SIZE]
        passages = "\n\n".join(
            f"<passage>\n{content.strip()}\n</passage>" for _, content in batch
        )

        try:
            payload = await gateway.structured(
                StructuredRequest(
                    messages=[
                        Message(role=Role.SYSTEM, content=prompt.body),
                        Message(
                            role=Role.USER, content=f"<PASSAGES>\n{passages}\n</PASSAGES>"
                        ),
                    ],
                    json_schema=QUESTION_SCHEMA,
                    task=TaskClass.GENERATE_QUESTIONS,
                    model=model,
                )
            )
        except ProviderError as exc:
            log.warning("questions.batch_failed", offset=start, error=str(exc))
            continue

        chunk_ids = [str(cid) for cid, _ in batch]
        parsed.extend((q, chunk_ids) for q in parse_questions(payload))

    return await _store(session, parsed[:limit], notebook_id, owner_id)


def parse_questions(payload: dict[str, Any]) -> list[ParsedQuestion]:
    """Validate a generated batch, dropping anything unusable.

    A malformed MCQ is worse than a missing one: it would be graded against a
    correct index that does not exist, and the learner would be marked wrong for a
    right answer.
    """
    raw = payload.get("questions")
    if not isinstance(raw, list):
        return []

    questions: list[ParsedQuestion] = []
    for item in raw[:MAX_QUESTIONS_PER_BATCH]:
        if not isinstance(item, dict):
            continue

        kind = GENERATABLE.get(str(item.get("type")))
        prompt = str(item.get("prompt") or "").strip()[:MAX_PROMPT]
        if kind is None or not prompt:
            continue

        built = _payload_for(kind, item)
        if built is None:
            continue

        questions.append(
            ParsedQuestion(
                type=kind,
                difficulty=_difficulty(item.get("difficulty")),
                prompt=prompt,
                concept_name=str(item.get("concept") or "").strip()[:200],
                payload=built,
                rubric=_rubric(kind, item),
            )
        )

    return questions


def _payload_for(kind: QuestionType, item: dict[str, Any]) -> dict[str, Any] | None:
    explanation = str(item.get("explanation") or "").strip()[:1000]

    if kind is QuestionType.MCQ:
        options = [str(o).strip() for o in item.get("options", []) if str(o).strip()]
        index = item.get("correct_index")
        if (
            len(options) < 2
            or not isinstance(index, int)
            or not 0 <= index < len(options)
        ):
            return None
        return {"options": options, "correct_index": index, "explanation": explanation}

    if kind is QuestionType.TRUE_FALSE:
        if not isinstance(item.get("answer"), bool):
            return None
        return {"answer": item["answer"], "explanation": explanation}

    if kind is QuestionType.FILL_BLANK:
        accepted = [str(a).strip() for a in item.get("accepted", []) if str(a).strip()]
        return {"accepted": accepted} if accepted else None

    if kind is QuestionType.ORDERING:
        order = [str(o).strip() for o in item.get("order", []) if str(o).strip()]
        return {"order": order} if len(order) >= 2 else None

    return {"explanation": explanation}


def _rubric(kind: QuestionType, item: dict[str, Any]) -> dict[str, Any] | None:
    if kind is not QuestionType.OPEN:
        return None
    points = [str(p).strip() for p in item.get("rubric_points", []) if str(p).strip()]
    # An open question with no rubric cannot be graded on anything but vibes.
    return {"points": points} if points else None


def _difficulty(value: Any) -> Difficulty:
    try:
        return Difficulty(str(value))
    except ValueError:
        return Difficulty.MEDIUM


async def _store(
    session: AsyncSession,
    parsed: Sequence[tuple[ParsedQuestion, list[str]]],
    notebook_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> list[Question]:
    if not parsed:
        return []

    concepts = {
        concept.normalized_name: concept
        for concept in (
            await session.scalars(
                select(Concept).where(
                    Concept.owner_id == owner_id, Concept.status != ConceptStatus.MERGED
                )
            )
        ).all()
    }

    stored: list[Question] = []
    for question, chunk_ids in parsed:
        if question.type is QuestionType.OPEN and question.rubric is None:
            continue

        concept = concepts.get(normalize_name(question.concept_name))
        row = Question(
            owner_id=owner_id,
            notebook_id=notebook_id,
            concept_id=concept.id if concept else None,
            type=question.type,
            difficulty=question.difficulty,
            prompt=question.prompt,
            payload=question.payload,
            rubric=question.rubric,
            source_chunk_ids=[uuid.UUID(cid) for cid in chunk_ids],
            origin=CardOrigin.AI,
        )
        session.add(row)
        stored.append(row)

    await session.flush()
    log.info("questions.generated", notebook_id=str(notebook_id), count=len(stored))
    return stored


async def answer_question(
    session: AsyncSession,
    question_id: uuid.UUID,
    response: dict[str, Any],
    *,
    owner_id: uuid.UUID,
    gateway: AIGateway | None = None,
    confidence: int | None = None,
    elapsed_ms: int = 0,
    model: str | None = None,
    now: datetime | None = None,
) -> Answer:
    """Grade an answer, record it, and update what follows from it."""
    now = now or utcnow()

    question = await session.scalar(
        select(Question).where(
            Question.id == question_id,
            Question.owner_id == owner_id,
            Question.deleted_at.is_(None),
        )
    )
    if question is None:
        raise NotFound("Question not found")

    if is_gradeable_locally(question.type):
        grade = grade_deterministic(question.type, question.payload, response)
    else:
        grade = await _grade_semantically(question, response, gateway, model)

    answer = Answer(
        owner_id=owner_id,
        question_id=question.id,
        concept_id=question.concept_id,
        response=response,
        is_correct=grade.is_correct,
        score=grade.score,
        confidence=confidence,
        elapsed_ms=max(elapsed_ms, 0),
        grader=grade.grader,
        feedback=grade.feedback,
        answered_at=now,
    )
    session.add(answer)
    await session.flush()

    if grade.score < 0.5:
        await _record_mistake(session, question, answer, confidence, owner_id)

    if question.concept_id is not None:
        await recompute_for_review(
            session, question.concept_id, owner_id=owner_id, now=now
        )

    return answer


async def _grade_semantically(
    question: Question,
    response: dict[str, Any],
    gateway: AIGateway | None,
    model: str | None,
) -> Grade:
    """Grade an open answer against its rubric.

    Never by comparing strings: the question is whether the learner demonstrated the
    understanding, not whether they used the source's words.
    """
    text = str(response.get("text", "")).strip()
    if not text:
        return Grade(0.0, False, Grader.SELF, {"feedback": "No answer given."})

    if gateway is None:
        # Without a model there is no honest grade, so the learner self-assesses
        # rather than being told a number nobody computed.
        return Grade(
            score=0.0,
            is_correct=False,
            grader=Grader.SELF,
            feedback={"feedback": "No grading model is configured; grade yourself."},
        )

    points = (question.rubric or {}).get("points", [])
    prompt = load("grade.open")

    try:
        payload = await gateway.structured(
            StructuredRequest(
                messages=[
                    Message(role=Role.SYSTEM, content=prompt.body),
                    Message(
                        role=Role.USER,
                        content=(
                            f"<QUESTION>\n{question.prompt}\n</QUESTION>\n\n"
                            f"<RUBRIC>\n"
                            + "\n".join(f"- {p}" for p in points)
                            + "\n</RUBRIC>\n\n"
                            f"<ANSWER>\n{text}\n</ANSWER>"
                        ),
                    ),
                ],
                json_schema=GRADE_SCHEMA,
                task=TaskClass.GRADE_OPEN_ANSWER,
                model=model,
            )
        )
    except ProviderError as exc:
        log.warning("grading.failed", question_id=str(question.id), error=str(exc))
        return Grade(
            score=0.0,
            is_correct=False,
            grader=Grader.SELF,
            feedback={"feedback": f"Grading was unavailable: {exc}"},
        )

    score = min(max(float(payload.get("score", 0.0)), 0.0), 1.0)
    return Grade(
        score=score,
        # A pass here is 0.7, not 0.5: a half-right answer to an open question is a
        # gap, and marking it correct would tell the mastery model otherwise.
        is_correct=score >= 0.7,
        grader=Grader.AI,
        feedback={
            "missing": payload.get("missing", []),
            "errors": payload.get("errors", []),
            "feedback": str(payload.get("feedback", ""))[:1000],
        },
    )


async def _record_mistake(
    session: AsyncSession,
    question: Question,
    answer: Answer,
    confidence: int | None,
    owner_id: uuid.UUID,
) -> None:
    """Store a wrong answer, flagging the confident ones.

    A confident error is the failure mode spaced repetition never catches: the
    learner has a coherent wrong model and no reason to flag it for review.
    """
    is_misconception = confidence is not None and confidence >= MISCONCEPTION_CONFIDENCE

    session.add(
        Mistake(
            owner_id=owner_id,
            question_id=question.id,
            answer_id=answer.id,
            concept_id=question.concept_id,
            confidence=confidence,
            is_misconception=is_misconception,
            summary=None,
        )
    )
    await session.flush()

    if is_misconception:
        log.info(
            "mistake.misconception_flagged",
            question_id=str(question.id),
            concept_id=str(question.concept_id) if question.concept_id else None,
        )
