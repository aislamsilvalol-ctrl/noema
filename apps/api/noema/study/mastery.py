"""Projecting mastery from the evidence log.

The engine in ``noema.engines.mastery`` is pure and already tested; this module's
only job is to feed it real rows and store the decomposition it returns. Keeping
those two apart is what lets the formula be re-run over history when it changes.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.config import get_settings
from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.db.models import (
    Card,
    CardSchedule,
    Concept,
    ConceptEdge,
    ConceptMastery,
    EdgeKind,
    Review,
)
from noema.engines import fsrs
from noema.engines.mastery import CardSnapshot, Evidence, Grader, Mastery, compute_mastery

log = get_logger(__name__)

__all__ = ["recompute_for_review", "recompute_mastery"]

#: How far a change propagates. A review moves the concept it tested and the things
#: built on it, whose prior shifted — but two hops out the effect is noise, and
#: recomputing a whole workspace on every card is how a study session gets slow.
PROPAGATION_DEPTH = 2

#: Ratings map onto correctness. "Hard" is a recall that worked, so it counts as
#: correct — with a lower score, because it nearly did not.
RATING_SCORES: dict[int, float] = {1: 0.0, 2: 0.6, 3: 0.85, 4: 1.0}


async def recompute_mastery(
    session: AsyncSession,
    concept_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    now: datetime | None = None,
) -> Mastery | None:
    """Recompute and store mastery for one concept."""
    now = now or utcnow()

    concept = await session.scalar(
        select(Concept).where(Concept.id == concept_id, Concept.owner_id == owner_id)
    )
    if concept is None:
        return None

    evidence = await _evidence(session, concept_id, owner_id, now)
    cards = await _card_snapshots(session, concept_id, owner_id, now)
    prerequisites = await _prerequisite_masteries(session, concept_id, owner_id)

    mastery = compute_mastery(evidence, cards, prerequisites)
    await _store(session, concept_id, owner_id, mastery, evidence, now)
    return mastery


async def recompute_for_review(
    session: AsyncSession,
    concept_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    now: datetime | None = None,
) -> None:
    """Recompute a concept and the concepts that depend on it.

    A dependent's prior is drawn from its prerequisites, so improving the chain rule
    genuinely changes what we believe about backpropagation even though no card of
    backpropagation was answered.
    """
    now = now or utcnow()
    seen: set[uuid.UUID] = set()
    frontier = {concept_id}

    for _ in range(PROPAGATION_DEPTH):
        if not frontier:
            break
        for current in frontier:
            if current not in seen:
                await recompute_mastery(session, current, owner_id=owner_id, now=now)
                seen.add(current)

        dependents = (
            await session.scalars(
                select(ConceptEdge.dst_id).where(
                    ConceptEdge.src_id.in_(frontier),
                    ConceptEdge.kind == EdgeKind.PREREQUISITE_OF,
                )
            )
        ).all()
        frontier = {d for d in dependents if d not in seen}


async def _evidence(
    session: AsyncSession, concept_id: uuid.UUID, owner_id: uuid.UUID, now: datetime
) -> list[Evidence]:
    rows = (
        await session.execute(
            select(Review.rating, Review.confidence, Review.reviewed_at, Card.type)
            .join(Card, Card.id == Review.card_id)
            .where(Review.concept_id == concept_id, Review.owner_id == owner_id)
            .order_by(Review.reviewed_at.desc())
            .limit(500)
        )
    ).all()

    evidence: list[Evidence] = []
    for rating, confidence, reviewed_at, _card_type in rows:
        moment = reviewed_at if reviewed_at.tzinfo else reviewed_at.replace(tzinfo=UTC)
        evidence.append(
            Evidence(
                score=RATING_SCORES.get(int(rating), 0.5),
                # Card reviews are self-graded recall, so they are mid-difficulty by
                # construction. Real item difficulty arrives with the quiz engine.
                difficulty=0.5,
                age_days=max((now - moment).total_seconds() / 86400, 0.0),
                grader=Grader.DETERMINISTIC,
                confidence=confidence,
            )
        )
    return evidence


async def _card_snapshots(
    session: AsyncSession, concept_id: uuid.UUID, owner_id: uuid.UUID, now: datetime
) -> list[CardSnapshot]:
    rows = (
        (
            await session.execute(
                select(CardSchedule)
                .join(Card, Card.id == CardSchedule.card_id)
                .where(
                    Card.concept_id == concept_id,
                    Card.owner_id == owner_id,
                    Card.deleted_at.is_(None),
                    CardSchedule.reps > 0,
                )
            )
        )
        .scalars()
        .all()
    )

    snapshots: list[CardSnapshot] = []
    for schedule in rows:
        last = schedule.last_review_at
        if last is None:
            continue
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        snapshots.append(
            CardSnapshot(
                state=fsrs.MemoryState(
                    stability=max(schedule.stability, 0.01),
                    difficulty=min(max(schedule.difficulty, 1.0), 10.0),
                ),
                elapsed_days=max((now - last).total_seconds() / 86400, 0.0),
            )
        )
    return snapshots


async def _prerequisite_masteries(
    session: AsyncSession, concept_id: uuid.UUID, owner_id: uuid.UUID
) -> list[tuple[float, float]]:
    rows = (
        await session.execute(
            select(ConceptMastery.mastery, ConceptEdge.weight)
            .join(ConceptEdge, ConceptEdge.src_id == ConceptMastery.concept_id)
            .where(
                ConceptEdge.dst_id == concept_id,
                ConceptEdge.kind == EdgeKind.PREREQUISITE_OF,
                ConceptMastery.owner_id == owner_id,
            )
        )
    ).all()
    return [(float(mastery), float(weight)) for mastery, weight in rows]


async def _store(
    session: AsyncSession,
    concept_id: uuid.UUID,
    owner_id: uuid.UUID,
    mastery: Mastery,
    evidence: Sequence[Evidence],
    now: datetime,
) -> None:
    row = await session.scalar(
        select(ConceptMastery).where(
            ConceptMastery.concept_id == concept_id,
            ConceptMastery.owner_id == owner_id,
        )
    )
    if row is None:
        row = ConceptMastery(owner_id=owner_id, concept_id=concept_id)
        session.add(row)

    row.mastery = mastery.score
    row.competence = mastery.competence
    row.retrievability = mastery.retrievability
    row.uncertainty = mastery.uncertainty
    row.calibration = mastery.calibration
    row.evidence_count = mastery.effective_observations
    row.last_evidence_at = now if evidence else None
    row.model_version = get_settings().noema_mastery_model_version
    # Stored so the UI can show the working. A number a learner cannot interrogate
    # is one they will argue with rather than act on.
    row.components = {
        "competence": round(mastery.competence, 4),
        "retrievability": round(mastery.retrievability, 4),
        "prior_mean": round(mastery.prior_mean, 4),
        "uncertainty": round(mastery.uncertainty, 4),
        "calibration": round(mastery.calibration, 4),
        "effective_observations": round(mastery.effective_observations, 2),
        "provisional": mastery.is_provisional,
    }

    await session.flush()
