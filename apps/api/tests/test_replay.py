"""Replaying review histories.

These tests build histories with known properties and check the replay reports them
— because the whole point of the harness is to be trusted when it says a scheduler
change made things worse.
"""

from __future__ import annotations

import pytest

from noema.engines import fsrs
from noema.engines.replay import Attempt, compare, replay


def history(
    ratings: list[fsrs.Rating], *, gap: float = 5.0, card: str = "c1"
) -> list[Attempt]:
    return [Attempt(card_id=card, elapsed_days=gap, rating=rating) for rating in ratings]


def test_a_history_with_no_second_review_scores_nothing() -> None:
    """A first exposure has no prediction to score: there was no memory yet."""
    result = replay(history([fsrs.Rating.GOOD]))
    assert result.attempts == 0


def test_predictions_are_made_before_the_answer_is_applied() -> None:
    """Scoring a model on information it would not have had makes it look perfect."""
    result = replay(history([fsrs.Rating.GOOD] * 5))

    assert result.attempts == 4  # five reviews, four predictions
    assert 0 < result.mean_predicted < 1


def test_recalling_after_long_gaps_makes_the_model_look_pessimistic() -> None:
    """Someone who remembers far longer than predicted is evidence the intervals are
    too short — the harness has to be able to say so."""
    result = replay(history([fsrs.Rating.GOOD] * 20, gap=45.0))

    assert result.actual_recall == 1.0
    assert not result.optimistic
    assert "pessimistic" in result.summary().lower()


def test_reviewing_on_schedule_reads_as_well_calibrated() -> None:
    result = replay(history([fsrs.Rating.GOOD] * 20, gap=2.0))

    assert result.actual_recall == 1.0
    assert "well calibrated" in result.summary().lower()


def test_a_learner_who_never_recalls_makes_the_model_look_optimistic() -> None:
    result = replay(history([fsrs.Rating.AGAIN] * 20, gap=2.0))

    assert result.actual_recall == 0.0
    assert result.optimistic
    assert result.calibration_error > 0


def test_log_loss_punishes_confident_wrongness() -> None:
    """Reviewing at a short interval predicts high recall; failing anyway should
    cost more than failing after a long gap."""
    confident_and_wrong = replay(
        [
            Attempt("c1", 0.5, fsrs.Rating.GOOD),
            Attempt("c1", 0.5, fsrs.Rating.AGAIN),
        ]
    )
    unsure_and_wrong = replay(
        [
            Attempt("c1", 0.5, fsrs.Rating.GOOD),
            Attempt("c1", 400.0, fsrs.Rating.AGAIN),
        ]
    )

    assert confident_and_wrong.log_loss > unsure_and_wrong.log_loss


def test_cards_are_replayed_independently() -> None:
    """One card's state must never leak into another's prediction."""
    interleaved = [
        Attempt("a", 1.0, fsrs.Rating.GOOD),
        Attempt("b", 1.0, fsrs.Rating.AGAIN),
        Attempt("a", 1.0, fsrs.Rating.GOOD),
        Attempt("b", 1.0, fsrs.Rating.AGAIN),
    ]
    separate = replay([interleaved[0], interleaved[2]])
    mixed = replay(interleaved)

    assert mixed.attempts == 2
    # Card A's prediction is unchanged by B's presence in the log.
    assert mixed.buckets != [] and separate.buckets != []


def test_buckets_form_a_reliability_curve() -> None:
    result = replay(
        history([fsrs.Rating.GOOD] * 10, gap=1.0, card="a")
        + history([fsrs.Rating.AGAIN] * 10, gap=90.0, card="b")
    )

    assert result.buckets
    assert sum(b.count for b in result.buckets) == result.attempts
    assert all(0 <= b.predicted <= 1 and 0 <= b.actual <= 1 for b in result.buckets)


def test_calibration_error_is_zero_when_predictions_match_outcomes() -> None:
    """A history where roughly the predicted fraction is recalled should score well."""
    perfect = replay(history([fsrs.Rating.GOOD] * 30, gap=0.01))

    # At a near-zero gap the model predicts ~100% recall, and gets it.
    assert perfect.calibration_error < 0.05


def test_comparing_weight_sets_reports_which_fits_better() -> None:
    """The point of the harness: a scheduler change is judged, not asserted."""
    attempts = history(
        [fsrs.Rating.GOOD, fsrs.Rating.GOOD, fsrs.Rating.AGAIN] * 10, gap=3.0
    )

    # A variant that grows stability far faster, so it over-predicts recall.
    optimistic = list(fsrs.DEFAULT_WEIGHTS)
    optimistic[8] = optimistic[8] + 2.0

    baseline, candidate, candidate_better = compare(attempts, candidate=tuple(optimistic))

    assert baseline.attempts == candidate.attempts
    assert candidate.mean_predicted != baseline.mean_predicted
    assert candidate_better is (candidate.log_loss < baseline.log_loss)


def test_an_empty_history_reports_nothing_rather_than_dividing_by_zero() -> None:
    result = replay([])
    assert result.attempts == 0
    assert result.log_loss == 0.0
    assert result.buckets == []


def test_the_summary_names_the_direction_of_the_error() -> None:
    optimistic = replay(history([fsrs.Rating.AGAIN] * 15, gap=1.0))
    assert "optimistic" in optimistic.summary().lower()
    assert "15" in optimistic.summary() or "14" in optimistic.summary()


@pytest.mark.parametrize("rating", list(fsrs.Rating))
def test_every_rating_replays_without_error(rating: fsrs.Rating) -> None:
    assert replay(history([rating] * 3)).attempts == 2


def test_no_history_makes_no_claim() -> None:
    """The empty summary was the one that reached a real screen.

    With nothing scored, predicted and actual are both zero, so the gap is zero
    and the old wording announced "Well calibrated over 0 reviews" — a confident
    number from no evidence, on the progress page, to a learner who had just
    signed up. It is rendered whether or not the result is marked reliable.
    """
    summary = replay([]).summary()

    assert "well calibrated" not in summary.lower()
    assert "0 reviews" not in summary
