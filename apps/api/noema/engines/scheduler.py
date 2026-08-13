"""The Adaptive Learning Engine.

A time budget goes in; an ordered, explained plan comes out. This is the feature the
whole product exists to deliver — see ``docs/learning-engine.md``.

Pure functions over frozen dataclasses. No database, no clock, no model calls: the
scheduler is the component most likely to be wrong, and it has to be replayable
against real history to find out.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Final

__all__ = [
    "Candidate",
    "ItemKind",
    "Plan",
    "PlanBlock",
    "SchedulerSettings",
    "build_plan",
    "utility",
]


class ItemKind(StrEnum):
    CARD_REVIEW = "card_review"
    CARD_LEARN = "card_learn"
    QUESTION = "question"
    MISCONCEPTION_DRILL = "misconception_drill"
    PREREQ_REPAIR = "prereq_repair"
    READ = "read"


class BlockKind(StrEnum):
    WARMUP = "warmup"
    REPAIR = "repair"
    PRACTICE = "practice"
    COOLDOWN = "cooldown"


@dataclass(frozen=True, slots=True)
class SchedulerSettings:
    """Every heuristic constant, in one place.

    All of them are hypotheses. `docs/learning-engine.md` §8 describes the replay
    harness that will decide whether they are good ones.
    """

    warmup_share: float = 0.15
    cooldown_share: float = 0.10
    max_consecutive_same_concept: int = 3
    minutes_per_heavy_item: int = 25

    # Pedagogical multipliers (§3).
    overdue_boost: float = 1.4
    misconception_boost: float = 2.0
    blocking_prerequisite_boost: float = 1.8
    recently_studied_penalty: float = 0.4
    interleaving_bonus: float = 1.15
    new_material_penalty: float = 0.3

    #: Beyond this many overdue reviews, new material is actively discouraged. This
    #: is the rule that stops NOEMA letting someone start a shiny new subject while
    #: everything they already know rots.
    overdue_backlog_threshold: int = 40
    recently_studied_hours: float = 4.0


DEFAULTS: Final = SchedulerSettings()


@dataclass(frozen=True, slots=True)
class Candidate:
    """One thing the learner could do next."""

    ref_id: uuid.UUID
    kind: ItemKind
    cost_seconds: float
    #: Expected gain in durable retention, 0 to 1. See §3.
    memory_gain: float
    #: Graph-weighted importance of the concept this touches.
    importance: float = 1.0
    concept_id: uuid.UUID | None = None
    concept_name: str = ""
    retrievability: float = 1.0
    overdue_ratio: float = 0.0  # elapsed / scheduled interval
    is_misconception: bool = False
    blocks_failing_concept: bool = False
    #: The concept this one is holding back, and this one's own mastery. Carried
    #: purely so the plan can say *why* it was rerouted: "X keeps slipping, your
    #: Y is at 38%". A plan that reorders your session without saying what it
    #: noticed is asking to be trusted rather than earning it.
    blocked_concept_name: str = ""
    mastery: float | None = None
    hours_since_studied: float | None = None
    prerequisite_of: frozenset[uuid.UUID] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.cost_seconds <= 0:
            raise ValueError("cost_seconds must be positive")


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    candidate: Candidate
    score: float
    multiplier: float


@dataclass(frozen=True, slots=True)
class PlanBlock:
    kind: BlockKind
    items: list[Candidate]
    #: Required, not decoration. If the engine cannot explain a choice in one
    #: sentence, that is a bug in the engine.
    why: str

    @property
    def seconds(self) -> float:
        return sum(item.cost_seconds for item in self.items)


@dataclass(frozen=True, slots=True)
class Plan:
    blocks: list[PlanBlock]
    rationale: str

    @property
    def items(self) -> list[Candidate]:
        return [item for block in self.blocks for item in block.items]

    @property
    def estimated_seconds(self) -> float:
        return sum(block.seconds for block in self.blocks)


def multiplier(candidate: Candidate, backlog: int, settings: SchedulerSettings) -> float:
    """The pedagogical multiplier: what we believe about learning, in one place."""
    value = 1.0

    if candidate.overdue_ratio > 1.5:
        value *= settings.overdue_boost
    if candidate.is_misconception:
        value *= settings.misconception_boost
    if candidate.blocks_failing_concept:
        value *= settings.blocking_prerequisite_boost

    if (
        candidate.hours_since_studied is not None
        and candidate.hours_since_studied < settings.recently_studied_hours
    ):
        # Spacing, not cramming: seeing the same concept twice in an hour buys much
        # less than seeing it tomorrow.
        value *= settings.recently_studied_penalty

    if (
        candidate.kind in {ItemKind.CARD_LEARN, ItemKind.READ}
        and backlog > settings.overdue_backlog_threshold
    ):
        value *= settings.new_material_penalty

    return value


def utility(
    candidate: Candidate, backlog: int, settings: SchedulerSettings = DEFAULTS
) -> float:
    """Expected learning per second — the quantity selection maximises."""
    return (
        candidate.memory_gain
        * candidate.importance
        * multiplier(candidate, backlog, settings)
        / candidate.cost_seconds
    )


def build_plan(
    candidates: Sequence[Candidate],
    minutes: int,
    *,
    backlog: int = 0,
    settings: SchedulerSettings = DEFAULTS,
) -> Plan:
    """Choose what the next ``minutes`` should contain, and say why."""
    if minutes <= 0:
        raise ValueError("minutes must be positive")
    budget = minutes * 60

    if not candidates:
        return Plan(
            blocks=[], rationale="Nothing is due, and nothing is weak enough to drill."
        )

    scored = sorted(
        (
            ScoredCandidate(
                candidate=c,
                score=utility(c, backlog, settings),
                multiplier=multiplier(c, backlog, settings),
            )
            for c in candidates
        ),
        key=lambda s: -s.score,
    )

    chosen = _fill(scored, budget)
    if not chosen:
        return Plan(blocks=[], rationale="Nothing fits in the time available.")

    # Partition first, order within each block afterwards. Ordering the whole
    # session and then re-partitioning would undo the interleaving, because the
    # blocks regroup by kind.
    blocks = _blocks(chosen, budget, settings)
    return Plan(blocks=blocks, rationale=_rationale(chosen, backlog, settings))


def _fill(scored: Sequence[ScoredCandidate], budget: float) -> list[Candidate]:
    """Greedy by utility.

    Within a constant factor of optimal for this knapsack shape and it runs in
    milliseconds. A proper solver would not earn its dependency.
    """
    chosen: list[Candidate] = []
    spent = 0.0

    for entry in scored:
        if spent + entry.candidate.cost_seconds > budget:
            continue
        chosen.append(entry.candidate)
        spent += entry.candidate.cost_seconds

    return chosen


@dataclass
class _Run:
    """How long the current concept has been running, across block boundaries."""

    concept_id: uuid.UUID | None = None
    length: int = 0

    def observe(self, candidate: Candidate) -> None:
        if candidate.concept_id == self.concept_id:
            self.length += 1
        else:
            self.concept_id = candidate.concept_id
            self.length = 1


def _order(
    chosen: Sequence[Candidate],
    all_selected: Sequence[Candidate],
    settings: SchedulerSettings,
    run: _Run,
) -> list[Candidate]:
    """Apply the ordering constraints: prerequisites first, then interleave."""
    selected_ids = {c.concept_id for c in all_selected if c.concept_id}

    # A prerequisite of something else in this session has to come first — being
    # taught the dependent before the thing it rests on is worse than not being
    # taught it at all.
    def is_prerequisite(candidate: Candidate) -> bool:
        return bool(candidate.prerequisite_of & selected_ids)

    prerequisites = [c for c in chosen if is_prerequisite(c)]
    rest = [c for c in chosen if not is_prerequisite(c)]

    return _interleave(prerequisites, settings, run) + _interleave(rest, settings, run)


def _interleave(
    items: Sequence[Candidate], settings: SchedulerSettings, run: _Run
) -> list[Candidate]:
    """Break up runs of the same concept.

    Blocked practice feels easier and is measurably worse for retention, so the
    ordering deliberately makes the session feel harder than it needs to.

    Best effort, not a guarantee: when everything left in a block shares a concept
    there is nothing to alternate with, and dropping an item to keep the rule would
    cost the learner more than the long run does.
    """
    remaining = list(items)
    ordered: list[Candidate] = []

    while remaining:
        pick = None
        if run.length >= settings.max_consecutive_same_concept:
            pick = next((c for c in remaining if c.concept_id != run.concept_id), None)
        if pick is None:
            # Nothing else to switch to: a long run beats dropping the item.
            pick = remaining[0]

        remaining.remove(pick)
        run.observe(pick)
        ordered.append(pick)

    return ordered


def _blocks(
    ordered: Sequence[Candidate], budget: float, settings: SchedulerSettings
) -> list[PlanBlock]:
    """Split the session into warm-up, repair, practice and cool-down."""
    warmup_budget = budget * settings.warmup_share
    cooldown_budget = budget * settings.cooldown_share
    selected = list(ordered)

    # Repair is claimed first, before anything can file it as filler. A confidently
    # wrong answer is not warm-up material, however cheap it is to answer.
    repair = [c for c in selected if _needs_repair(c)]
    remaining = [c for c in selected if not _needs_repair(c)]

    # Warm-up is due reviews only. Opening a session with something new asks for
    # effort before the learner has any momentum.
    warmup: list[Candidate] = []
    spent = 0.0
    for candidate in list(remaining):
        if candidate.kind is not ItemKind.CARD_REVIEW or spent >= warmup_budget:
            continue
        warmup.append(candidate)
        remaining.remove(candidate)
        spent += candidate.cost_seconds

    # Cool-down: end on things they can actually recall. A motivation decision, made
    # explicitly rather than smuggled in as a streak.
    cooldown: list[Candidate] = []
    spent = 0.0
    for candidate in sorted(remaining, key=lambda c: -c.retrievability):
        if candidate.kind is not ItemKind.CARD_REVIEW or spent >= cooldown_budget:
            continue
        cooldown.append(candidate)
        remaining.remove(candidate)
        spent += candidate.cost_seconds

    practice = remaining

    blocks: list[PlanBlock] = []
    # The run state carries across blocks: the learner experiences one sequence, so
    # four cards on the same concept spanning a block boundary is still the blocked
    # practice interleaving exists to prevent.
    run = _Run()

    def add(kind: BlockKind, items: list[Candidate], why: str) -> None:
        if items:
            blocks.append(PlanBlock(kind, _order(items, selected, settings, run), why))

    add(BlockKind.WARMUP, warmup, "Due reviews, to start on something you know.")
    add(BlockKind.REPAIR, repair, _repair_why(repair))
    add(
        BlockKind.PRACTICE,
        _cap_heavy(practice, budget, settings),
        "Practice on what is weakest.",
    )
    add(
        BlockKind.COOLDOWN,
        cooldown,
        "Cards you should get right, to end on success.",
    )

    return blocks


def _needs_repair(candidate: Candidate) -> bool:
    """Whether an item is repair work rather than practice or warm-up."""
    return (
        candidate.is_misconception
        or candidate.blocks_failing_concept
        or candidate.kind in {ItemKind.PREREQ_REPAIR, ItemKind.MISCONCEPTION_DRILL}
    )


def _cap_heavy(
    items: Sequence[Candidate], budget: float, settings: SchedulerSettings
) -> list[Candidate]:
    """Cognitive load: at most one long item per 25 minutes.

    Three explain-back questions in half an hour is not a study session, it is an
    interrogation, and people stop showing up to those.
    """
    allowed = max(int(budget / 60 / settings.minutes_per_heavy_item), 1)
    heavy_seen = 0
    kept: list[Candidate] = []

    for item in items:
        is_heavy = item.cost_seconds >= 90
        if is_heavy:
            if heavy_seen >= allowed:
                continue
            heavy_seen += 1
        kept.append(item)

    return kept


def _repair_why(repair: Sequence[Candidate]) -> str:
    misconception = next((c for c in repair if c.is_misconception), None)
    if misconception is not None:
        name = misconception.concept_name or "a concept"
        return f"You were confident and wrong about {name}. That is worth fixing first."

    blocking = next((c for c in repair if c.blocks_failing_concept), None)
    if blocking is not None:
        name = blocking.concept_name or "a prerequisite"
        blocked = blocking.blocked_concept_name

        if blocked and blocking.mastery is not None:
            return (
                f"{blocked} keeps slipping. Your {name} mastery is "
                f"{round(blocking.mastery)}%. Fixing that first is the shorter way "
                f"round."
            )
        if blocked:
            return f"{blocked} keeps slipping, and {name} is what it rests on."
        return f"{name} is blocking concepts you keep failing."

    return "Repairing what is holding the rest back."


def _rationale(
    chosen: Sequence[Candidate], backlog: int, settings: SchedulerSettings
) -> str:
    """One sentence explaining the session's shape."""
    misconceptions = [c for c in chosen if c.is_misconception]
    if misconceptions:
        name = misconceptions[0].concept_name or "a concept"
        return f"Starting with {name}, which you got wrong while sure you were right."

    blocking = [c for c in chosen if c.blocks_failing_concept]
    if blocking:
        name = blocking[0].concept_name or "a prerequisite"
        return f"{name} is blocking several concepts, so it comes first."

    if backlog > settings.overdue_backlog_threshold:
        return (
            f"{backlog} reviews are overdue, so this session clears them before "
            "anything new."
        )

    most_important = max(chosen, key=lambda c: c.importance, default=None)
    if most_important is not None and most_important.concept_name:
        return f"Mostly review, weighted towards {most_important.concept_name}."

    return "Due reviews, oldest first."


def with_cost(candidate: Candidate, seconds: float) -> Candidate:
    """Replace an estimated cost with a measured one."""
    return replace(candidate, cost_seconds=seconds)
