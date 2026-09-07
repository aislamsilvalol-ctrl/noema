"""Pseudonymous export of learning evidence, in Aquilante's LearningEvent shape.

The one place the product's two evidence trails meet: flashcard reviews
(``Review``), graded answers (``Answer``) and the Professor's mastery events
(``MasteryEvent``) become one stream of events a learner model can read.
Identity never leaves: ``student_id`` is an HMAC of the user id under a
secret the export is given, and no text field is copied — not the question,
not the chosen option, not a note. What crosses the boundary is: who
(pseudonym), which concept, which item, when, what kind, right or wrong,
how long, how sure, which session.

This module is deliberately independent of the ``aquilante`` package: it
writes the schema, it does not import it, so the product does not depend on
the engine to record its own history.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import Answer, MasteryEvent, Review

SCHEMA_VERSION = 1
SOURCE = "noema"

#: MasteryEvent kinds that are graded showings (the rest are exposures).
GRADED_KINDS = {"quiz", "check", "flashcard", "assessment", "teach_back"}


def pseudonym(secret: str, user_id: uuid.UUID) -> str:
    return (
        "u_"
        + hmac.new(secret.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()[
            :24
        ]
    )


def _ts(dt: datetime) -> float:
    return dt.timestamp()


def _confidence_from_scale(value: int | None) -> float | None:
    """The product asks 1 … 5; the schema wants 0 … 1."""
    if value is None:
        return None
    return max(0.0, min(1.0, (int(value) - 1) / 4.0))


def event_from_review(review: Review, secret: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": f"review:{review.id}",
        "student_id": pseudonym(secret, review.owner_id),
        "concept_id": f"concept:{review.concept_id}"
        if review.concept_id
        else f"card:{review.card_id}",
        "item_id": f"card:{review.card_id}",
        "timestamp": _ts(review.reviewed_at),
        "event_type": "recall",
        # FSRS ratings: 1 again · 2 hard · 3 good · 4 easy. "Again" is a lapse.
        "correct": review.rating >= 2,
        "difficulty": None,
        "response_ms": review.elapsed_ms or None,
        "hints": 0,
        "attempt": 1,
        "confidence": _confidence_from_scale(review.confidence),
        "session_id": None,
        "source": SOURCE,
        "extra": {"rating": review.rating},
    }


def event_from_answer(answer: Answer, secret: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": f"answer:{answer.id}",
        "student_id": pseudonym(secret, answer.owner_id),
        "concept_id": f"concept:{answer.concept_id}"
        if answer.concept_id
        else f"question:{answer.question_id}",
        "item_id": f"question:{answer.question_id}",
        "timestamp": _ts(answer.answered_at),
        "event_type": "answer",
        "correct": bool(answer.is_correct),
        "difficulty": None,
        "response_ms": answer.elapsed_ms or None,
        "hints": 0,
        "attempt": 1,
        "confidence": _confidence_from_scale(answer.confidence),
        "session_id": None,
        "source": SOURCE,
        "extra": {"score": answer.score, "grader": str(answer.grader)},
    }


def event_from_mastery(event: MasteryEvent, secret: str) -> dict[str, Any]:
    graded = event.kind in GRADED_KINDS
    concept = (
        f"concept:{event.concept_id}"
        if event.concept_id
        else f"name:{event.concept_name.strip().lower()}"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": f"mastery:{event.id}",
        "student_id": pseudonym(secret, event.owner_id),
        "concept_id": concept,
        "item_id": event.item_id,
        "timestamp": _ts(event.created_at),
        "event_type": "answer" if graded else "exposure",
        "correct": (event.score >= 0.5) if graded else None,
        "difficulty": event.difficulty,
        "response_ms": event.elapsed_ms,
        "hints": 0,
        "attempt": 1,
        "confidence": event.confidence,
        "session_id": str(event.session_id) if event.session_id else None,
        "source": SOURCE,
        "extra": {
            "kind": event.kind,
            "score": event.score,
            "journey": str(event.journey_id),
        },
    }


async def export_events(
    db: AsyncSession,
    *,
    secret: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield events from the three trails, oldest first within each trail."""
    if not secret or len(secret) < 16:
        raise ValueError(
            "the export needs a secret of at least 16 characters for the pseudonyms"
        )

    q_rev = select(Review).order_by(Review.reviewed_at)
    q_ans = select(Answer).order_by(Answer.answered_at)
    q_mas = select(MasteryEvent).order_by(MasteryEvent.created_at)
    if since is not None:
        q_rev = q_rev.where(Review.reviewed_at >= since)
        q_ans = q_ans.where(Answer.answered_at >= since)
        q_mas = q_mas.where(MasteryEvent.created_at >= since)
    if until is not None:
        q_rev = q_rev.where(Review.reviewed_at < until)
        q_ans = q_ans.where(Answer.answered_at < until)
        q_mas = q_mas.where(MasteryEvent.created_at < until)

    for review in (await db.execute(q_rev)).scalars():
        yield event_from_review(review, secret)
    for answer in (await db.execute(q_ans)).scalars():
        yield event_from_answer(answer, secret)
    for event in (await db.execute(q_mas)).scalars():
        yield event_from_mastery(event, secret)


def to_jsonl(event: dict[str, Any]) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"))
