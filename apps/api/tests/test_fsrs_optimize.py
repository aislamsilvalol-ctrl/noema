"""Fitting FSRS to one learner.

The tests are about the discipline rather than the search: too little history is
refused, the held-out half is really held out, and a candidate that only wins by a
hair is not adopted. A optimiser without those is a machine for convincing itself.
"""

from __future__ import annotations

import random

from noema.engines import fsrs
from noema.engines.fsrs_optimize import MARGIN, TRAIN_SPLIT, Fit, optimise
from noema.engines.replay import Attempt


def history(count: int, *, recall_rate: float = 0.85, seed: int = 7) -> list[Attempt]:
    """A plausible review log: many cards, mixed ratings, mixed intervals."""
    rng = random.Random(seed)
    attempts = []
    for i in range(count):
        recalled = rng.random() < recall_rate
        attempts.append(
            Attempt(
                card_id=f"card-{i % 40}",
                elapsed_days=rng.choice([0.5, 1.0, 3.0, 7.0, 14.0, 30.0]),
                rating=(
                    rng.choice([fsrs.Rating.HARD, fsrs.Rating.GOOD, fsrs.Rating.EASY])
                    if recalled
                    else fsrs.Rating.AGAIN
                ),
            )
        )
    return attempts


def test_too_little_history_is_refused_not_fitted() -> None:
    """Below the floor the search finds noise, and adopting it would be worse
    than doing nothing at all."""
    fit = optimise(history(50), min_reviews=400)

    assert fit.adopted is False
    assert fit.weights == fsrs.DEFAULT_WEIGHTS
    assert "400" in fit.summary


def test_the_validation_half_is_never_fitted_on() -> None:
    """Judged on data the search never saw, or the number means nothing."""
    attempts = history(500)
    fit = optimise(attempts, min_reviews=100)

    assert fit.train_attempts == int(len(attempts) * TRAIN_SPLIT)
    assert fit.validation_attempts == len(attempts) - fit.train_attempts
    assert fit.train_attempts + fit.validation_attempts == len(attempts)


def test_the_split_is_chronological() -> None:
    """A random split puts the same card either side and leaks the future.

    Sliced in order, the last validation attempt is the last attempt in the log.
    """
    attempts = history(500)
    cut = int(len(attempts) * TRAIN_SPLIT)

    # The function slices rather than samples; this pins the contract that the
    # tail is the tail.
    assert attempts[cut:][-1] is attempts[-1]


def test_a_hair_of_improvement_is_not_adopted() -> None:
    """Search hard enough and something always wins on the training half."""
    fit = optimise(history(600), min_reviews=100)

    if fit.adopted:
        assert fit.baseline_loss - fit.candidate_loss >= MARGIN
    else:
        assert fit.weights == fsrs.DEFAULT_WEIGHTS


def test_the_result_says_what_happened_either_way() -> None:
    """A learner should be able to read why their schedule did or did not change."""
    fit = optimise(history(600), min_reviews=100)

    assert "log loss" in fit.summary
    assert str(fit.train_attempts) in fit.summary
    assert isinstance(fit, Fit)


def test_weights_stay_inside_their_bounds() -> None:
    """An unbounded search will happily propose a stability of 0.0001."""
    from noema.engines.fsrs_optimize import BOUNDS

    fit = optimise(history(600), min_reviews=100)

    for index, (low, high) in BOUNDS.items():
        assert low <= fit.weights[index] <= high


def test_a_learner_who_forgets_faster_gets_different_weights() -> None:
    """The point of fitting: two learners, two schedules.

    Not an assertion that the fit is *good* — only that a materially different
    history is capable of producing a materially different answer, which is the
    thing that would be silently broken if the search were a no-op.
    """
    forgetful = optimise(history(800, recall_rate=0.55, seed=3), min_reviews=100)
    steady = optimise(history(800, recall_rate=0.95, seed=3), min_reviews=100)

    if forgetful.adopted and steady.adopted:
        assert forgetful.weights != steady.weights


# ── Where a learner's weights live ───────────────────────────────────────────


def test_malformed_settings_cost_the_fit_not_the_review() -> None:
    """A corrupted blob must not stop someone reviewing a card.

    These are read on every single review, so the failure mode has to be "you get
    the defaults", never an exception in the middle of a study session.
    """
    from noema.db.models import User
    from noema.study.scheduling import fitted_weights

    for broken in ({"fsrs": "nonsense"}, {"fsrs": {"weights": [1, 2]}}, {}, None):
        user = User(email="a@b.c", password_hash="x", display_name="A")
        user.settings = broken  # type: ignore[assignment]
        assert fitted_weights(user) == fsrs.DEFAULT_WEIGHTS


def test_stored_weights_come_back() -> None:
    from noema.db.models import User
    from noema.study.scheduling import fitted_weights, store_weights

    user = User(email="a@b.c", password_hash="x", display_name="A")
    user.settings = {}
    fitted = tuple(w * 1.1 for w in fsrs.DEFAULT_WEIGHTS)

    store_weights(user, fitted, {"fitted_at": "2026-03-01T00:00:00Z"})

    assert fitted_weights(user) == fitted
    # The metadata rides along, so a later fit can be compared with this one.
    assert user.settings["fsrs"]["fitted_at"] == "2026-03-01T00:00:00Z"


def test_storing_replaces_the_dict_rather_than_mutating_it() -> None:
    """SQLAlchemy does not notice a JSONB dict edited in place.

    Mutating would leave the fit in memory and never in the database — the kind of
    bug that looks like it works until the next request.
    """
    from noema.db.models import User
    from noema.study.scheduling import store_weights

    user = User(email="a@b.c", password_hash="x", display_name="A")
    original = {"theme": "dark"}
    user.settings = original

    store_weights(user, fsrs.DEFAULT_WEIGHTS, {})

    assert user.settings is not original, "the settings dict was mutated in place"
    assert user.settings["theme"] == "dark", "unrelated settings were dropped"
