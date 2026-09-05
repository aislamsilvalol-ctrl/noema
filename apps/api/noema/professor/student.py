"""The student model: what one learner knows, per concept, on one journey.

Two tables and a rule. `MasteryEvent` is the append-only log — every quiz
option, checkpoint answer, flashcard recall, teach-back, and the professor's
own reading of a chat line. `StudentConceptState` is the projection: a score,
a stage, streaks, open misconceptions. The rule: the projection is a pure
function of the events (`project`), so a change to the weights is a replay,
not a migration of opinions.

Weights say how much a kind of showing counts. A quiz option recognised is
worth less than an answer produced; the professor judging a chat line is
worth least, because it is an AI reading an AI's conversation.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.base import utcnow
from noema.db.models import (
    ConceptState,
    LearningJourney,
    MasteryEvent,
    StudentConceptState,
)
from noema.knowledge.resolution import normalize_name

__all__ = [
    "KIND_WEIGHTS",
    "Projection",
    "StudentModel",
    "project",
    "render_knowledge",
    "stage_for",
]

#: How much each kind of evidence counts.
KIND_WEIGHTS: dict[str, float] = {
    "conversation": 0.35,
    "quiz": 0.7,
    "flashcard": 0.8,
    "check": 1.0,
    "teach_back": 1.2,
    "assessment": 1.1,
}
#: Kinds that are not the professor's own judgement of a chat line.
STRONG_KINDS = frozenset({"quiz", "flashcard", "check", "teach_back", "assessment"})

#: A mastered concept not shown for this long is due for review.
REVIEW_AFTER = timedelta(days=7)

#: How many recent events shape the score. Older ones still count, less.
DECAY = 0.75


@dataclass(frozen=True, slots=True)
class Projection:
    score: float
    evidence_count: int
    strong_evidence_count: int
    correct_streak: int
    wrong_streak: int
    stage: str


def project(
    scores: Sequence[tuple[str, float]], *, introduced: bool, last_at: datetime | None
) -> Projection:
    """From (kind, score) pairs oldest-first to a state.

    A recency-weighted mean: each event's weight is its kind's weight times a
    decay for its age in the sequence, so the last three answers matter more
    than the first three without the first ever being forgotten.
    """
    if not scores:
        return Projection(0.0, 0, 0, 0, 0, stage_for(0.0, 0, 0, introduced, last_at))
    weighted = 0.0
    total = 0.0
    n = len(scores)
    for index, (kind, score) in enumerate(scores):
        age = n - 1 - index
        weight = KIND_WEIGHTS.get(kind, 0.5) * (DECAY**age)
        weighted += weight * max(0.0, min(1.0, score))
        total += weight
    value = weighted / total if total else 0.0

    correct = 0
    for _, score in reversed(scores):
        if score >= 0.6:
            correct += 1
        else:
            break
    wrong = 0
    for _, score in reversed(scores):
        if score < 0.6:
            wrong += 1
        else:
            break
    strong = sum(1 for kind, _ in scores if kind in STRONG_KINDS)
    return Projection(
        score=round(value, 4),
        evidence_count=n,
        strong_evidence_count=strong,
        correct_streak=correct,
        wrong_streak=wrong,
        stage=stage_for(value, n, strong, introduced, last_at),
    )


def stage_for(
    score: float, evidence: int, strong: int, introduced: bool, last_at: datetime | None
) -> str:
    if evidence == 0:
        return (
            ConceptState.INTRODUCED.value
            if introduced
            else ConceptState.NOT_STARTED.value
        )
    if score >= 0.8 and evidence >= 3 and strong >= 1:
        if last_at is not None and utcnow() - last_at > REVIEW_AFTER:
            return ConceptState.NEEDS_REVIEW.value
        return ConceptState.MASTERED.value
    if score < 0.4 and evidence >= 2:
        return ConceptState.UNCERTAIN.value
    return ConceptState.LEARNING.value


class StudentModel:
    """Reads and writes one journey's knowledge state. Owner-scoped throughout."""

    def __init__(self, db: AsyncSession, owner_id: uuid.UUID, journey: LearningJourney):
        self.db = db
        self.owner_id = owner_id
        self.journey = journey

    async def states(self) -> list[StudentConceptState]:
        rows = await self.db.execute(
            select(StudentConceptState)
            .where(
                StudentConceptState.journey_id == self.journey.id,
                StudentConceptState.owner_id == self.owner_id,
            )
            .order_by(StudentConceptState.created_at.asc())
        )
        return list(rows.scalars())

    async def get(self, name: str) -> StudentConceptState | None:
        state: StudentConceptState | None = await self.db.scalar(
            select(StudentConceptState).where(
                StudentConceptState.journey_id == self.journey.id,
                StudentConceptState.owner_id == self.owner_id,
                StudentConceptState.normalized_name == normalize_name(name),
            )
        )
        return state

    async def ensure(self, name: str) -> StudentConceptState:
        state = await self.get(name)
        if state is not None:
            return state
        state = StudentConceptState(
            owner_id=self.owner_id,
            journey_id=self.journey.id,
            name=name.strip()[:200],
            normalized_name=normalize_name(name),
        )
        self.db.add(state)
        await self.db.flush()
        return state

    async def mark_introduced(
        self, names: Iterable[str], *, now: datetime | None = None
    ) -> int:
        """The lesson reached these concepts. Counts toward the checkpoint."""
        now = now or utcnow()
        fresh = 0
        for name in names:
            if not name or not name.strip():
                continue
            state = await self.ensure(name)
            if state.introduced_at is None:
                state.introduced_at = now
                fresh += 1
                if state.state == ConceptState.NOT_STARTED.value:
                    state.state = ConceptState.INTRODUCED.value
        if fresh:
            self.journey.concepts_since_checkpoint += fresh
        await self.db.flush()
        return fresh

    async def record(
        self,
        name: str,
        *,
        kind: str,
        score: float,
        detail: dict[str, Any] | None = None,
        turn_id: uuid.UUID | None = None,
        misconception: str | None = None,
        note: str | None = None,
        now: datetime | None = None,
    ) -> StudentConceptState:
        """Append one event and re-project the concept's state."""
        now = now or utcnow()
        state = await self.ensure(name)
        weight = KIND_WEIGHTS.get(kind, 0.5)
        self.db.add(
            MasteryEvent(
                owner_id=self.owner_id,
                journey_id=self.journey.id,
                concept_name=state.name,
                kind=kind,
                score=max(0.0, min(1.0, score)),
                weight=weight,
                detail=detail or {},
                turn_id=turn_id,
                created_at=now,
            )
        )
        await self.db.flush()
        if state.introduced_at is None:
            # Evidence about a concept the lesson never named still counts
            # as the lesson reaching it — toward the checkpoint too.
            state.introduced_at = now
            self.journey.concepts_since_checkpoint += 1
        if misconception:
            kept = [m for m in state.misconceptions if m != misconception]
            state.misconceptions = [*kept, misconception][-4:]
        if note:
            kept = [n for n in state.notes if n != note]
            state.notes = [*kept, note][-4:]
        await self.reproject(state, now=now)
        return state

    async def resolve_misconception(self, name: str, belief: str) -> None:
        state = await self.get(name)
        if state is None:
            return
        state.misconceptions = [m for m in state.misconceptions if m != belief]
        await self.db.flush()

    async def reproject(self, state: StudentConceptState, *, now: datetime) -> None:
        rows = await self.db.execute(
            select(MasteryEvent.kind, MasteryEvent.score)
            .where(
                MasteryEvent.journey_id == self.journey.id,
                MasteryEvent.owner_id == self.owner_id,
                MasteryEvent.concept_name == state.name,
            )
            .order_by(MasteryEvent.created_at.asc(), MasteryEvent.id.asc())
        )
        scores = [(kind, score) for kind, score in rows.all()]
        projection = project(
            scores, introduced=state.introduced_at is not None, last_at=now
        )
        state.score = projection.score
        state.evidence_count = projection.evidence_count
        state.strong_evidence_count = projection.strong_evidence_count
        state.correct_streak = projection.correct_streak
        state.wrong_streak = projection.wrong_streak
        state.state = projection.stage
        state.last_evidence_at = now
        await self.db.flush()

    async def snapshot(self, *, focus: Sequence[str] = ()) -> str:
        """The KNOWLEDGE_STATE block for the prompt, bounded."""
        return render_knowledge(
            await self.states(), focus=focus, profile=self.journey.profile
        )

    async def public(self) -> list[dict[str, Any]]:
        return [
            {
                "name": s.name,
                "state": s.state,
                "evidence": s.evidence_count,
                "misconceptions": list(s.misconceptions),
            }
            for s in await self.states()
        ]


def render_knowledge(
    states: Sequence[StudentConceptState],
    *,
    focus: Sequence[str] = (),
    profile: dict[str, Any] | None = None,
    limit: int = 10,
) -> str:
    """Current lesson's concepts first, then the weakest, then the rest, up to
    `limit`; open misconceptions; the profile's few lines. Empty when nothing
    is known yet — the caller appends nothing then."""
    if not states and not profile:
        return ""
    focus_keys = {normalize_name(f) for f in focus}
    focused = [s for s in states if s.normalized_name in focus_keys]
    weak = sorted(
        (
            s
            for s in states
            if s not in focused and s.state == ConceptState.UNCERTAIN.value
        ),
        key=lambda s: s.score,
    )
    rest = [s for s in states if s not in focused and s not in weak]
    chosen = (focused + weak + rest)[:limit]

    lines: list[str] = []
    if chosen:
        lines.append("Knowledge state (stage · evidence count):")
        for s in chosen:
            lines.append(f"- {s.name}: {s.state} · {s.evidence_count}")
    beliefs = [(s.name, m) for s in states for m in s.misconceptions][:4]
    if beliefs:
        lines.append("Open misconceptions (correct when they surface, do not lecture):")
        for name, belief in beliefs:
            lines.append(f"- {name}: {belief}")
    if profile:
        bits = []
        if profile.get("preferred_depth"):
            bits.append(f"prefers {profile['preferred_depth']} depth")
        for pattern in list(profile.get("patterns", []))[:3]:
            bits.append(str(pattern))
        if bits:
            lines.append("About this learner: " + "; ".join(bits) + ".")
    return "\n".join(lines)
