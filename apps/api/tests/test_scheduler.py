"""The Adaptive Learning Engine.

Every constant here is a hypothesis about how people learn. These tests pin the
*behaviour* those hypotheses are supposed to produce, so a future change to the
numbers has to admit what it is changing.
"""

from __future__ import annotations

import uuid

import pytest

from noema.engines.scheduler import (
    BlockKind,
    Candidate,
    ItemKind,
    SchedulerSettings,
    build_plan,
    utility,
)

CHAIN_RULE = uuid.uuid4()
BACKPROP = uuid.uuid4()


def card(
    *,
    cost: float = 8.0,
    gain: float = 0.25,
    importance: float = 1.0,
    kind: ItemKind = ItemKind.CARD_REVIEW,
    concept: uuid.UUID | None = None,
    name: str = "",
    retrievability: float = 0.9,
    overdue: float = 0.0,
    misconception: bool = False,
    blocking: bool = False,
    hours_since: float | None = None,
    prerequisite_of: frozenset[uuid.UUID] = frozenset(),
) -> Candidate:
    return Candidate(
        ref_id=uuid.uuid4(),
        kind=kind,
        cost_seconds=cost,
        memory_gain=gain,
        importance=importance,
        concept_id=concept,
        concept_name=name,
        retrievability=retrievability,
        overdue_ratio=overdue,
        is_misconception=misconception,
        blocks_failing_concept=blocking,
        hours_since_studied=hours_since,
        prerequisite_of=prerequisite_of,
    )


# ── Utility ───────────────────────────────────────────────────────────────────


def test_utility_is_learning_per_second() -> None:
    cheap = card(cost=5.0, gain=0.2)
    expensive = card(cost=50.0, gain=0.2)
    assert utility(cheap, 0) > utility(expensive, 0)


def test_importance_raises_utility() -> None:
    """A shaky prerequisite with eight things stacked on it outranks an isolated
    concept at the same score."""
    isolated = card(importance=1.0)
    foundational = card(importance=4.0)
    assert utility(foundational, 0) > utility(isolated, 0)


def test_a_misconception_outranks_an_ordinary_item() -> None:
    ordinary = card()
    confidently_wrong = card(misconception=True)
    assert utility(confidently_wrong, 0) > utility(ordinary, 0)


def test_a_blocking_prerequisite_outranks_an_ordinary_item() -> None:
    assert utility(card(blocking=True), 0) > utility(card(), 0)


def test_an_overdue_card_outranks_one_barely_due() -> None:
    assert utility(card(overdue=3.0), 0) > utility(card(overdue=1.0), 0)


def test_something_studied_an_hour_ago_is_deprioritised() -> None:
    """Spacing, not cramming."""
    assert utility(card(hours_since=1.0), 0) < utility(card(hours_since=48.0), 0)


def test_new_material_is_suppressed_while_reviews_rot() -> None:
    """The rule that keeps NOEMA honest: no starting a shiny new subject while
    forty reviews are overdue."""
    new = card(kind=ItemKind.CARD_LEARN)

    assert utility(new, backlog=0) > utility(new, backlog=100)
    # Existing reviews are unaffected by the backlog — they *are* the backlog.
    review = card(kind=ItemKind.CARD_REVIEW)
    assert utility(review, backlog=0) == utility(review, backlog=100)


# ── Selection ─────────────────────────────────────────────────────────────────


def test_the_plan_fits_the_time_budget() -> None:
    plan = build_plan([card(cost=60.0) for _ in range(100)], minutes=10)
    assert plan.estimated_seconds <= 10 * 60


def test_higher_utility_items_are_chosen_first() -> None:
    important = card(importance=10.0, name="Chain Rule")
    filler = [card(importance=0.1) for _ in range(50)]

    plan = build_plan([*filler, important], minutes=2)

    assert important in plan.items


def test_an_empty_candidate_set_says_so_rather_than_returning_an_empty_plan() -> None:
    plan = build_plan([], minutes=30)
    assert plan.blocks == []
    assert "Nothing is due" in plan.rationale


def test_items_that_cannot_fit_are_skipped_not_truncated() -> None:
    plan = build_plan([card(cost=3600.0)], minutes=5)
    assert plan.items == []
    assert "Nothing fits" in plan.rationale


def test_a_zero_length_session_is_refused() -> None:
    with pytest.raises(ValueError):
        build_plan([card()], minutes=0)


# ── Shape ─────────────────────────────────────────────────────────────────────


def test_a_session_starts_with_due_reviews() -> None:
    """Opening with new material asks for effort before there is any momentum."""
    candidates = [card() for _ in range(20)] + [
        card(kind=ItemKind.CARD_LEARN) for _ in range(20)
    ]
    plan = build_plan(candidates, minutes=10)

    assert plan.blocks[0].kind is BlockKind.WARMUP
    assert all(item.kind is ItemKind.CARD_REVIEW for item in plan.blocks[0].items)


def test_a_session_ends_on_something_recallable() -> None:
    """A motivation decision, made explicitly rather than smuggled in as a streak."""
    candidates = [card(retrievability=r / 10) for r in range(1, 11)] * 5
    plan = build_plan(candidates, minutes=10)

    cooldown = [b for b in plan.blocks if b.kind is BlockKind.COOLDOWN]
    assert cooldown
    assert min(i.retrievability for i in cooldown[0].items) >= 0.5


def test_misconceptions_land_in_a_repair_block_that_names_them() -> None:
    plan = build_plan(
        [
            card(misconception=True, name="Backpropagation", concept=BACKPROP),
            *[card() for _ in range(10)],
        ],
        minutes=10,
    )

    repair = next(b for b in plan.blocks if b.kind is BlockKind.REPAIR)
    assert "Backpropagation" in repair.why
    assert "confident" in repair.why.lower()


def test_every_block_explains_itself() -> None:
    """If the engine cannot explain a choice in one sentence, that is a bug."""
    plan = build_plan(
        [
            card(),
            card(kind=ItemKind.QUESTION, cost=45.0),
            card(misconception=True, name="X"),
        ],
        minutes=15,
    )

    assert plan.rationale
    for block in plan.blocks:
        assert block.why, f"{block.kind} has no explanation"


def test_prerequisites_are_ordered_before_what_depends_on_them() -> None:
    prerequisite = card(
        concept=CHAIN_RULE, name="Chain Rule", prerequisite_of=frozenset({BACKPROP})
    )
    dependent = card(concept=BACKPROP, name="Backpropagation")

    plan = build_plan([dependent, prerequisite], minutes=10)
    items = plan.items

    assert items.index(prerequisite) < items.index(dependent)


def test_the_same_concept_does_not_run_while_an_alternative_exists() -> None:
    """Blocked practice feels easier and is measurably worse, so the ordering makes
    the session feel harder than it needs to.

    Best effort by design: a run may exceed the limit only when everything left in
    that block shares the concept, because dropping an item to keep the rule would
    cost the learner more than the long run does.
    """
    settings = SchedulerSettings(max_consecutive_same_concept=3)
    one, two = uuid.uuid4(), uuid.uuid4()
    candidates = [card(concept=one) for _ in range(6)] + [
        card(concept=two) for _ in range(6)
    ]

    plan = build_plan(candidates, minutes=10, settings=settings)

    run = 0
    previous = None
    for block in plan.blocks:
        for position, item in enumerate(block.items):
            run = run + 1 if item.concept_id == previous else 1
            previous = item.concept_id
            if run > settings.max_consecutive_same_concept:
                later = block.items[position + 1 :]
                assert all(i.concept_id == item.concept_id for i in later), (
                    "the run was extended while a different concept was available"
                )


def test_interleaving_happens_when_both_concepts_are_available() -> None:
    settings = SchedulerSettings(max_consecutive_same_concept=2)
    one, two = uuid.uuid4(), uuid.uuid4()
    candidates = [card(concept=one) for _ in range(4)] + [
        card(concept=two) for _ in range(4)
    ]

    plan = build_plan(candidates, minutes=30, settings=settings)
    sequence = [i.concept_id for i in plan.items]

    # Without interleaving this would be four of one followed by four of the other.
    assert sequence != [one] * 4 + [two] * 4


def test_long_items_are_capped_per_session() -> None:
    """Three explain-back questions in half an hour is an interrogation, and people
    stop showing up to those."""
    heavy = [card(kind=ItemKind.QUESTION, cost=180.0, gain=0.9) for _ in range(10)]

    plan = build_plan(heavy, minutes=25)

    assert sum(1 for i in plan.items if i.cost_seconds >= 90) <= 1


def test_a_backlog_is_named_in_the_rationale() -> None:
    plan = build_plan([card() for _ in range(30)], minutes=10, backlog=120)
    assert "120" in plan.rationale


def test_a_plan_never_contains_an_item_twice() -> None:
    plan = build_plan([card() for _ in range(40)], minutes=20)
    ids = [item.ref_id for item in plan.items]
    assert len(ids) == len(set(ids))


def test_a_free_item_is_rejected_rather_than_dividing_by_zero() -> None:
    with pytest.raises(ValueError):
        card(cost=0.0)


# ── Saying why the session was rerouted ──────────────────────────────────────


def test_a_blocked_concept_is_named_with_the_number() -> None:
    """The plan should say what it noticed, not assert that it noticed something.

    `docs/learning-engine.md` §5 specifies this sentence, and a reordered session
    that will not explain itself is asking to be trusted rather than earning it.
    """
    from noema.engines.scheduler import _repair_why

    blocking = Candidate(
        ref_id=uuid.uuid4(),
        kind=ItemKind.CARD_REVIEW,
        cost_seconds=40,
        memory_gain=0.4,
        concept_id=uuid.uuid4(),
        concept_name="chain rule",
        blocks_failing_concept=True,
        blocked_concept_name="Backpropagation",
        mastery=38.2,
    )

    why = _repair_why([blocking])

    assert "Backpropagation" in why, "the failing concept was not named"
    assert "chain rule" in why, "the prerequisite was not named"
    assert "38%" in why, "the mastery number was not shown"


def test_without_a_number_it_still_says_what_is_blocked() -> None:
    """A concept with no mastery row yet is common; silence is not the answer."""
    from noema.engines.scheduler import _repair_why

    blocking = Candidate(
        ref_id=uuid.uuid4(),
        kind=ItemKind.CARD_REVIEW,
        cost_seconds=40,
        memory_gain=0.4,
        concept_id=uuid.uuid4(),
        concept_name="chain rule",
        blocks_failing_concept=True,
        blocked_concept_name="Backpropagation",
    )

    why = _repair_why([blocking])

    assert "Backpropagation" in why and "chain rule" in why
    assert "%" not in why, "a percentage was shown for a concept with no score"


def test_a_misconception_still_comes_first() -> None:
    """Being confidently wrong outranks being blocked."""
    from noema.engines.scheduler import _repair_why

    common = {
        "kind": ItemKind.CARD_REVIEW,
        "cost_seconds": 40,
        "memory_gain": 0.4,
        "concept_id": uuid.uuid4(),
    }
    blocked = Candidate(
        ref_id=uuid.uuid4(),
        concept_name="chain rule",
        blocks_failing_concept=True,
        blocked_concept_name="Backpropagation",
        mastery=38.0,
        **common,  # type: ignore[arg-type]
    )
    wrong = Candidate(
        ref_id=uuid.uuid4(),
        concept_name="pre-load",
        is_misconception=True,
        **common,  # type: ignore[arg-type]
    )

    assert "pre-load" in _repair_why([blocked, wrong])
