"""Selective context the Professor pulls in before it explains something.

Not a context dump. The spec this module implements is explicit about that: every
message does not need every fact this account has ever produced, and sending it all
would both blow the token budget and bury the one thing actually relevant to what the
student just asked. This queries the *existing* mastery and misconception tables --
it stores nothing new -- and returns a small, bounded snapshot: the concepts this
notebook has recently touched, and any misconception still open for one of them.

Concepts are found through ``Card``/``Question`` (both carry ``notebook_id`` and an
optional ``concept_id``), because ``Concept`` itself is workspace-scoped, not
notebook-scoped -- there is no direct notebook -> concept column to query.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import Card, Concept, ConceptMastery, Mistake, Question

#: Bounds, not tuned values -- keeps the block small regardless of how much
#: history an account has. A longer list would not make the Professor smarter,
#: only more expensive per turn.
MAX_CONCEPTS = 5
MAX_MISCONCEPTIONS = 3
#: A misconception's summary is free text (an AI-written belief statement) with
#: no length cap of its own -- this keeps one long one from crowding out the rest
#: of the block.
MAX_SUMMARY_CHARS = 220


@dataclass(frozen=True, slots=True)
class ConceptSnapshot:
    name: str
    mastery: float
    evidence_count: float


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    concepts: tuple[ConceptSnapshot, ...]
    misconceptions: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not self.concepts and not self.misconceptions

    def render(self) -> str:
        """A compact block for the prompt. Empty string when there is nothing --
        the caller only appends a message when this is non-empty, the same way
        ``noema/api/v1/ai.py``'s ``_assemble`` skips a materials block when
        retrieval found nothing.
        """
        lines: list[str] = []
        if self.concepts:
            lines.append("Concepts this notebook has covered, with current mastery:")
            for concept in self.concepts:
                pct = round(concept.mastery * 100)
                lines.append(f"- {concept.name}: {pct}% mastery")
        if self.misconceptions:
            lines.append("Misconceptions still open for this student here:")
            for summary in self.misconceptions:
                lines.append(f"- {summary}")
        return "\n".join(lines)


async def _notebook_concept_ids(
    db: AsyncSession, *, owner_id: uuid.UUID, notebook_id: uuid.UUID
) -> list[uuid.UUID]:
    """Concepts touched in this notebook, via the cards and questions in it.

    A ``UNION`` rather than two round trips -- either source is enough to prove a
    concept belongs here, and a concept referenced by both should not be counted
    twice.
    """
    from_cards = select(Card.concept_id).where(
        Card.notebook_id == notebook_id,
        Card.owner_id == owner_id,
        Card.concept_id.is_not(None),
    )
    from_questions = select(Question.concept_id).where(
        Question.notebook_id == notebook_id,
        Question.owner_id == owner_id,
        Question.concept_id.is_not(None),
    )
    result = await db.execute(from_cards.union(from_questions))
    return [row for row in result.scalars().all() if row is not None]


async def build_memory(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    notebook_id: uuid.UUID,
    max_concepts: int = MAX_CONCEPTS,
    max_misconceptions: int = MAX_MISCONCEPTIONS,
) -> MemorySnapshot:
    """Selective mastery + open-misconception context for one notebook.

    Scoped to ``owner_id`` on every query -- ``ConceptMastery`` and ``Mistake`` are
    both ``OwnedEntity``, so this filters the same way every other tenancy-sensitive
    query in this codebase does, not a bespoke check.
    """
    concept_ids = await _notebook_concept_ids(
        db, owner_id=owner_id, notebook_id=notebook_id
    )

    concepts: tuple[ConceptSnapshot, ...] = ()
    if concept_ids:
        result = await db.execute(
            select(Concept.name, ConceptMastery.mastery, ConceptMastery.evidence_count)
            .join(ConceptMastery, ConceptMastery.concept_id == Concept.id)
            .where(
                Concept.id.in_(concept_ids),
                ConceptMastery.owner_id == owner_id,
            )
            .order_by(ConceptMastery.last_evidence_at.desc().nulls_last())
            .limit(max_concepts)
        )
        concepts = tuple(
            ConceptSnapshot(name=name, mastery=mastery, evidence_count=count)
            for name, mastery, count in result.all()
        )

    misconceptions: tuple[str, ...] = ()
    if concept_ids:
        result = await db.execute(
            select(Mistake.summary)
            .join(Question, Question.id == Mistake.question_id)
            .where(
                Question.notebook_id == notebook_id,
                Mistake.owner_id == owner_id,
                Mistake.is_misconception.is_(True),
                Mistake.resolved_at.is_(None),
                Mistake.summary.is_not(None),
            )
            .order_by(Mistake.created_at.desc())
            .limit(max_misconceptions)
        )
        misconceptions = tuple(
            summary[:MAX_SUMMARY_CHARS] for (summary,) in result.all() if summary
        )

    return MemorySnapshot(concepts=concepts, misconceptions=misconceptions)
