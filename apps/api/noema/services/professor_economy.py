"""What teaching costs, read from what was recorded.

Every Professor call writes an `AIUsage` row tagged with its `feature`
(`professor.teach`, `professor.compact`, …), its `session_id` and the tokens
the provider served from its cache. Every compaction writes a
`MemorySummary` with the tokens the archived turns would have cost per turn.
This module turns those rows into the numbers the brief asks an operator to
see: tokens and cost by feature, the cache hit rate, what compaction saved,
cost per lesson and per active learner. Nothing is projected; a number that
cannot be computed from the rows is reported as absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import AIUsage, MemorySummary
from noema.services.admin_intelligence import month_start

__all__ = ["EconomySnapshot", "FeatureUsage", "ProfessorEconomyService"]


@dataclass(frozen=True, slots=True)
class FeatureUsage:
    feature: str
    calls: int
    prompt_tokens: int
    cached_tokens: int
    completion_tokens: int
    cost_cents: float


@dataclass(frozen=True, slots=True)
class EconomySnapshot:
    #: This calendar month, professor features only.
    features: list[FeatureUsage]
    calls: int
    prompt_tokens: int
    cached_tokens: int
    completion_tokens: int
    cost_cents: float
    #: cached ÷ prompt over the teaching calls, or None when there were none.
    cache_hit_rate: float | None
    #: Tokens that compaction removed from every later turn's prompt.
    compaction_tokens_saved: int
    compactions: int
    #: Distinct sessions taught this month, and what each cost on average.
    lessons: int
    cost_per_lesson_cents: float | None
    #: Distinct learners with a professor call this month, and the same.
    active_learners: int
    cost_per_learner_cents: float | None


class ProfessorEconomyService:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def snapshot(self, *, now: datetime | None = None) -> EconomySnapshot:
        month = month_start(now)
        professor = AIUsage.feature.like("professor.%")

        rows = (
            await self.db.execute(
                select(
                    AIUsage.feature,
                    func.count(AIUsage.id),
                    func.coalesce(func.sum(AIUsage.prompt_tokens), 0),
                    func.coalesce(func.sum(AIUsage.cached_tokens), 0),
                    func.coalesce(func.sum(AIUsage.completion_tokens), 0),
                    func.coalesce(func.sum(AIUsage.cost_cents), 0.0),
                )
                .where(AIUsage.created_at >= month, professor)
                .group_by(AIUsage.feature)
                .order_by(func.sum(AIUsage.cost_cents).desc())
            )
        ).all()
        features = [
            FeatureUsage(
                feature=str(feature),
                calls=int(calls),
                prompt_tokens=int(prompt),
                cached_tokens=int(cached),
                completion_tokens=int(completion),
                cost_cents=float(cost),
            )
            for feature, calls, prompt, cached, completion, cost in rows
        ]
        calls = sum(f.calls for f in features)
        prompt = sum(f.prompt_tokens for f in features)
        cached = sum(f.cached_tokens for f in features)
        completion = sum(f.completion_tokens for f in features)
        cost = sum(f.cost_cents for f in features)

        # The cache rate is meaningful only for the teaching calls, whose
        # system block is the cacheable prefix; structured calls report no
        # usage today and would dilute the ratio with zeros.
        teaching = [
            f for f in features if f.feature == "professor.teach" or f.prompt_tokens
        ]
        teaching_prompt = sum(f.prompt_tokens for f in teaching)
        teaching_cached = sum(f.cached_tokens for f in teaching)
        cache_hit_rate = teaching_cached / teaching_prompt if teaching_prompt else None

        compactions, tokens_saved = (
            await self.db.execute(
                select(
                    func.count(MemorySummary.id),
                    func.coalesce(func.sum(MemorySummary.tokens_saved), 0),
                ).where(
                    MemorySummary.created_at >= month, MemorySummary.level == "session"
                )
            )
        ).one()

        lessons = await self.db.scalar(
            select(func.count(func.distinct(AIUsage.session_id))).where(
                AIUsage.created_at >= month, professor, AIUsage.session_id.is_not(None)
            )
        )
        learners = await self.db.scalar(
            select(func.count(func.distinct(AIUsage.owner_id))).where(
                AIUsage.created_at >= month, professor
            )
        )
        lessons = int(lessons or 0)
        learners = int(learners or 0)
        return EconomySnapshot(
            features=features,
            calls=calls,
            prompt_tokens=prompt,
            cached_tokens=cached,
            completion_tokens=completion,
            cost_cents=cost,
            cache_hit_rate=cache_hit_rate,
            compaction_tokens_saved=int(tokens_saved),
            compactions=int(compactions),
            lessons=lessons,
            cost_per_lesson_cents=cost / lessons if lessons else None,
            active_learners=learners,
            cost_per_learner_cents=cost / learners if learners else None,
        )
