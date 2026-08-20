"""Turning a model's raw response into cards worth showing a human."""

from __future__ import annotations

from noema.db.models import CardType
from noema.study.generation import (
    MAX_BACK,
    MAX_CARDS_PER_BATCH,
    MAX_FRONT,
    parse_cards,
)


def card(**overrides: object) -> dict[str, object]:
    base = {"front": "Q", "back": "A", "type": "basic", "concept": "Cell Biology"}
    return {**base, **overrides}


def test_a_well_formed_card_comes_through() -> None:
    cards = parse_cards({"cards": [card()]}, ["chunk-1"])

    assert len(cards) == 1
    assert cards[0].front == "Q"
    assert cards[0].back == "A"
    assert cards[0].type is CardType.BASIC
    assert cards[0].concept_name == "Cell Biology"
    assert cards[0].source_chunk_ids == ["chunk-1"]


def test_a_missing_cards_key_is_no_cards_not_an_error() -> None:
    assert parse_cards({}, []) == []


def test_a_non_list_cards_value_is_no_cards() -> None:
    assert parse_cards({"cards": "not a list"}, []) == []


def test_a_non_dict_item_is_skipped() -> None:
    cards = parse_cards({"cards": ["not a dict", card()]}, [])

    assert len(cards) == 1


def test_a_card_with_no_front_is_skipped() -> None:
    cards = parse_cards({"cards": [card(front="")]}, [])

    assert cards == []


def test_a_card_with_no_back_is_skipped() -> None:
    cards = parse_cards({"cards": [card(back="")]}, [])

    assert cards == []


def test_a_card_whose_answer_restates_the_question_is_skipped() -> None:
    """The most common way a generated deck pads itself out."""
    cards = parse_cards({"cards": [card(front="Mitochondria", back="mitochondria ")]}, [])

    assert cards == []


def test_front_and_back_are_truncated_to_their_limits() -> None:
    cards = parse_cards(
        {"cards": [card(front="Q" * (MAX_FRONT + 50), back="A" * (MAX_BACK + 50))]}, []
    )

    assert len(cards[0].front) == MAX_FRONT
    assert len(cards[0].back) == MAX_BACK


def test_only_the_first_batch_limit_worth_of_cards_survive() -> None:
    raw = [card(front=f"Q{i}", back=f"A{i}") for i in range(MAX_CARDS_PER_BATCH + 5)]
    cards = parse_cards({"cards": raw}, [])

    assert len(cards) == MAX_CARDS_PER_BATCH
    assert cards[0].front == "Q0"


def test_every_recognised_type_maps_correctly() -> None:
    mapping = {
        "basic": CardType.BASIC,
        "definition": CardType.DEFINITION,
        "concept": CardType.CONCEPT,
        "code": CardType.CODE,
    }
    for raw, expected in mapping.items():
        cards = parse_cards({"cards": [card(type=raw)]}, [])
        assert cards[0].type is expected, raw


def test_an_unrecognised_type_falls_back_to_basic() -> None:
    cards = parse_cards({"cards": [card(type="essay")]}, [])

    assert cards[0].type is CardType.BASIC


def test_a_missing_type_falls_back_to_basic() -> None:
    cards = parse_cards({"cards": [{"front": "Q", "back": "A", "concept": "x"}]}, [])

    assert cards[0].type is CardType.BASIC


def test_the_concept_name_is_truncated_to_200_characters() -> None:
    cards = parse_cards({"cards": [card(concept="x" * 250)]}, [])

    assert len(cards[0].concept_name) == 200


def test_every_card_in_the_batch_carries_the_same_source_chunk_ids() -> None:
    cards = parse_cards(
        {"cards": [card(front="Q1", back="A1"), card(front="Q2", back="A2")]},
        ["chunk-a", "chunk-b"],
    )

    assert cards[0].source_chunk_ids == ["chunk-a", "chunk-b"]
    assert cards[1].source_chunk_ids == ["chunk-a", "chunk-b"]
