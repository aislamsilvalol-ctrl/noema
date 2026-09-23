"""The placement engine — pure, so it runs without a database."""

from __future__ import annotations

import math

from noema.engines.placement import (
    MAX_QUESTIONS,
    MIN_QUESTIONS,
    PRIOR_SD,
    STOP_SE,
    Ability,
    difficulty_logit,
    information,
    next_item,
    probability_correct,
    should_stop,
    update,
)


def test_an_average_item_meets_an_average_learner_at_even_odds() -> None:
    assert difficulty_logit(0.5) == 0.0
    assert probability_correct(0.0, difficulty_logit(0.5)) == 0.5


def test_difficulty_at_the_extremes_stays_finite() -> None:
    """A real item is never certain either way, and infinity breaks the arithmetic."""
    assert math.isfinite(difficulty_logit(0.0))
    assert math.isfinite(difficulty_logit(1.0))
    assert difficulty_logit(0.0) < difficulty_logit(0.5) < difficulty_logit(1.0)


def test_the_most_informative_question_is_the_one_nearest_the_belief() -> None:
    """An answer nobody can predict teaches most; a foregone one teaches nothing."""
    even = information(0.0, difficulty_logit(0.5))
    hopeless = information(0.0, difficulty_logit(0.98))
    trivial = information(0.0, difficulty_logit(0.02))
    assert even > hopeless and even > trivial
    assert even == 0.25  # p = 0.5 exactly


def test_a_right_answer_raises_the_estimate_and_a_wrong_one_lowers_it() -> None:
    start = Ability()
    up = update(start, difficulty_logit(0.5), correct=True)
    down = update(start, difficulty_logit(0.5), correct=False)
    assert up.mean > start.mean > down.mean


def test_being_right_about_a_hard_item_moves_more_than_an_easy_one() -> None:
    """Which is the whole reason to choose the question rather than pick one."""
    start = Ability()
    hard = update(start, difficulty_logit(0.9), correct=True)
    easy = update(start, difficulty_logit(0.1), correct=True)
    assert hard.mean > easy.mean


def test_every_answer_tightens_the_belief() -> None:
    ability = Ability()
    widths = [ability.sd]
    for _ in range(5):
        ability = update(ability, difficulty_logit(0.5), correct=True)
        widths.append(ability.sd)
    assert widths == sorted(widths, reverse=True)
    assert widths[-1] < widths[0]


def test_a_confident_learner_is_asked_harder_things() -> None:
    bank = {"easy": 0.2, "medium": 0.5, "hard": 0.8}
    assert next_item(Ability(mean=0.0), bank) == "medium"
    assert next_item(Ability(mean=1.6), bank) == "hard"
    assert next_item(Ability(mean=-1.6), bank) == "easy"


def test_an_empty_bank_asks_nothing_rather_than_guessing() -> None:
    assert next_item(Ability(), {}) is None


def test_the_same_belief_and_bank_always_choose_the_same_question() -> None:
    """A diagnostic that varies under repetition cannot be debugged."""
    bank = {"b": 0.5, "a": 0.5, "c": 0.5}  # identical difficulty: the tie-break decides
    assert next_item(Ability(), bank) == "a"
    assert next_item(Ability(), bank) == "a"


def test_it_never_concludes_from_one_lucky_answer() -> None:
    settled = Ability(mean=0.0, sd=0.01)
    assert should_stop(settled, asked=MIN_QUESTIONS - 1) is False
    assert should_stop(settled, asked=MIN_QUESTIONS) is True


def test_it_stops_asking_even_when_it_never_became_sure() -> None:
    """Someone who came to learn did not come to be measured."""
    unsure = Ability(mean=0.0, sd=10.0)
    assert should_stop(unsure, asked=MAX_QUESTIONS - 1) is False
    assert should_stop(unsure, asked=MAX_QUESTIONS) is True


def test_a_diagnostic_ends_and_says_something_about_the_learner() -> None:
    """Strength shows in the estimate; the length is bounded either way."""
    ability = Ability()
    asked = 0
    bank = {f"q{i}": d for i, d in enumerate((0.1, 0.3, 0.5, 0.7, 0.9))}
    while not should_stop(ability, asked):
        item = next_item(ability, bank)
        assert item is not None
        ability = update(ability, difficulty_logit(bank[item]), correct=True)
        asked += 1
    assert MIN_QUESTIONS <= asked <= MAX_QUESTIONS
    assert ability.mean > 0.0  # answering everything right must read as strength


def test_the_stopping_threshold_is_one_the_model_can_actually_reach() -> None:
    """An early-stopping rule that cannot fire is a lie told in a constant.

    Precision gains at most 0.25 per answer, and the prior starts at
    1/PRIOR_SD**2. So the tightest belief reachable inside the cap is fixed, and
    the threshold has to sit above it or the rule is decoration.
    """
    best_precision = 1.0 / PRIOR_SD**2 + 0.25 * MAX_QUESTIONS
    best_se = math.sqrt(1.0 / best_precision)
    assert best_se < STOP_SE, (
        f"unreachable: best possible SE after {MAX_QUESTIONS} answers is {best_se:.3f}"
    )


def test_an_ideal_informant_stops_before_the_cap() -> None:
    """The case the engine is built to create: every question at even odds."""
    ability = Ability()
    asked = 0
    while not should_stop(ability, asked):
        # An item exactly at the current belief — the most informative there is.
        ability = update(ability, ability.mean, correct=asked % 2 == 0)
        asked += 1
    assert asked < MAX_QUESTIONS
