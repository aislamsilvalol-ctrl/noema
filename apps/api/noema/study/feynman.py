"""Feynman mode: explain it, and find out what you were missing.

Explaining a concept unaided is the hardest retrieval a learner can do, and the
one that most reliably exposes the difference between recognising an idea and
holding it. So the explanation is evidence, weighted as a hard item, and kept
verbatim.

The evaluation is grounded in the learner's own material. A model judging an
explanation from its own knowledge will mark someone down for not saying what a
textbook it has never seen would say — and, worse, will confidently correct a
claim their source actually supports.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import NotFound, ProviderUnavailable
from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.db.models import Chunk, Concept, Explanation, Grader
from noema.prompts import PROMPT_DIR, load
from noema.providers.base import (
    Message,
    ProviderError,
    Role,
    StructuredRequest,
    TaskClass,
)
from noema.providers.gateway import AIGateway
from noema.study.mastery import recompute_for_review

log = get_logger(__name__)

__all__ = ["Evaluation", "evaluate_explanation"]

#: How much of the learner's material to put in front of the grader. Enough to
#: judge against, small enough that the explanation stays the subject.
CONTEXT_CHUNKS = 6

SCHEMA: dict[str, Any] = json.loads(
    (PROMPT_DIR / "explain.feynman.schema.json").read_text(encoding="utf-8")
)


@dataclass(frozen=True, slots=True)
class Evaluation:
    score: float
    gaps: list[str]
    oversimplifications: list[str]
    assumed: list[str]
    contradictions: list[str]
    next_step: str


async def evaluate_explanation(
    session: AsyncSession,
    concept_id: uuid.UUID,
    text: str,
    *,
    owner_id: uuid.UUID,
    gateway: AIGateway | None = None,
    model: str | None = None,
    now: datetime | None = None,
) -> Explanation:
    """Judge an explanation against the material, store it, and count it."""
    now = now or utcnow()
    text = text.strip()

    concept = await session.scalar(
        select(Concept).where(Concept.id == concept_id, Concept.owner_id == owner_id)
    )
    if concept is None:
        raise NotFound("Concept not found")

    if not text:
        raise ProviderUnavailable("There is nothing to evaluate yet.")
    if gateway is None:
        # Better to refuse than to store a zero the learner did not earn: a
        # missing model is our problem, not evidence about them.
        raise ProviderUnavailable(
            "No grading model is configured, so an explanation cannot be evaluated."
        )

    evaluation = await _judge(
        concept, text, await _context(session, concept, owner_id), gateway, model
    )

    explanation = Explanation(
        owner_id=owner_id,
        concept_id=concept_id,
        text=text,
        score=evaluation.score,
        grader=Grader.AI,
        findings={
            "gaps": evaluation.gaps,
            "oversimplifications": evaluation.oversimplifications,
            "assumed": evaluation.assumed,
            "contradictions": evaluation.contradictions,
            "next_step": evaluation.next_step,
        },
        explained_at=now,
    )
    session.add(explanation)
    await session.flush()

    await recompute_for_review(session, concept_id, owner_id=owner_id, now=now)
    return explanation


async def _context(session: AsyncSession, concept: Concept, owner_id: uuid.UUID) -> str:
    """The learner's own material about this concept.

    Chunks the concept was extracted from, plus its definition. Deliberately not a
    semantic search over everything: the question is whether the explanation
    matches what they read, and widening the net invites the grader to mark
    against material the learner never saw.
    """
    parts: list[str] = []
    if concept.definition:
        parts.append(concept.definition)

    chunk_ids = [uuid.UUID(str(c)) for c in (concept.source_chunk_ids or [])]
    if chunk_ids:
        rows = (
            await session.scalars(
                select(Chunk.content)
                .where(Chunk.owner_id == owner_id, Chunk.id.in_(chunk_ids))
                .limit(CONTEXT_CHUNKS)
            )
        ).all()
        parts.extend(rows)

    return "\n\n---\n\n".join(p for p in parts if p)


async def _judge(
    concept: Concept,
    text: str,
    context: str,
    gateway: AIGateway,
    model: str | None,
) -> Evaluation:
    prompt = load("explain.feynman")

    try:
        payload: dict[str, Any] = await gateway.structured(
            StructuredRequest(
                messages=[
                    Message(role=Role.SYSTEM, content=prompt.body),
                    Message(
                        role=Role.USER,
                        content=(
                            f"<CONCEPT>\n{concept.name}\n</CONCEPT>\n\n"
                            f"<SOURCE>\n{context or 'No source material available.'}\n"
                            "</SOURCE>\n\n"
                            f"<EXPLANATION>\n{text}\n</EXPLANATION>"
                        ),
                    ),
                ],
                json_schema=SCHEMA,
                task=TaskClass.GRADE_OPEN_ANSWER,
                model=model,
            )
        )
    except ProviderError as exc:
        log.warning("feynman.failed", concept_id=str(concept.id), error=str(exc))
        raise ProviderUnavailable(
            f"The explanation could not be evaluated: {exc}"
        ) from exc

    return Evaluation(
        score=min(max(float(payload.get("score", 0.0)), 0.0), 1.0),
        gaps=_strings(payload.get("gaps")),
        oversimplifications=_strings(payload.get("oversimplifications")),
        assumed=_strings(payload.get("assumed")),
        contradictions=_strings(payload.get("contradictions")),
        next_step=str(payload.get("next_step", "")).strip(),
    )


def _strings(value: Any) -> list[str]:
    """Whatever the model sent, as a list of non-empty strings.

    Schema-validated output is still model output; a list of nulls would
    otherwise reach the database and then the screen.
    """
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]
