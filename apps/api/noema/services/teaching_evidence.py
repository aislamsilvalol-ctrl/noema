"""What a conversation shows about the learner, counted — carefully.

A Professor turn's PEDAGOGY record may carry one `mastery_evidence` entry: the
concept the learner just showed something about, a verdict, and how strong the
showing was. This turns it into the same kind of row the Feynman and Socratic
paths already write (`Explanation`), so the mastery engine sees it with the
rest — but as the weakest evidence there is: AI-judged, from a chat, at the
easiest difficulty. A lesson should move the number a little, not decide it.

The concept is matched by name within the owner's own concepts. No match, no
row: inventing a concept from a model's phrasing would pollute the graph.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.base import utcnow
from noema.db.models import Concept, Explanation, ExplanationKind, Grader
from noema.knowledge.resolution import normalize_name
from noema.study.mastery import recompute_for_review

__all__ = ["record_conversational_evidence"]

#: A verdict, as a score the engine understands. "unknown" never reaches here —
#: parse_pedagogy drops it, because no evidence is not weak evidence.
SCORES = {"understood": 1.0, "partial": 0.5, "misunderstood": 0.0}


async def record_conversational_evidence(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    session_id: uuid.UUID,
    pedagogy: dict[str, Any],
    learner_text: str,
    now: datetime | None = None,
) -> Explanation | None:
    evidence = pedagogy.get("mastery_evidence")
    if not isinstance(evidence, dict):
        return None
    score = SCORES.get(str(evidence.get("verdict", "")))
    name = str(evidence.get("concept", "")).strip()
    if score is None or not name:
        return None

    concept = await db.scalar(
        select(Concept)
        .where(
            Concept.owner_id == owner_id,
            Concept.normalized_name == normalize_name(name),
        )
        .limit(1)
    )
    if concept is None:
        return None

    now = now or utcnow()
    row = Explanation(
        owner_id=owner_id,
        concept_id=concept.id,
        kind=ExplanationKind.CONVERSATION,
        text=learner_text.strip()[:4000] or "(no words recorded)",
        score=score,
        grader=Grader.AI,
        findings={
            "source": "teaching_session",
            "session_id": str(session_id),
            "strength": evidence.get("strength", "weak"),
            "situation": pedagogy.get("situation"),
        },
        explained_at=now,
    )
    db.add(row)
    await db.flush()
    await recompute_for_review(db, concept.id, owner_id=owner_id, now=now)
    return row
