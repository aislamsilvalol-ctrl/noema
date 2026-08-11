from __future__ import annotations

import pytest

from noema.engines import fsrs
from noema.engines.fsrs import MemoryState, Rating


def test_first_review_stability_matches_initial_weights() -> None:
    for rating in Rating:
        state = fsrs.next_state(None, rating, elapsed_days=0)
        assert state.stability == pytest.approx(fsrs.DEFAULT_WEIGHTS[rating - 1])


def test_first_review_difficulty_decreases_with_better_ratings() -> None:
    difficulties = [
        fsrs.next_state(None, r, elapsed_days=0).difficulty for r in Rating
    ]
    assert difficulties == sorted(difficulties, reverse=True)


def test_retrievability_starts_at_one_and_decays() -> None:
    state = MemoryState(stability=10.0, difficulty=5.0)
    assert fsrs.retrievability(state, 0) == pytest.approx(1.0)

    values = [fsrs.retrievability(state, t) for t in range(0, 60, 5)]
    assert all(a > b for a, b in zip(values, values[1:], strict=False))
    assert 0 < values[-1] < 1


def test_interval_reaches_the_target_retention() -> None:
    state = MemoryState(stability=12.0, difficulty=4.0)
    for target in (0.80, 0.90, 0.97):
        days = fsrs.interval_days(state, target)
        assert fsrs.retrievability(state, days) == pytest.approx(target, abs=1e-9)


def test_higher_target_retention_means_shorter_intervals() -> None:
    state = MemoryState(stability=12.0, difficulty=4.0)
    assert fsrs.interval_days(state, 0.97) < fsrs.interval_days(state, 0.80)


def test_good_reviews_grow_stability_monotonically() -> None:
    state = fsrs.next_state(None, Rating.GOOD, 0)
    previous = state.stability
    for _ in range(10):
        elapsed = fsrs.interval_days(state, 0.9)
        state = fsrs.next_state(state, Rating.GOOD, elapsed)
        assert state.stability > previous
        previous = state.stability


def test_lapse_never_increases_stability() -> None:
    state = MemoryState(stability=40.0, difficulty=6.0)
    lapsed = fsrs.next_state(state, Rating.AGAIN, elapsed_days=30)
    assert lapsed.stability <= state.stability


def test_easy_grows_stability_more_than_hard() -> None:
    state = MemoryState(stability=10.0, difficulty=5.0)
    hard = fsrs.next_state(state, Rating.HARD, 10).stability
    good = fsrs.next_state(state, Rating.GOOD, 10).stability
    easy = fsrs.next_state(state, Rating.EASY, 10).stability
    assert hard < good < easy


def test_difficulty_stays_in_range_under_any_rating_sequence() -> None:
    sequence = [Rating.AGAIN, Rating.AGAIN, Rating.HARD, Rating.EASY, Rating.EASY] * 20
    state = fsrs.next_state(None, Rating.GOOD, 0)
    for rating in sequence:
        state = fsrs.next_state(state, rating, elapsed_days=5)
        assert 1.0 <= state.difficulty <= 10.0
        assert state.stability >= fsrs.MIN_STABILITY


def test_difficulty_reverts_toward_the_easy_anchor() -> None:
    """Without mean reversion a hard card can never recover. Verify it does."""
    state = MemoryState(stability=10.0, difficulty=10.0)
    for _ in range(30):
        state = fsrs.next_state(state, Rating.EASY, 10)
    assert state.difficulty < 3.0


def test_invalid_inputs_are_rejected() -> None:
    with pytest.raises(ValueError):
        MemoryState(stability=0.0, difficulty=5.0)
    with pytest.raises(ValueError):
        MemoryState(stability=1.0, difficulty=11.0)
    with pytest.raises(ValueError):
        fsrs.retrievability(MemoryState(1.0, 5.0), -1)
    with pytest.raises(ValueError):
        fsrs.interval_days(MemoryState(1.0, 5.0), 1.0)
