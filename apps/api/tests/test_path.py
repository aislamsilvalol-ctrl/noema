"""Planning a goal with a date on it.

The tests are about the two things that make this useful rather than decorative:
the order respects what has to be learned first, and the verdict tells the truth
when the deadline does not fit.
"""

from __future__ import annotations

import uuid

from noema.engines.path import Target, plan_path

A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def target(
    concept_id: uuid.UUID,
    name: str,
    mastery: float,
    prerequisites: frozenset[uuid.UUID] = frozenset(),
) -> Target:
    return Target(
        concept_id=concept_id, name=name, mastery=mastery, prerequisites=prerequisites
    )


def test_prerequisites_come_first_even_when_stronger() -> None:
    """Order is not "weakest first" — it is "what you can actually learn next"."""
    path = plan_path(
        [
            target(B, "Backpropagation", 20, prerequisites=frozenset({A})),
            target(A, "Chain rule", 55),
        ],
        target_mastery=80,
        days=30,
        minutes_per_day=30,
    )

    assert [m.name for m in path.milestones] == ["Chain rule", "Backpropagation"]


def test_the_weakest_goes_first_among_equals() -> None:
    """With nothing to order them, start where the ground is worst."""
    path = plan_path(
        [target(A, "Alpha", 70), target(B, "Beta", 30), target(C, "Gamma", 50)],
        target_mastery=80,
        days=30,
        minutes_per_day=30,
    )

    assert [m.name for m in path.milestones] == ["Beta", "Gamma", "Alpha"]


def test_a_cycle_still_produces_a_plan() -> None:
    """Bad edges should not hand the learner an exception instead of a plan."""
    path = plan_path(
        [
            target(A, "Alpha", 30, prerequisites=frozenset({B})),
            target(B, "Beta", 40, prerequisites=frozenset({A})),
        ],
        target_mastery=80,
        days=10,
        minutes_per_day=30,
    )

    assert len(path.milestones) == 2


def test_concepts_already_at_target_are_left_alone() -> None:
    path = plan_path(
        [target(A, "Alpha", 85), target(B, "Beta", 30)],
        target_mastery=80,
        days=30,
        minutes_per_day=30,
    )

    assert [m.name for m in path.milestones] == ["Beta"]
    assert path.feasibility.reachable is True


def test_an_impossible_deadline_is_said_out_loud() -> None:
    """The whole point. A plan that agrees to anything is not planning.

    The learner finds out on the deadline either way; the only question is
    whether they find out from us first.
    """
    path = plan_path(
        [target(uuid.uuid4(), f"Concept {i}", 10) for i in range(40)],
        target_mastery=80,
        days=3,
        minutes_per_day=20,
    )

    assert path.feasibility.reachable is False
    assert path.feasibility.projected_mastery < 80
    assert path.feasibility.required_minutes_per_day > 20
    assert path.feasibility.required_days > 3
    # And it says what would fix it, in both currencies.
    assert "minutes a day" in path.feasibility.summary
    assert "days at the pace you have" in path.feasibility.summary


def test_a_reachable_goal_says_so_with_the_numbers() -> None:
    path = plan_path(
        [target(A, "Alpha", 70), target(B, "Beta", 65)],
        target_mastery=80,
        days=30,
        minutes_per_day=30,
    )

    assert path.feasibility.reachable is True
    assert path.feasibility.projected_mastery == 80
    assert "hours of work" in path.feasibility.summary


def test_the_last_points_cost_more_than_the_first() -> None:
    """Going 70→80 is slower than 20→30, and the estimate should know that."""
    low = plan_path(
        [target(A, "Alpha", 20)], target_mastery=30, days=30, minutes_per_day=30
    ).milestones[0]
    high = plan_path(
        [target(A, "Alpha", 70)], target_mastery=80, days=30, minutes_per_day=30
    ).milestones[0]

    assert high.estimated_minutes > 0
    # Same ten points of distance, more expensive at the top — before the extra
    # teaching cost that only the low one carries.
    assert high.estimated_minutes / 10 > (low.estimated_minutes - 12) / 10


def test_a_goal_already_met_is_not_busywork() -> None:
    path = plan_path(
        [target(A, "Alpha", 90)], target_mastery=80, days=7, minutes_per_day=30
    )

    assert path.milestones == []
    assert path.feasibility.reachable is True
    assert "already there" in path.feasibility.summary


def test_work_is_spread_across_days_not_split_within_them() -> None:
    """A concept half-learned on Tuesday is not a milestone anyone can act on."""
    path = plan_path(
        [target(uuid.uuid4(), f"Concept {i}", 60) for i in range(6)],
        target_mastery=80,
        days=6,
        minutes_per_day=30,
    )

    days = [m.day for m in path.milestones]
    assert days == sorted(days), "the plan jumps backwards through the calendar"
    assert max(days) > 1, "everything was piled onto one day"


# ── Counting the days left ───────────────────────────────────────────────────


def test_a_goal_due_today_still_has_a_day() -> None:
    """There are hours left in today.

    Counting zero would divide the work by nothing and report every goal as
    impossible on the morning it is due — which is both wrong and the least
    useful moment to be told so.
    """
    from datetime import date

    from noema.study.goals import days_remaining

    assert days_remaining(date(2026, 3, 1), today=date(2026, 3, 1)) == 1
    assert days_remaining(date(2026, 3, 8), today=date(2026, 3, 1)) == 8


def test_a_goal_already_past_does_not_go_negative() -> None:
    """An overdue goal still needs a plan; dividing by -3 does not produce one."""
    from datetime import date

    from noema.study.goals import days_remaining

    assert days_remaining(date(2026, 2, 25), today=date(2026, 3, 1)) == 1
