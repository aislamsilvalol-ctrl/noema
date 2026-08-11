from __future__ import annotations

import pytest

from noema.engines import mastery
from noema.engines.fsrs import MemoryState
from noema.engines.mastery import CardSnapshot, Evidence, Grader


def correct(**kw: object) -> Evidence:
    return Evidence(score=1.0, difficulty=0.5, age_days=1.0, grader=Grader.DETERMINISTIC, **kw)  # type: ignore[arg-type]


def wrong(**kw: object) -> Evidence:
    return Evidence(score=0.0, difficulty=0.5, age_days=1.0, grader=Grader.DETERMINISTIC, **kw)  # type: ignore[arg-type]


def test_no_evidence_falls_back_to_the_default_prior() -> None:
    result = mastery.compute_mastery([])
    assert result.competence == pytest.approx(0.35)
    assert result.retrievability == 0.0
    assert result.score == pytest.approx(100 * 0.35 * 0.5)
    assert result.is_provisional


def test_thin_evidence_never_reads_as_mastered() -> None:
    """Two right answers must not produce 100. The prior is doing the work here."""
    result = mastery.compute_mastery([correct(), correct()])
    assert result.score < 60
    assert result.is_provisional


def test_sustained_correct_evidence_approaches_full_mastery() -> None:
    fresh_cards = [CardSnapshot(MemoryState(30.0, 4.0), elapsed_days=0.0)]
    result = mastery.compute_mastery([correct() for _ in range(40)], cards=fresh_cards)
    assert result.score > 90
    assert not result.is_provisional


def test_prerequisites_set_the_prior() -> None:
    weak = mastery.compute_mastery([], prerequisite_masteries=[(20.0, 1.0)])
    strong = mastery.compute_mastery([], prerequisite_masteries=[(90.0, 1.0)])
    assert weak.prior_mean == pytest.approx(0.2)
    assert strong.prior_mean == pytest.approx(0.9)
    assert weak.score < strong.score


def test_forgetting_reduces_mastery_but_only_to_the_floor() -> None:
    evidence = [correct() for _ in range(40)]
    fresh = mastery.compute_mastery(
        evidence, cards=[CardSnapshot(MemoryState(20.0, 4.0), elapsed_days=0.0)]
    )
    stale = mastery.compute_mastery(
        evidence, cards=[CardSnapshot(MemoryState(20.0, 4.0), elapsed_days=3650.0)]
    )
    assert stale.score < fresh.score
    assert stale.score > 50 * stale.competence

    # The power forgetting curve has a long tail, so the floor is a limit rather than
    # something a real card reaches. Verify the limit holds.
    forgotten = mastery.compute_mastery(
        evidence, cards=[CardSnapshot(MemoryState(20.0, 4.0), elapsed_days=1e6)]
    )
    assert forgotten.score == pytest.approx(50 * forgotten.competence, rel=0.02)


def test_zero_competence_gives_zero_mastery_however_recent() -> None:
    result = mastery.compute_mastery(
        [wrong() for _ in range(200)],
        cards=[CardSnapshot(MemoryState(30.0, 5.0), elapsed_days=0.0)],
        prerequisite_masteries=[(0.0, 1.0)],
    )
    assert result.score < 3


def test_confident_errors_hurt_more_than_uncertain_ones() -> None:
    guessed = mastery.compute_mastery([wrong(confidence=1) for _ in range(5)])
    certain = mastery.compute_mastery([wrong(confidence=5) for _ in range(5)])
    assert certain.score < guessed.score


def test_lucky_guesses_count_less_than_confident_answers() -> None:
    guessed = mastery.compute_mastery([correct(confidence=1) for _ in range(5)])
    certain = mastery.compute_mastery([correct(confidence=5) for _ in range(5)])
    assert guessed.score < certain.score


def test_ai_grading_is_discounted_against_deterministic_grading() -> None:
    deterministic = mastery.compute_mastery([correct() for _ in range(10)])
    ai_graded = mastery.compute_mastery(
        [
            Evidence(score=1.0, difficulty=0.5, age_days=1.0, grader=Grader.AI)
            for _ in range(10)
        ]
    )
    assert ai_graded.score < deterministic.score


def test_old_evidence_weighs_less_than_recent_evidence() -> None:
    recent = mastery.compute_mastery(
        [Evidence(1.0, 0.5, age_days=1, grader=Grader.DETERMINISTIC) for _ in range(10)]
    )
    old = mastery.compute_mastery(
        [Evidence(1.0, 0.5, age_days=365, grader=Grader.DETERMINISTIC) for _ in range(10)]
    )
    assert old.competence < recent.competence


def test_harder_items_carry_more_weight() -> None:
    easy = mastery.compute_mastery(
        [Evidence(1.0, 0.0, 1.0, Grader.DETERMINISTIC) for _ in range(10)]
    )
    expert = mastery.compute_mastery(
        [Evidence(1.0, 1.0, 1.0, Grader.DETERMINISTIC) for _ in range(10)]
    )
    assert expert.competence > easy.competence


def test_calibration_detects_overconfidence() -> None:
    overconfident = mastery.compute_mastery([wrong(confidence=5) for _ in range(5)])
    underconfident = mastery.compute_mastery([correct(confidence=1) for _ in range(5)])
    assert overconfident.calibration > 0.3
    assert underconfident.calibration < 0


def test_misconception_needs_both_a_wrong_answer_and_high_confidence() -> None:
    assert mastery.is_misconception(wrong(confidence=5))
    assert mastery.is_misconception(wrong(confidence=4))
    assert not mastery.is_misconception(wrong(confidence=2))
    assert not mastery.is_misconception(correct(confidence=5))
    assert not mastery.is_misconception(wrong())


def test_impact_ranks_by_what_a_concept_blocks() -> None:
    isolated = mastery.impact(40.0, [])
    foundational = mastery.impact(40.0, [4, 8])
    assert foundational > isolated

    # A weak prerequisite outranks a slightly weaker but isolated concept.
    assert mastery.impact(45.0, [6]) > mastery.impact(35.0, [])


def test_evidence_validates_its_inputs() -> None:
    with pytest.raises(ValueError):
        Evidence(1.5, 0.5, 1.0, Grader.DETERMINISTIC)
    with pytest.raises(ValueError):
        Evidence(1.0, 2.0, 1.0, Grader.DETERMINISTIC)
    with pytest.raises(ValueError):
        Evidence(1.0, 0.5, 1.0, Grader.DETERMINISTIC, confidence=6)
