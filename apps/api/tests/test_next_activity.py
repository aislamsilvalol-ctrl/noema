"""The next-activity rule and the focus-session plan, without a database."""

from __future__ import annotations

import uuid

from noema.db.models import LearningJourney, User
from noema.professor.focus import load_for
from noema.services.focus_sessions import auto_minutes, steps_for
from noema.services.next_activity import (
    REVIEW_THRESHOLD,
    LearnCandidate,
    choose,
    review_minutes,
)

JOURNEY = LearnCandidate(
    journey_id=uuid.uuid4(), subject="Freud", concept="recalque", session_id=None
)


def test_nothing_anywhere_means_start() -> None:
    activity = choose(due_count=0, overdue_count=0, candidate=None)
    assert activity.kind == "start"
    assert activity.reason_code == "start"
    assert activity.journey_id is None


def test_a_journey_and_nothing_due_continues_it_at_its_concept() -> None:
    activity = choose(due_count=0, overdue_count=0, candidate=JOURNEY, learn_minutes=8)
    assert activity.kind == "learn"
    assert activity.concept == "recalque"
    assert activity.title == "Freud"
    assert activity.journey_id == JOURNEY.journey_id
    assert activity.minutes_estimate == 8
    assert activity.reason_code == "continue"


def test_a_few_due_cards_wait_behind_the_lesson() -> None:
    activity = choose(due_count=REVIEW_THRESHOLD - 1, overdue_count=0, candidate=JOURNEY)
    assert activity.kind == "learn"
    assert activity.due_count == REVIEW_THRESHOLD - 1


def test_enough_due_cards_come_first() -> None:
    activity = choose(due_count=REVIEW_THRESHOLD, overdue_count=0, candidate=JOURNEY)
    assert activity.kind == "review"
    assert activity.reason_code == "due"
    assert activity.reason == f"{REVIEW_THRESHOLD} cards due for review"
    assert activity.minutes_estimate == review_minutes(REVIEW_THRESHOLD)


def test_one_overdue_card_comes_first_whatever_the_count() -> None:
    activity = choose(due_count=1, overdue_count=1, candidate=JOURNEY)
    assert activity.kind == "review"
    assert activity.reason_code == "overdue"
    assert activity.reason == "1 card overdue since yesterday or earlier"


def test_due_cards_with_nothing_else_under_way_are_the_next_thing() -> None:
    activity = choose(due_count=2, overdue_count=0, candidate=None)
    assert activity.kind == "review"


def test_review_minutes_are_whole_and_never_zero() -> None:
    assert review_minutes(1) == 1
    assert review_minutes(16) == 8


def test_auto_duration_is_always_one_of_the_offered_buttons() -> None:
    review = choose(due_count=3, overdue_count=1, candidate=None)
    assert auto_minutes(review) == 5
    many = choose(due_count=24, overdue_count=1, candidate=None)
    assert auto_minutes(many) == 15
    huge = choose(due_count=400, overdue_count=1, candidate=None)
    assert auto_minutes(huge) == 15
    learn = choose(due_count=0, overdue_count=0, candidate=JOURNEY)
    assert auto_minutes(learn) == 10


def test_steps_follow_the_minutes() -> None:
    # Learn: a micro-step is about two and a half minutes, never fewer than two.
    assert steps_for("learn", 5) == 2
    assert steps_for("learn", 10) == 4
    assert steps_for("learn", 25) == 10
    # Review: one rated card is a step, capped by what is due.
    assert steps_for("review", 5, due_count=3) == 3
    assert steps_for("review", 5, due_count=40) == 10


def test_the_focus_flag_reaches_the_load_profile_whatever_the_preference() -> None:
    user = User(email="a@example.com", password_hash="x", display_name="A")
    user.settings = {"learning_mode": "normal"}
    journey = LearningJourney(profile={})

    normal = load_for(user, journey)
    assert not normal.focus
    assert normal.ask_every == 3

    forced = load_for(user, journey, focus=True)
    assert forced.focus
    assert forced.ask_every == 1
    assert forced.max_words < normal.max_words
