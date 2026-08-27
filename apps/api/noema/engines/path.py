"""Turning a goal with a date on it into an order and an honest verdict.

Two jobs. The order: prerequisites before the things that rest on them, and within
that, whatever is furthest from the target first. The verdict: whether the deadline
is actually reachable at the pace the learner has, and if not, what would make it —
more minutes a day, or more days.

The second job is the one most goal features skip. A plan that cheerfully accepts
"learn all of pharmacology by Friday" is not planning, it is agreeing; and the
learner finds out on Friday. Saying "at 20 minutes a day you get about two thirds
of the way — you need 35, or another nine days" is the only version of this feature
worth having.

Pure: no database, no clock, no IO. Days and minutes come in as numbers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

__all__ = ["Feasibility", "Milestone", "Target", "plan_path"]

#: Minutes of study to move one concept one point of mastery, at the middle of the
#: curve. Calibrated from `docs/learning-engine.md` §7 rather than guessed: roughly
#: three minutes of deliberate work per point, and the last points cost more than
#: the first, which `_effort` accounts for.
MINUTES_PER_POINT = 3.0

#: Below this, a concept is not "nearly there" — it needs teaching, not topping up.
FOUNDATION = 40.0


@dataclass(frozen=True, slots=True)
class Target:
    concept_id: uuid.UUID
    name: str
    mastery: float
    #: Concepts that must come first. Only those inside the goal matter; a
    #: prerequisite outside it is someone else's problem today.
    prerequisites: frozenset[uuid.UUID] = frozenset()


@dataclass(frozen=True, slots=True)
class Milestone:
    concept_id: uuid.UUID
    name: str
    from_mastery: float
    to_mastery: float
    estimated_minutes: float
    #: Which day of the plan this lands on, counting from 1.
    day: int


@dataclass(frozen=True, slots=True)
class Feasibility:
    reachable: bool
    #: Mastery the learner would actually average by the deadline at this pace.
    projected_mastery: float
    required_minutes_per_day: float
    #: Days needed at the pace they said they have.
    required_days: int
    summary: str


@dataclass(frozen=True, slots=True)
class Path:
    milestones: list[Milestone]
    feasibility: Feasibility


def plan_path(
    targets: list[Target],
    *,
    target_mastery: float,
    days: int,
    minutes_per_day: float,
    overdue: bool = False,
) -> Path:
    """Order the work and say whether the date holds.

    ``days`` is already floored to at least 1 by the caller, so there is always a
    day to schedule work into — but that floor would otherwise make a goal whose
    deadline has already passed look identical to one due tomorrow: a handful of
    concepts left would fit "today" and come back ``reachable``. ``overdue`` is how
    the caller says the date itself, not just the arithmetic, has already failed.
    """
    ordered = _in_teaching_order(targets)
    work = [t for t in ordered if t.mastery < target_mastery]

    total = sum(_effort(t.mastery, target_mastery) for t in work)
    capacity = max(days, 0) * max(minutes_per_day, 0.0)

    milestones = _schedule(work, target_mastery, minutes_per_day, days)
    return Path(
        milestones=milestones,
        feasibility=_verdict(
            work,
            targets,
            target_mastery,
            total,
            capacity,
            days,
            minutes_per_day,
            overdue=overdue,
        ),
    )


def _in_teaching_order(targets: list[Target]) -> list[Target]:
    """Prerequisites first; weakest first among things that are equally ready.

    A cycle in the graph does not raise here. The DAG is validated when edges are
    written; if a bad one ever survives that, a goal should still produce a usable
    order rather than an exception the learner cannot act on.
    """
    inside = {t.concept_id for t in targets}
    remaining = {t.concept_id: t for t in targets}
    done: set[uuid.UUID] = set()
    ordered: list[Target] = []

    while remaining:
        ready = [t for t in remaining.values() if not (t.prerequisites & inside) - done]
        if not ready:
            # Cycle, or a prerequisite that is itself unreachable. Take the weakest
            # and keep going: an imperfect order beats no plan.
            ready = [min(remaining.values(), key=lambda t: t.mastery)]

        ready.sort(key=lambda t: (t.mastery, t.name))
        for target in ready:
            ordered.append(target)
            done.add(target.concept_id)
            del remaining[target.concept_id]

    return ordered


def _effort(current: float, target: float) -> float:
    """Minutes to move one concept from ``current`` to ``target``.

    The last points cost more than the first — going 80 to 90 is slower than 30 to
    40, because the easy wins are gone — so the distance is weighted rather than
    linear. Concepts below the foundation line carry an extra fixed cost: they need
    to be learned before they can be practised.
    """
    if current >= target:
        return 0.0

    distance = target - current
    difficulty = 1.0 + max(target - 60.0, 0.0) / 40.0
    teaching = MINUTES_PER_POINT * 4 if current < FOUNDATION else 0.0
    return distance * MINUTES_PER_POINT * difficulty + teaching


def _schedule(
    work: list[Target], target_mastery: float, minutes_per_day: float, days: int
) -> list[Milestone]:
    """Lay the ordered work across the days available.

    Work is not split across days. A concept half-learned at the end of Tuesday is
    not a milestone anyone can act on, and the estimate is not precise enough to
    pretend otherwise.
    """
    milestones: list[Milestone] = []
    day = 1
    spent = 0.0

    for target in work:
        minutes = _effort(target.mastery, target_mastery)
        if spent > 0 and spent + minutes > minutes_per_day and day < max(days, 1):
            day += 1
            spent = 0.0

        milestones.append(
            Milestone(
                concept_id=target.concept_id,
                name=target.name,
                from_mastery=target.mastery,
                to_mastery=target_mastery,
                estimated_minutes=round(minutes, 1),
                day=day,
            )
        )
        spent += minutes

    return milestones


def _verdict(
    work: list[Target],
    everything: list[Target],
    target_mastery: float,
    total_minutes: float,
    capacity: float,
    days: int,
    minutes_per_day: float,
    *,
    overdue: bool = False,
) -> Feasibility:
    if not work:
        return Feasibility(
            reachable=True,
            projected_mastery=_average(everything, everything, target_mastery),
            required_minutes_per_day=0.0,
            required_days=0,
            summary="You are already there. Nothing in this goal is below the target.",
        )

    required_per_day = total_minutes / max(days, 1)
    required_days = int(-(-total_minutes // max(minutes_per_day, 1.0)))

    if overdue:
        # The deadline itself is gone, not just the arithmetic around it — capacity
        # says nothing true about a day that already happened.
        return Feasibility(
            reachable=False,
            projected_mastery=round(_average([], everything, target_mastery), 1),
            required_minutes_per_day=round(required_per_day, 1),
            required_days=required_days,
            summary=(
                f"This deadline has passed. {len(work)} concept"
                f"{'s' if len(work) != 1 else ''} still below target — push the date "
                "back or drop them from the goal."
            ),
        )

    if capacity >= total_minutes:
        return Feasibility(
            reachable=True,
            projected_mastery=target_mastery,
            required_minutes_per_day=round(required_per_day, 1),
            required_days=required_days,
            summary=(
                f"{len(work)} concepts to raise, about "
                f"{round(total_minutes / 60, 1)} hours of work. At "
                f"{round(minutes_per_day)} minutes a day that fits in {required_days} "
                f"of your {days} days."
            ),
        )

    # Which concepts the capacity actually covers, in the order they would be done.
    covered: list[Target] = []
    budget = capacity
    for target in work:
        cost = _effort(target.mastery, target_mastery)
        if cost > budget:
            break
        budget -= cost
        covered.append(target)

    return Feasibility(
        reachable=False,
        projected_mastery=round(_average(covered, everything, target_mastery), 1),
        required_minutes_per_day=round(required_per_day, 1),
        required_days=required_days,
        summary=(
            f"Not at this pace. {len(work)} concepts need about "
            f"{round(total_minutes / 60, 1)} hours; {days} days at "
            f"{round(minutes_per_day)} minutes gives you "
            f"{round(capacity / 60, 1)}. You would reach {len(covered)} of them. "
            f"Either {round(required_per_day)} minutes a day, or {required_days} "
            f"days at the pace you have."
        ),
    )


def _average(
    reached: list[Target], everything: list[Target], target_mastery: float
) -> float:
    """Mastery across the whole goal if only ``reached`` gets raised."""
    if not everything:
        return 0.0

    lifted = {t.concept_id for t in reached}
    return sum(
        target_mastery if t.concept_id in lifted else t.mastery for t in everything
    ) / len(everything)
