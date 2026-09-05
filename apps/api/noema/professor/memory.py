"""MemoryEngine: context window ≠ memory.

Six layers, one rule — nothing is deleted, and nothing is resent that a
summary already says:

- L0 active context: the newest non-archived turns of the session, fitted
  to a budget (`budget.fit_transcript`).
- L1 session summary: a `MemorySummary(level="session")` written by
  `ContextCompactor.compact` when the active window crosses a threshold or a
  lesson boundary passes.
- L2 learning memory: what the summaries say was mastered / uncertain /
  misunderstood, folded into the student model as it is written.
- L3 profile: `LearningJourney.profile`, revised from each summary's
  `learner_patterns`, deduplicated.
- L4 knowledge state: `StudentConceptState` (student.py).
- L5 archive: the turns themselves, with `archived_at` set.

Hierarchical: when a journey accumulates `fold_after` session summaries, they
fold into one `module` summary and are superseded (kept, not deleted); the
prompt carries the latest module summary and the unsuperseded session
summaries, so memory stays roughly constant while the transcript grows.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.db.models import (
    LearningJourney,
    MemorySummary,
    TeachingSession,
    TeachingTurn,
    TurnRole,
)
from noema.prompts import load
from noema.providers.base import (
    EmbedRequest,
    Message,
    ProviderError,
    Role,
    StructuredRequest,
    TaskClass,
)
from noema.providers.gateway import AIGateway

from .budget import estimate
from .student import StudentModel

if TYPE_CHECKING:
    from typing import Protocol

    class _Sized(Protocol):
        content: str
        token_estimate: int


log = get_logger(__name__)

__all__ = [
    "MEMORY_SCHEMA",
    "CompactionResult",
    "ContextCompactor",
    "active_turns",
    "merge_profile",
    "render_handoff",
    "render_memory",
    "should_compact",
    "validate_memory",
]

MEMORY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "goal": {"type": "string"},
        "concepts_covered": {"type": "array", "items": {"type": "string"}},
        "mastered": {"type": "array", "items": {"type": "string"}},
        "uncertain": {"type": "array", "items": {"type": "string"}},
        "misconceptions": {"type": "array", "items": {"type": "string"}},
        "examples_that_worked": {"type": "array", "items": {"type": "string"}},
        "questions_answered": {"type": "integer", "minimum": 0},
        "assessment_results": {"type": "array", "items": {"type": "string"}},
        "learner_patterns": {"type": "array", "items": {"type": "string"}},
        "last_taught": {"type": "string"},
        "next_step": {"type": "string"},
    },
    "required": [
        "goal",
        "concepts_covered",
        "mastered",
        "uncertain",
        "misconceptions",
        "examples_that_worked",
        "questions_answered",
        "assessment_results",
        "learner_patterns",
        "last_taught",
        "next_step",
    ],
}

LIST_FIELDS = (
    "concepts_covered",
    "mastered",
    "uncertain",
    "misconceptions",
    "examples_that_worked",
    "assessment_results",
    "learner_patterns",
)


@dataclass(frozen=True, slots=True)
class CompactionResult:
    summary: MemorySummary | None
    archived_turns: int
    tokens_saved: int
    folded: bool = False


async def active_turns(
    db: AsyncSession, session: TeachingSession, *, owner_id: uuid.UUID
) -> list[TeachingTurn]:
    rows = await db.execute(
        select(TeachingTurn)
        .where(
            TeachingTurn.session_id == session.id,
            TeachingTurn.owner_id == owner_id,
            TeachingTurn.archived_at.is_(None),
        )
        .order_by(TeachingTurn.created_at.asc(), TeachingTurn.id.asc())
    )
    return list(rows.scalars())


def should_compact(
    turns: Sequence[_Sized],
    *,
    after_tokens: int,
    after_turns: int,
    keep: int,
    boundary: bool = False,
) -> bool:
    """Compaction is a technical decision: size, or a boundary with enough
    behind it to be worth summarising. Never with fewer turns than `keep`
    would leave anything to summarise."""
    if len(turns) <= keep:
        return False
    tokens = sum(t.token_estimate or estimate(t.content) for t in turns)
    if tokens >= after_tokens or len(turns) >= after_turns:
        return True
    return boundary and len(turns) >= keep * 2


def validate_memory(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("goal", "last_taught", "next_step"):
        out[key] = _text(payload.get(key))[:400]
    for key in LIST_FIELDS:
        raw = payload.get(key)
        items = [
            v.strip()[:200]
            for v in (raw if isinstance(raw, list) else [])
            if isinstance(v, str) and v.strip()
        ]
        out[key] = _dedupe(items)[:8]
    count = payload.get("questions_answered")
    out["questions_answered"] = (
        int(count) if isinstance(count, int | float) and count >= 0 else 0
    )
    return out


class ContextCompactor:
    def __init__(
        self,
        db: AsyncSession,
        *,
        owner_id: uuid.UUID,
        journey: LearningJourney,
        session: TeachingSession,
        gateway: AIGateway,
        model: str | None,
        keep: int = 6,
        fold_after: int = 4,
        embedding_model: str | None = None,
    ) -> None:
        self.db = db
        self.owner_id = owner_id
        self.journey = journey
        self.session = session
        self.gateway = gateway
        self.model = model
        self.keep = keep
        self.fold_after = fold_after
        self.embedding_model = embedding_model

    async def compact(
        self, turns: Sequence[TeachingTurn], *, now: datetime | None = None
    ) -> CompactionResult:
        """Summarise all but the newest `keep` turns, archive them, fold the
        result into the student model and the profile, and fold summaries
        upward when there are enough of them.

        A failed summary call archives nothing: the turns stay in the active
        window and the next turn tries again. Losing context silently would
        be the worse failure.
        """
        now = now or utcnow()
        to_archive = list(turns[: -self.keep]) if self.keep else list(turns)
        if not to_archive:
            return CompactionResult(None, 0, 0)

        transcript = "\n".join(
            f"{'Learner' if t.role is TurnRole.LEARNER else 'Mino'}: {t.content.strip()}"
            for t in to_archive
        )
        previous = await self._latest(level="session", limit=1)
        context_lines = [f"Goal: {self.journey.goal}"]
        if previous:
            context_lines.append(f"Previous summary: {previous[0].summary}")
        prompt = load("professor.compact")
        try:
            payload = await self.gateway.structured(
                StructuredRequest(
                    messages=[
                        Message(role=Role.SYSTEM, content=prompt.body),
                        Message(
                            role=Role.USER,
                            content="\n".join(context_lines)
                            + f"\n\n<TRANSCRIPT>\n{transcript[:24_000]}\n</TRANSCRIPT>",
                        ),
                    ],
                    json_schema=MEMORY_SCHEMA,
                    task=TaskClass.SUMMARIZE,
                    model=self.model,
                    metadata={
                        "feature": "professor.compact",
                        "session_id": str(self.session.id),
                    },
                )
            )
        except ProviderError as exc:
            log.warning("professor.compact_failed", error=str(exc))
            return CompactionResult(None, 0, 0)

        memory = validate_memory(payload)
        tokens_saved = sum(t.token_estimate or estimate(t.content) for t in to_archive)
        turn_from = self.session.compacted_through + 1
        turn_to = self.session.compacted_through + len(to_archive)
        summary = MemorySummary(
            owner_id=self.owner_id,
            journey_id=self.journey.id,
            session_id=self.session.id,
            level="session",
            turn_from=turn_from,
            turn_to=turn_to,
            summary=memory,
            tokens_saved=tokens_saved,
            created_at=now,
        )
        self.db.add(summary)
        await self._embed(summary)
        for turn in to_archive:
            turn.archived_at = now
        self.session.compacted_through = turn_to
        self.journey.profile = merge_profile(self.journey.profile, memory)
        await self.db.flush()

        # L2: what the summary says, into the student model — deduplicated by
        # construction (one row per concept, misconceptions merged by text).
        student = StudentModel(self.db, self.owner_id, self.journey)
        await student.mark_introduced(memory["concepts_covered"], now=now)
        for belief in memory["misconceptions"]:
            name = _concept_of(belief, memory["concepts_covered"]) or (
                self.journey.current_concept or self.journey.subject
            )
            state = await student.ensure(name)
            if belief not in state.misconceptions:
                state.misconceptions = [*state.misconceptions, belief][-4:]
        await self.db.flush()

        folded = await self._fold(now=now)
        log.info(
            "professor.compacted",
            session_id=str(self.session.id),
            archived=len(to_archive),
            tokens_saved=tokens_saved,
            folded=folded,
        )
        return CompactionResult(summary, len(to_archive), tokens_saved, folded=folded)

    async def _embed(self, summary: MemorySummary) -> None:
        """Embed the rendered summary so retrieval can rank by relevance.

        Optional: with no embedding model, or a provider that cannot embed,
        the row stays unembedded and is read newest-first like before.
        """
        if not self.embedding_model:
            return
        try:
            response = await self.gateway.embed(
                EmbedRequest(texts=[_render_summary(summary)], model=self.embedding_model)
            )
        except ProviderError as exc:
            log.warning("professor.memory_embed_failed", error=str(exc))
            return
        if response.vectors:
            summary.embedding = list(response.vectors[0])
            summary.embedding_model = response.model

    async def _latest(self, *, level: str, limit: int) -> list[MemorySummary]:
        rows = await self.db.execute(
            select(MemorySummary)
            .where(
                MemorySummary.journey_id == self.journey.id,
                MemorySummary.owner_id == self.owner_id,
                MemorySummary.level == level,
                MemorySummary.superseded_at.is_(None),
            )
            .order_by(MemorySummary.created_at.desc(), MemorySummary.id.desc())
            .limit(limit)
        )
        return list(rows.scalars())

    async def _fold(self, *, now: datetime) -> bool:
        """Session summaries → one module summary, deterministically (a
        union of the structured fields), so the fold costs no model call."""
        sessions = await self._latest(level="session", limit=self.fold_after + 4)
        if len(sessions) < self.fold_after:
            return False
        sessions.sort(key=lambda s: (s.created_at, s.id))
        merged: dict[str, Any] = {key: [] for key in LIST_FIELDS}
        merged["questions_answered"] = 0
        for s in sessions:
            for key in LIST_FIELDS:
                merged[key] = _dedupe([*merged[key], *s.summary.get(key, [])])[:12]
            merged["questions_answered"] += int(s.summary.get("questions_answered", 0))
        last = sessions[-1].summary
        merged["goal"] = last.get("goal", self.journey.goal)
        merged["last_taught"] = last.get("last_taught", "")
        merged["next_step"] = last.get("next_step", "")
        # Something both mastered and uncertain later is uncertain now.
        merged["mastered"] = [
            m for m in merged["mastered"] if m not in merged["uncertain"]
        ]
        self.db.add(
            MemorySummary(
                owner_id=self.owner_id,
                journey_id=self.journey.id,
                session_id=self.session.id,
                level="module",
                turn_from=sessions[0].turn_from,
                turn_to=sessions[-1].turn_to,
                summary=merged,
                tokens_saved=sum(s.tokens_saved for s in sessions),
                created_at=now,
            )
        )
        for s in sessions:
            s.superseded_at = now
        # Older module summaries fold into the new one the same way, so the
        # chain never grows past two levels the prompt has to read.
        modules = await self._latest(level="module", limit=10)
        for m in modules:
            m.superseded_at = now
        await self.db.flush()
        return True


#: Below this many open session summaries every one rides; above it, the
#: query decides which come first.
RELEVANCE_FROM = 3


async def render_memory(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    journey: LearningJourney,
    budget: int,
    query: str = "",
    gateway: AIGateway | None = None,
    embedding_model: str | None = None,
) -> str:
    """The LEARNING_MEMORY block: the latest module summary, then the open
    session summaries — newest-first, or nearest to `query` when there are
    more than a few and the query can be embedded — within `budget`."""
    rows = await db.execute(
        select(MemorySummary)
        .where(
            MemorySummary.journey_id == journey.id,
            MemorySummary.owner_id == owner_id,
            MemorySummary.superseded_at.is_(None),
        )
        .order_by(MemorySummary.created_at.desc(), MemorySummary.id.desc())
        .limit(12)
    )
    summaries = list(rows.scalars())
    if not summaries:
        return ""
    modules = [s for s in summaries if s.level == "module"]
    sessions = [s for s in summaries if s.level == "session"]
    if len(sessions) > RELEVANCE_FROM and query.strip() and gateway and embedding_model:
        sessions = await _by_relevance(sessions, query, gateway, embedding_model)
    parts: list[str] = []
    used = 0
    for s in modules[:1] + sessions:
        rendered = _render_summary(s)
        cost = estimate(rendered)
        if parts and used + cost > budget:
            break
        parts.append(rendered)
        used += cost
    return "\n\n".join(parts)


async def _by_relevance(
    sessions: list[MemorySummary],
    query: str,
    gateway: AIGateway,
    embedding_model: str,
) -> list[MemorySummary]:
    """Embedded summaries nearest the query first; unembedded ones keep their
    place after them. Any failure returns the input untouched."""
    embedded = [s for s in sessions if s.embedding is not None]
    if not embedded:
        return sessions
    try:
        response = await gateway.embed(EmbedRequest(texts=[query], model=embedding_model))
    except ProviderError as exc:
        log.warning("professor.memory_query_embed_failed", error=str(exc))
        return sessions
    if not response.vectors:
        return sessions
    q = list(response.vectors[0])

    def similarity(vector: list[float]) -> float:
        dot = sum(a * b for a, b in zip(q, vector, strict=False))
        norm = (sum(a * a for a in q) ** 0.5) * (sum(b * b for b in vector) ** 0.5)
        return dot / norm if norm else 0.0

    ranked = sorted(
        embedded, key=lambda s: similarity(list(s.embedding or [])), reverse=True
    )
    rest = [s for s in sessions if s.embedding is None]
    return ranked + rest


def _render_summary(s: MemorySummary) -> str:
    m = s.summary
    label = "Earlier in this course" if s.level == "module" else "Earlier in this lesson"
    lines = [f"{label} (turns {s.turn_from}-{s.turn_to}):"]
    if m.get("concepts_covered"):
        lines.append("- covered: " + ", ".join(m["concepts_covered"]))
    if m.get("mastered"):
        lines.append("- shown understood: " + ", ".join(m["mastered"]))
    if m.get("uncertain"):
        lines.append("- still uncertain: " + ", ".join(m["uncertain"]))
    if m.get("misconceptions"):
        lines.append("- misconceptions seen: " + "; ".join(m["misconceptions"]))
    if m.get("examples_that_worked"):
        lines.append("- what landed: " + "; ".join(m["examples_that_worked"]))
    if m.get("assessment_results"):
        lines.append("- assessments: " + "; ".join(m["assessment_results"]))
    if m.get("last_taught"):
        lines.append(f"- last taught: {m['last_taught']}")
    if m.get("next_step"):
        lines.append(f"- agreed next step: {m['next_step']}")
    return "\n".join(lines)


def render_handoff(
    *,
    journey: LearningJourney,
    plan_block: str,
    knowledge_block: str,
    memory_block: str,
    session_block: str,
) -> str:
    """After a compaction the new context answers the brief's seven questions
    in order: who, what, where, knows, struggles, just taught, next."""
    parts = [
        f"WHO: a {journey.inferred_level} learner; goal in their words: {journey.goal}",
        f"WHAT: {journey.subject} — {journey.objective}",
    ]
    if plan_block:
        parts.append(f"WHERE:\n{plan_block}")
    if knowledge_block:
        parts.append(f"KNOWS / STRUGGLES WITH:\n{knowledge_block}")
    if memory_block:
        parts.append(f"JUST TAUGHT / NEXT:\n{memory_block}")
    if session_block:
        parts.append(session_block)
    return "\n\n".join(parts)


def merge_profile(profile: dict[str, Any], memory: dict[str, Any]) -> dict[str, Any]:
    """L3: fold a summary's learner patterns into the profile, deduplicated,
    newest last, never more than six. A new dict, never an in-place edit."""
    patterns = _dedupe(
        [*profile.get("patterns", []), *memory.get("learner_patterns", [])]
    )
    updated = dict(profile)
    updated["patterns"] = patterns[-6:]
    return updated


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = " ".join(item.lower().split())
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _concept_of(belief: str, concepts: Sequence[str]) -> str | None:
    lowered = belief.lower()
    for concept in concepts:
        if concept.lower() in lowered:
            return concept
    return None


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
