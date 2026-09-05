"""The lesson, remembered: reading and writing teaching sessions.

`POST /ai/professor` used to see only what the browser resent. This module is
what lets it see yesterday: which session a message belongs to, what the
professor had decided so far, and what the conversation has shown about the
learner — and it is what writes each turn down so tomorrow has something to
read.

Deliberately small. It does not decide pedagogy (that is the teaching policy)
and it does not call a model. It stores decisions, renders them for the prompt,
and records evidence. Everything here is owner-scoped through OwnedRepository,
the same way every other tenancy-sensitive query in this codebase is.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import NotFound
from noema.db.base import utcnow
from noema.db.models import TeachingSession, TeachingTurn, TurnRole
from noema.db.repository import OwnedRepository

__all__ = ["TeachingSessions", "render_session"]

#: How much of a session's own history rides in the prompt. The transcript
#: is still sent by the client for the current conversation; this block is the
#: *state* — what was decided and learned — not a second copy of the words.
MAX_UNDERSTANDING = 6
MAX_MISCONCEPTIONS = 4
MAX_PLAN = 12

#: Depth and level vocabulary the policy may use. Stored as strings so the
#: policy can refine the scale without a migration; validated here so a typo
#: in a prompt's output cannot become a permanent state.
LEVELS = ("introductory", "foundational", "intermediate", "advanced", "expert")


@dataclass(frozen=True, slots=True)
class Resumed:
    session: TeachingSession
    #: True when this call created the session rather than finding it.
    created: bool


class TeachingSessions:
    def __init__(self, db: AsyncSession, owner_id: uuid.UUID) -> None:
        self.db = db
        self.owner_id = owner_id
        self.sessions = OwnedRepository(db, TeachingSession, owner_id)
        self.turns = OwnedRepository(db, TeachingTurn, owner_id)

    async def start_or_resume(
        self,
        *,
        session_id: uuid.UUID | None,
        notebook_id: uuid.UUID | None,
        learning_goal: str,
    ) -> Resumed:
        """The session a message belongs to.

        With an id: that session, if it is this owner's and still open. Without
        one: a new session whose goal is the learner's first message, verbatim
        — the professor rewrites its own `session_goal`, never the learner's.
        """
        if session_id is not None:
            session = await self.sessions.get(session_id)
            if session.ended_at is not None:
                raise NotFound("That lesson has ended. Start a new one to continue.")
            return Resumed(session=session, created=False)

        session = await self.sessions.create(
            notebook_id=notebook_id,
            learning_goal=learning_goal.strip()[:4000],
        )
        return Resumed(session=session, created=True)

    async def latest_open(
        self, *, notebook_id: uuid.UUID | None
    ) -> TeachingSession | None:
        """Where the learner left off — for "Continue learning" on the home screen."""
        query = (
            select(TeachingSession)
            .where(
                TeachingSession.owner_id == self.owner_id,
                TeachingSession.ended_at.is_(None),
            )
            .order_by(TeachingSession.last_turn_at.desc().nulls_last())
            .limit(1)
        )
        if notebook_id is not None:
            query = query.where(TeachingSession.notebook_id == notebook_id)
        latest: TeachingSession | None = await self.db.scalar(query)
        return latest

    async def record_learner(
        self, session: TeachingSession, content: str
    ) -> TeachingTurn:
        return await self._record(session, TurnRole.LEARNER, content, intent="")

    async def record_noema(
        self,
        session: TeachingSession,
        content: str,
        *,
        intent: str,
        decision: dict[str, Any] | None = None,
        pedagogy: dict[str, Any] | None = None,
        blocks: list[Any] | None = None,
    ) -> TeachingTurn:
        turn = await self._record(
            session,
            TurnRole.NOEMA,
            content,
            intent=intent,
            decision=decision,
            pedagogy=pedagogy,
            blocks=blocks,
        )
        if pedagogy:
            self.apply_pedagogy(session, pedagogy, turn_index=session.turn_count)
        return turn

    async def _record(
        self,
        session: TeachingSession,
        role: TurnRole,
        content: str,
        *,
        intent: str,
        decision: dict[str, Any] | None = None,
        pedagogy: dict[str, Any] | None = None,
        blocks: list[Any] | None = None,
    ) -> TeachingTurn:
        turn = await self.turns.create(
            session_id=session.id,
            role=role,
            content=content,
            intent=intent,
            decision=decision,
            pedagogy=pedagogy,
            blocks=blocks,
            # The same estimate the context builder uses (chars ÷ 4), so the
            # budget it fits turns into is the budget that was measured.
            token_estimate=len(content) // 4,
        )
        session.turn_count += 1
        session.last_turn_at = utcnow()
        await self.db.flush()
        return turn

    async def history(
        self, session: TeachingSession, *, limit: int = 200
    ) -> list[TeachingTurn]:
        """The stored transcript, oldest first — what a returning learner sees."""
        rows = await self.db.execute(
            select(TeachingTurn)
            .where(
                TeachingTurn.session_id == session.id,
                TeachingTurn.owner_id == self.owner_id,
            )
            .order_by(TeachingTurn.created_at.asc())
            .limit(limit)
        )
        return list(rows.scalars())

    async def end(self, session: TeachingSession, *, at: datetime | None = None) -> None:
        session.ended_at = at or utcnow()
        await self.db.flush()

    @staticmethod
    def apply_pedagogy(
        session: TeachingSession, pedagogy: dict[str, Any], *, turn_index: int
    ) -> None:
        """Fold a reply's validated metadata into the session's state.

        JSONB columns are replaced, never mutated in place — SQLAlchemy does not
        notice an in-place edit to a dict or list, and the update would live in
        memory only (the same trap `study/scheduling.py` documents).
        """
        concept = _text(pedagogy.get("current_concept"))
        if concept:
            session.current_concept = concept[:200]
        topic = _text(pedagogy.get("current_topic"))
        if topic:
            session.current_topic = topic[:200]
        subject = _text(pedagogy.get("subject"))
        if subject and not session.subject:
            session.subject = subject[:200]
        goal = _text(pedagogy.get("session_goal"))
        if goal:
            session.session_goal = goal[:4000]

        level = _text(pedagogy.get("learner_level"))
        if level in LEVELS:
            session.learner_level = level
        depth = _text(pedagogy.get("depth"))
        if depth in LEVELS:
            session.depth = depth
        strategy = _text(pedagogy.get("strategy"))
        if strategy:
            session.strategy = strategy[:48]

        plan = pedagogy.get("plan")
        if isinstance(plan, list) and plan:
            session.plan = [
                {
                    "topic": _text(p.get("topic"))[:200],
                    "status": _text(p.get("status")) or "planned",
                }
                for p in plan
                if isinstance(p, dict) and _text(p.get("topic"))
            ][:MAX_PLAN]

        evidence = pedagogy.get("mastery_evidence")
        if isinstance(evidence, dict) and _text(evidence.get("concept")):
            entry = {
                "concept": _text(evidence.get("concept"))[:200],
                "verdict": _text(evidence.get("verdict"))[:32],
                "strength": _text(evidence.get("strength"))[:24],
                "turn": turn_index,
            }
            session.understanding = [*session.understanding, entry][-MAX_UNDERSTANDING:]

        misconception = _text(pedagogy.get("misconception"))
        if misconception:
            kept = [m for m in session.misconceptions if m != misconception]
            session.misconceptions = [*kept, misconception][-MAX_MISCONCEPTIONS:]

        resolved = _text(pedagogy.get("misconception_resolved"))
        if resolved:
            session.misconceptions = [m for m in session.misconceptions if m != resolved]


def render_session(session: TeachingSession) -> str:
    """The ACTIVE_SESSION block for the prompt. Empty for a session with no state yet.

    State, not transcript: what the professor decided, where the lesson is, and
    what the learner has shown. Kept short on purpose — a long block does not
    make the professor wiser, only slower.
    """
    lines: list[str] = []
    if session.learning_goal:
        lines.append(f"Learner's goal, in their words: {session.learning_goal}")
    if session.session_goal:
        lines.append(f"Your objective for this lesson: {session.session_goal}")
    if session.subject or session.current_topic or session.current_concept:
        where = " → ".join(
            part
            for part in (session.subject, session.current_topic, session.current_concept)
            if part
        )
        lines.append(f"Where the lesson is: {where}")
    lines.append(f"Learner level: {session.learner_level}. Depth: {session.depth}.")
    lines.append(f"Current strategy: {session.strategy}.")

    if session.plan:
        lines.append("Plan:")
        for item in session.plan[:MAX_PLAN]:
            lines.append(f"- [{item.get('status', 'planned')}] {item.get('topic', '')}")

    if session.understanding:
        lines.append("What the learner has shown so far:")
        for entry in session.understanding[-MAX_UNDERSTANDING:]:
            lines.append(
                f"- {entry.get('concept', '')}: {entry.get('verdict', '')}"
                f" ({entry.get('strength', '')} evidence, turn {entry.get('turn', '?')})"
            )

    if session.misconceptions:
        lines.append(
            "Misconceptions still open (correct them when they surface, do not lecture):"
        )
        for belief in session.misconceptions[-MAX_MISCONCEPTIONS:]:
            lines.append(f"- {belief}")

    if session.turn_count:
        lines.append(f"Turns so far: {session.turn_count}.")
    return "\n".join(lines)


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
