"""Socratic mode: questioned until you say it yourself.

The difference from the tutor's Socratic prompt is that this one *ends*. Each turn
returns either the next question or a verdict, and when it reaches a verdict the
dialogue is recorded as evidence — because arriving at an idea under questioning is
something the learner did, and a mode that leaves no trace is a chat window with a
theme.

It is not the same act as writing an explanation cold, so it is stored as its own
kind and weighed slightly lower. Being walked to a conclusion is real understanding
with a hand on your elbow.
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
from noema.db.models import Concept, Explanation, ExplanationKind, Grader
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
from noema.study.mastery import recompute_for_review

log = get_logger(__name__)

__all__ = ["Turn", "next_turn"]

#: After this many exchanges the dialogue concludes with whatever was reached. A
#: Socratic session that never ends records nothing, and the learner who gave up
#: on turn twelve deserves the credit for the eleven before it.
MAX_EXCHANGES = 8

SCHEMA: dict[str, Any] = json.loads(
    (PROMPT_DIR / "socratic.turn.schema.json").read_text(encoding="utf-8")
)


@dataclass(frozen=True, slots=True)
class Turn:
    #: The next question, or empty when the dialogue is over.
    question: str
    reached: bool
    score: float
    assessment: str
    #: Set when this turn concluded the dialogue and recorded it.
    explanation_id: uuid.UUID | None = None
    #: True when the turn limit ended it rather than the learner getting there.
    exhausted: bool = False


async def next_turn(
    session: AsyncSession,
    concept_id: uuid.UUID,
    transcript: list[dict[str, str]],
    *,
    owner_id: uuid.UUID,
    gateway: AIGateway | None = None,
    model: str | None = None,
    now: datetime | None = None,
) -> Turn:
    """Ask the next question, or end the dialogue and record what was reached."""
    now = now or utcnow()

    concept = await session.scalar(
        select(Concept).where(Concept.id == concept_id, Concept.owner_id == owner_id)
    )
    if concept is None:
        raise NotFound("Concept not found")
    if gateway is None:
        raise ProviderUnavailable(
            "No model is configured, so there is nobody to hold the other side of "
            "the conversation."
        )

    context = await source_context(session, concept, owner_id)
    verdict = await _ask(concept, transcript, context, gateway, model)

    answers = [entry for entry in transcript if entry.get("role") == "learner"]
    exhausted = len(answers) >= MAX_EXCHANGES

    if not verdict.reached and not exhausted:
        return verdict

    explanation = Explanation(
        owner_id=owner_id,
        concept_id=concept_id,
        kind=ExplanationKind.SOCRATIC,
        # What the learner said, not the questions: the record is of their
        # reasoning, and keeping our own prompts in the `text` would flatter it.
        text="\n\n".join(entry.get("content", "") for entry in answers).strip(),
        score=verdict.score,
        grader=Grader.AI,
        findings={"assessment": verdict.assessment, "reached": verdict.reached},
        transcript=list(transcript),
        explained_at=now,
    )
    session.add(explanation)
    await session.flush()

    await recompute_for_review(session, concept_id, owner_id=owner_id, now=now)

    return Turn(
        question="",
        reached=verdict.reached,
        score=verdict.score,
        assessment=verdict.assessment,
        explanation_id=explanation.id,
        exhausted=exhausted and not verdict.reached,
    )


async def _ask(
    concept: Concept,
    transcript: list[dict[str, str]],
    context: str,
    gateway: AIGateway,
    model: str | None,
) -> Turn:
    prompt = load("socratic.turn")

    dialogue = "\n".join(
        f"{'LEARNER' if entry.get('role') == 'learner' else 'YOU'}: "
        f"{entry.get('content', '')}"
        for entry in transcript
    )

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
                            f"<DIALOGUE>\n{dialogue or '(not started)'}\n</DIALOGUE>"
                        ),
                    ),
                ],
                json_schema=SCHEMA,
                task=TaskClass.TUTOR_CHAT,
                model=model,
            )
        )
    except ProviderError as exc:
        log.warning("socratic.failed", concept_id=str(concept.id), error=str(exc))
        raise ProviderUnavailable(f"The dialogue could not continue: {exc}") from exc

    question = str(payload.get("question", "")).strip()
    reached = bool(payload.get("reached", False))

    return Turn(
        # A turn that claims to continue without asking anything would strand the
        # learner in front of an empty box.
        question=question,
        reached=reached or not question,
        score=min(max(float(payload.get("score", 0.0)), 0.0), 1.0),
        assessment=str(payload.get("assessment", "")).strip(),
    )
