"""LEARNING CHECKPOINT: consolidation, decided pedagogically.

Two decisions live here and are kept apart on purpose. `compaction_due`
is technical: the active context is large. `checkpoint_due` is pedagogical:
enough concepts were introduced since the last checkpoint *and* the lesson
is at a boundary (the router is not in the middle of a correction or a
question). They may coincide; a big context alone never forces an exam.

`run_checkpoint` is the flow the brief lists: finish the concept, summarise,
update the student model (the compactor does both), cards for consolidated
concepts that have none, compact old context, and — when there are concepts
introduced without strong evidence — write a short assessment for the next
turn to open. Every step is optional in failure: a step that cannot run is
skipped and logged, and the lesson continues.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.db.models import (
    Assessment,
    Card,
    ConceptState,
    LearningJourney,
    TeachingSession,
    TeachingTurn,
    TurnRole,
)
from noema.providers.gateway import AIGateway

from . import assessment as assessments
from . import flashcards
from .memory import ContextCompactor
from .moves import Move
from .student import StudentModel

log = get_logger(__name__)

__all__ = ["CheckpointOutcome", "checkpoint_due", "run_checkpoint"]


@dataclass
class CheckpointOutcome:
    compacted_turns: int = 0
    tokens_saved: int = 0
    cards: list[Card] = field(default_factory=list)
    assessment: Assessment | None = None
    events: list[dict[str, Any]] = field(default_factory=list)


def checkpoint_due(
    journey: LearningJourney,
    *,
    last_move: str,
    every_concepts: int,
    enabled: bool,
) -> bool:
    if not enabled:
        return False
    if journey.concepts_since_checkpoint < every_concepts:
        return False
    # Not mid-correction, not while a question is waiting for its answer.
    return last_move not in (
        Move.CORRECT.value,
        Move.QUESTION.value,
        Move.QUIZ.value,
        Move.EXAM.value,
    )


async def run_checkpoint(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    journey: LearningJourney,
    session: TeachingSession,
    turns: Sequence[TeachingTurn],
    gateway: AIGateway,
    model: str | None,
    keep: int,
    fold_after: int,
    with_assessment: bool,
    flashcards_enabled: bool,
    now: datetime | None = None,
) -> CheckpointOutcome:
    now = now or utcnow()
    outcome = CheckpointOutcome()
    student = StudentModel(db, owner_id, journey)

    # 2-4, 6: summary, student model, profile, archive.
    compactor = ContextCompactor(
        db,
        owner_id=owner_id,
        journey=journey,
        session=session,
        gateway=gateway,
        model=model,
        keep=keep,
        fold_after=fold_after,
    )
    result = await compactor.compact(turns, now=now)
    outcome.compacted_turns = result.archived_turns
    outcome.tokens_saved = result.tokens_saved
    if result.archived_turns:
        outcome.events.append(
            {
                "event": "memory",
                "data": {
                    "compacted_turns": result.archived_turns,
                    "tokens_saved": result.tokens_saved,
                    "folded": result.folded,
                },
            }
        )

    # 5: cards for what landed and has none.
    context = "\n".join(
        f"{'Learner' if t.role is TurnRole.LEARNER else 'Mino'}: {t.content}"
        for t in turns[-12:]
    )
    states = await student.states()
    if flashcards_enabled:
        for state in states:
            landed = state.state in (
                ConceptState.LEARNING.value,
                ConceptState.MASTERED.value,
            )
            if not flashcards.should_card(state, understood=landed):
                continue
            cards = await flashcards.generate_for_concept(
                db,
                owner_id=owner_id,
                journey=journey,
                concept=state.name,
                context=context,
                gateway=gateway,
                model=model,
                now=now,
            )
            outcome.cards.extend(cards)
            if len(outcome.cards) >= 8:
                break

    # 7: an assessment, when pedagogically useful — concepts were introduced
    # and the lesson has little strong evidence about them.
    if with_assessment:
        untested = [
            s.name
            for s in states
            if s.introduced_at is not None and s.strong_evidence_count == 0
        ][:6]
        if len(untested) >= 2:
            outcome.assessment = await assessments.create_assessment(
                db,
                owner_id=owner_id,
                journey=journey,
                session_id=session.id,
                kind="checkpoint",
                concepts=untested,
                context=context,
                gateway=gateway,
                model=model,
                now=now,
            )
    if outcome.assessment is None:
        # No paper: the checkpoint still counts as consolidation.
        journey.concepts_since_checkpoint = 0
        journey.last_checkpoint_at = now
        journey.checkpoints += 1
    await db.flush()
    return outcome
