"""Cloze expansion.

A pure transform, so the tests can be about meaning: what each card asks, what it
gives away, and what it refuses to make.
"""

from __future__ import annotations

from noema.engines.cloze import expand, has_deletions


def test_each_deletion_becomes_its_own_card() -> None:
    """Recalling one blank says nothing about the other."""
    cards = expand(
        "The {{c1::diastole}} fills the ventricles and the {{c2::systole}} empties them."
    )

    assert [c.number for c in cards] == [1, 2]
    assert [c.back for c in cards] == ["diastole", "systole"]


def test_the_other_deletions_are_shown_not_blanked() -> None:
    """Otherwise one question becomes a puzzle with several unknowns."""
    cards = expand("{{c1::Preload}} is volume; {{c2::afterload}} is resistance.")

    assert cards[0].front == "[…] is volume; afterload is resistance."
    assert cards[1].front == "Preload is volume; […] is resistance."


def test_the_same_number_twice_is_one_card() -> None:
    """`c1` appearing twice is one idea appearing twice.

    Blanking only one occurrence would print the answer beside the question.
    """
    cards = expand("{{c1::Sodium}} enters in phase 0; {{c1::sodium}} then inactivates.")

    assert len(cards) == 1
    assert cards[0].front == "[…] enters in phase 0; […] then inactivates."
    assert cards[0].back == "Sodium, sodium"


def test_a_hint_is_shown_on_the_front() -> None:
    """Anki's convention, and decks get imported from there."""
    cards = expand("The {{c1::mitral::which valve}} valve separates them.")

    assert cards[0].front == "The […](which valve) valve separates them."
    assert cards[0].back == "mitral"


def test_text_without_a_deletion_makes_nothing() -> None:
    """A cloze card with no blank grades itself correct forever."""
    assert expand("The diastole fills the ventricles.") == []
    assert has_deletions("The diastole fills the ventricles.") is False


def test_numbers_out_of_order_follow_the_text() -> None:
    """The reading order is the order someone wrote them in, not sorted."""
    cards = expand("{{c2::Second}} comes after {{c1::first}}.")

    assert [c.number for c in cards] == [2, 1]


def test_a_deletion_can_span_lines() -> None:
    """Notes are Markdown; a blanked clause wraps."""
    cards = expand("The rule is:\n\n{{c1::force equals\nmass times acceleration}}")

    assert cards[0].back == "force equals\nmass times acceleration"
    assert cards[0].front == "The rule is:\n\n[…]"
