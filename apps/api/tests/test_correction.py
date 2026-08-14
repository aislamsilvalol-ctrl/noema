"""When a misconception counts as corrected.

The spacing rule is the whole idea, and it is pure arithmetic over timestamps, so
it can be tested without a database: two correct confident answers, far enough
apart that the second is evidence of memory rather than of the first still being
in the room.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from noema.study.correction import SPACING, _spaced_enough

NOON = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def test_one_correction_is_not_enough() -> None:
    """A single right answer is a coin landing the right way up."""
    assert _spaced_enough([NOON]) is False


def test_two_in_the_same_sitting_are_not_enough() -> None:
    """That is the last explanation still echoing, not a changed model."""
    assert _spaced_enough([NOON, NOON + timedelta(minutes=4)]) is False


def test_two_a_day_apart_resolve_it() -> None:
    assert _spaced_enough([NOON, NOON + timedelta(days=1)]) is True


def test_the_gap_is_measured_from_the_first_correction() -> None:
    """Three answers in one sitting then one the next day still counts.

    The learner did answer correctly a day later; that the middle attempts were
    bunched up does not make the last one worth less.
    """
    moments = [
        NOON,
        NOON + timedelta(minutes=2),
        NOON + timedelta(minutes=5),
        NOON + timedelta(days=1),
    ]
    assert _spaced_enough(moments) is True


def test_just_under_the_gap_does_not_count() -> None:
    """The boundary is a decision, so it is pinned rather than left to drift."""
    assert _spaced_enough([NOON, NOON + SPACING - timedelta(minutes=1)]) is False
    assert _spaced_enough([NOON, NOON + SPACING]) is True


def test_nothing_at_all_is_not_a_correction() -> None:
    assert _spaced_enough([]) is False
