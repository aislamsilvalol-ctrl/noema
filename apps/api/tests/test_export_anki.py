"""Writing `.apkg` files.

There is no live Anki client in this environment to check against, so the
strongest verification available is round-tripping every export back through
`noema.importers.anki.read` — the same reader real Anki exports are tested
against in `tests/test_import_anki.py` — plus direct structural assertions on
the SQLite this module writes.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

from noema.exporters.anki import ExportCard, ExportSchedule, write
from noema.importers.anki import read

CREATED = datetime(2024, 6, 1, tzinfo=UTC)


def _collection(data: bytes) -> sqlite3.Connection:
    with zipfile.ZipFile(BytesIO(data)) as package:
        assert set(package.namelist()) == {"collection.anki2", "media"}
        assert json.loads(package.read("media")) == {}
        raw = package.read("collection.anki2")

    tmp = Path(tempfile.mkdtemp()) / "c.anki2"
    tmp.write_bytes(raw)
    connection = sqlite3.connect(tmp)
    connection.row_factory = sqlite3.Row
    return connection


# ── Round-tripping through the real reader ───────────────────────────────────


def test_a_basic_card_round_trips() -> None:
    card = ExportCard(
        front="What is a mitochondrion?",
        back="An organelle",
        type="basic",
        tags=(),
        schedule=None,
    )

    data = write([card], deck_name="Biology", created=CREATED)
    result = read(data)

    assert len(result.cards) == 1
    imported = result.cards[0]
    assert imported.front == "What is a mitochondrion?"
    assert imported.back == "An organelle"
    assert imported.type == "basic"
    assert imported.deck == "Biology"
    assert imported.schedule is None


def test_line_breaks_survive_the_round_trip() -> None:
    card = ExportCard(
        front="Line one\nLine two", back="Answer", type="basic", tags=(), schedule=None
    )

    result = read(write([card], deck_name="Deck", created=CREATED))

    assert result.cards[0].front == "Line one\nLine two"


def test_html_special_characters_survive_the_round_trip() -> None:
    card = ExportCard(
        front="1 < 2 & 3 > 0", back="true", type="basic", tags=(), schedule=None
    )

    result = read(write([card], deck_name="Deck", created=CREATED))

    assert result.cards[0].front == "1 < 2 & 3 > 0"


def test_tags_survive_the_round_trip() -> None:
    card = ExportCard(
        front="Q", back="A", type="basic", tags=("hard", "week-3"), schedule=None
    )

    result = read(write([card], deck_name="Deck", created=CREATED))

    assert result.cards[0].tags == ("hard", "week-3")


def test_a_cloze_card_already_holding_markup_round_trips() -> None:
    """A card that arrived from Anki keeps its raw `{{c1::...}}` text verbatim."""
    card = ExportCard(
        front="The {{c1::mitochondria}} is the powerhouse of the cell.",
        back="",
        type="cloze",
        tags=(),
        schedule=None,
    )

    result = read(write([card], deck_name="Deck", created=CREATED))

    assert result.cards[0].type == "cloze"
    assert "{{c1::mitochondria}}" in result.cards[0].front


def test_a_generated_cloze_card_is_rebuilt_into_markup() -> None:
    """A card generated inside NOEMA carries the blank pre-rendered instead."""
    card = ExportCard(
        front="The […] fills the ventricles.",
        back="diastole",
        type="cloze",
        tags=(),
        schedule=None,
    )

    result = read(write([card], deck_name="Deck", created=CREATED))

    assert result.cards[0].type == "cloze"
    assert result.cards[0].front == "The {{c1::diastole}} fills the ventricles."


def test_a_generated_cloze_card_with_a_hint_is_rebuilt_into_markup() -> None:
    card = ExportCard(
        front="The […](chamber) fills with blood.",
        back="ventricle",
        type="cloze",
        tags=(),
        schedule=None,
    )

    result = read(write([card], deck_name="Deck", created=CREATED))

    assert result.cards[0].front == "The {{c1::ventricle::chamber}} fills with blood."


def test_a_cloze_answer_that_would_break_the_markup_is_left_behind() -> None:
    card = ExportCard(
        front="The […] fills the ventricles.",
        back="a beat (see {{c2::note}})",
        type="cloze",
        tags=(),
        schedule=None,
    )

    result = read(write([card], deck_name="Deck", created=CREATED))

    assert result.cards == ()


def test_an_image_card_is_left_behind() -> None:
    card = ExportCard(
        front="See the diagram", back="", type="image", tags=(), schedule=None
    )

    result = read(write([card], deck_name="Deck", created=CREATED))

    assert result.cards == ()


def test_a_reviewed_card_carries_its_schedule_across() -> None:
    schedule = ExportSchedule(
        stability=21.0,
        difficulty=4.0,
        reps=12,
        lapses=1,
        due_at=CREATED + timedelta(days=30),
    )
    card = ExportCard(front="Q", back="A", type="basic", tags=(), schedule=schedule)

    result = read(write([card], deck_name="Deck", created=CREATED))

    imported = result.cards[0].schedule
    assert imported is not None
    assert imported.stability == 21.0
    assert imported.reps == 12
    assert imported.lapses == 1
    assert imported.due_at == CREATED + timedelta(days=30)
    # Difficulty round-trips through Anki's ease factor, which only has integer
    # permille resolution — close, not exact, the same approximation the
    # importer itself documents.
    assert abs(imported.difficulty - 4.0) < 0.1


def test_a_new_cards_schedule_is_absent_after_the_round_trip() -> None:
    card = ExportCard(front="Q", back="A", type="basic", tags=(), schedule=None)

    result = read(write([card], deck_name="Deck", created=CREATED))

    assert result.cards[0].schedule is None


def test_many_cards_all_arrive() -> None:
    cards = [
        ExportCard(front=f"Q{i}", back=f"A{i}", type="basic", tags=(), schedule=None)
        for i in range(25)
    ]

    result = read(write(cards, deck_name="Deck", created=CREATED))

    assert {card.front for card in result.cards} == {f"Q{i}" for i in range(25)}


# ── The SQLite itself ─────────────────────────────────────────────────────────


def test_the_package_has_exactly_the_members_anki_expects() -> None:
    data = write(
        [ExportCard(front="Q", back="A", type="basic", tags=(), schedule=None)],
        deck_name="Deck",
        created=CREATED,
    )

    with zipfile.ZipFile(BytesIO(data)) as package:
        assert set(package.namelist()) == {"collection.anki2", "media"}


def test_the_collection_header_is_well_formed() -> None:
    data = write(
        [ExportCard(front="Q", back="A", type="basic", tags=(), schedule=None)],
        deck_name="My Deck",
        created=CREATED,
    )
    connection = _collection(data)
    try:
        row = connection.execute(
            "SELECT crt, ver, models, decks, dconf, conf FROM col"
        ).fetchone()
        assert row["crt"] == int(CREATED.timestamp())
        assert row["ver"] == 11

        models = json.loads(row["models"])
        assert {model["name"] for model in models.values()} == {"Basic", "Cloze"}
        for model in models.values():
            assert len(model["flds"]) == 2
            assert len(model["tmpls"]) == 1

        decks = json.loads(row["decks"])
        assert {deck["name"] for deck in decks.values()} == {"Default", "My Deck"}

        dconf = json.loads(row["dconf"])
        assert len(dconf) == 1

        conf = json.loads(row["conf"])
        assert conf["activeDecks"]
    finally:
        connection.close()


def test_an_empty_export_still_produces_a_readable_collection() -> None:
    data = write([], deck_name="Empty", created=CREATED)

    result = read(data)

    assert result.cards == ()
