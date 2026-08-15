"""Reading real `.apkg` files.

The fixtures are built here with sqlite3 and zipfile rather than committed as
binaries, so what is being tested is legible in the diff: a committed `.apkg`
is an opaque blob that nobody reviews and nobody can adjust.

The tables mirror Anki's own — the same columns, in the same order, holding the
same kinds of value — because a parser tested against a convenient shape is a
parser tested against itself.
"""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from noema.importers.anki import (
    AnkiImportError,
    ImportedCard,
    read,
)

CREATED = datetime(2020, 1, 1, tzinfo=UTC)

OLD_SCHEMA = """
CREATE TABLE col (id integer primary key, crt integer, mod integer, scm integer,
    ver integer, dty integer, usn integer, ls integer, conf text, models text,
    decks text, dconf text, tags text);
CREATE TABLE notes (id integer primary key, guid text, mid integer, mod integer,
    usn integer, tags text, flds text, sfld text, csum integer, flags integer,
    data text);
CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer,
    mod integer, usn integer, type integer, queue integer, due integer,
    ivl integer, factor integer, reps integer, lapses integer, left integer,
    odue integer, odid integer, flags integer, data text);
"""

NEW_DECKS_TABLE = """
CREATE TABLE decks (id integer primary key, name text);
"""


def build(
    tmp_path: Path,
    notes: list[dict[str, object]],
    *,
    decks: dict[int, str] | None = None,
    decks_table: bool = False,
    filename: str = "collection.anki2",
) -> bytes:
    """Assemble an `.apkg` from a description of its notes."""
    decks = decks or {1: "Default"}
    database = tmp_path / "build.anki2"
    database.unlink(missing_ok=True)

    connection = sqlite3.connect(database)
    connection.executescript(OLD_SCHEMA)
    if decks_table:
        connection.executescript(NEW_DECKS_TABLE)
        connection.executemany(
            "INSERT INTO decks (id, name) VALUES (?, ?)", list(decks.items())
        )
        deck_json = "{}"
    else:
        deck_json = json.dumps({str(key): {"name": name} for key, name in decks.items()})

    connection.execute(
        "INSERT INTO col (id, crt, decks, models) VALUES (1, ?, ?, '{}')",
        (int(CREATED.timestamp()), deck_json),
    )

    for index, note in enumerate(notes, start=1):
        connection.execute(
            "INSERT INTO notes (id, guid, mid, tags, flds, sfld) "
            "VALUES (?, ?, 1, ?, ?, '')",
            (index, f"g{index}", note.get("tags", ""), note["flds"]),
        )
        connection.execute(
            "INSERT INTO cards (id, nid, did, ord, type, queue, due, ivl, factor,"
            " reps, lapses, left, odue, odid, flags) "
            "VALUES (?, ?, ?, ?, ?, 2, ?, ?, ?, ?, ?, 0, 0, 0, 0)",
            (
                index,
                index,
                note.get("did", 1),
                note.get("ord", 0),
                note.get("type", 0),
                note.get("due", 0),
                note.get("ivl", 0),
                note.get("factor", 2500),
                note.get("reps", 0),
                note.get("lapses", 0),
            ),
        )

    connection.commit()
    connection.close()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr(filename, database.read_bytes())
        package.writestr("media", "{}")
    return buffer.getvalue()


def only(cards: tuple[ImportedCard, ...]) -> ImportedCard:
    assert len(cards) == 1, f"expected one card, got {len(cards)}"
    return cards[0]


# ── The cards themselves ─────────────────────────────────────────────────────


def test_a_basic_card_comes_across(tmp_path: Path) -> None:
    result = read(build(tmp_path, [{"flds": "What is a mitochondrion?\x1fAn organelle"}]))

    card = only(result.cards)
    assert card.front == "What is a mitochondrion?"
    assert card.back == "An organelle"
    assert card.type == "basic"


def test_the_second_template_is_the_reverse_and_is_swapped(tmp_path: Path) -> None:
    """Anki's second card for a note asks the question the other way round.

    Importing it unswapped would give the learner two identical cards and quietly
    halve the value of a reversed deck.
    """
    result = read(build(tmp_path, [{"flds": "casa\x1fhouse", "ord": 1}]))

    card = only(result.cards)
    assert card.type == "reverse"
    assert card.front == "house"
    assert card.back == "casa"


def test_a_cloze_note_keeps_its_syntax(tmp_path: Path) -> None:
    """`{{c1::...}}` is exactly what `noema.engines.cloze` already expands."""
    result = read(
        build(tmp_path, [{"flds": "The capital of {{c1::France}} is {{c2::Paris}}"}])
    )

    card = only(result.cards)
    assert card.type == "cloze"
    assert card.front == "The capital of {{c1::France}} is {{c2::Paris}}"


def test_tags_and_deck_names_survive(tmp_path: Path) -> None:
    result = read(
        build(
            tmp_path,
            [{"flds": "q\x1fa", "tags": " biology  cells ", "did": 7}],
            decks={7: "Biology"},
        )
    )

    card = only(result.cards)
    assert card.tags == ("biology", "cells")
    assert card.deck == "Biology"


def test_nested_deck_names_from_the_newer_layout(tmp_path: Path) -> None:
    result = read(
        build(
            tmp_path,
            [{"flds": "q\x1fa", "did": 3}],
            decks={3: "Medicine\x1fCardiology"},
            decks_table=True,
        )
    )

    assert only(result.cards).deck == "Medicine::Cardiology"


# ── The history, which is the reason to import at all ────────────────────────


def test_a_reviewed_card_keeps_its_interval(tmp_path: Path) -> None:
    """The interval is the part that cannot be recreated by retyping.

    Losing it means re-reviewing thousands of cards the learner already knows,
    which is the single fastest way to make someone abandon an import.
    """
    result = read(
        build(
            tmp_path,
            [
                {
                    "flds": "q\x1fa",
                    "type": 2,
                    "ivl": 180,
                    "due": 400,
                    "reps": 12,
                    "lapses": 2,
                }
            ],
        )
    )

    schedule = only(result.cards).schedule
    assert schedule is not None
    assert schedule.stability == 180.0
    assert schedule.reps == 12
    assert schedule.lapses == 2
    assert schedule.state == "review"
    assert schedule.due_at == CREATED + timedelta(days=400)


def test_a_harder_card_imports_as_harder(tmp_path: Path) -> None:
    """The scales are different and inverted; only the ordering must hold."""
    easy = read(
        build(tmp_path, [{"flds": "q\x1fa", "type": 2, "ivl": 10, "factor": 2900}])
    )
    hard = read(
        build(tmp_path, [{"flds": "q\x1fa", "type": 2, "ivl": 10, "factor": 1400}])
    )

    easy_schedule = only(easy.cards).schedule
    hard_schedule = only(hard.cards).schedule
    assert easy_schedule is not None and hard_schedule is not None
    assert hard_schedule.difficulty > easy_schedule.difficulty
    assert 1.0 <= easy_schedule.difficulty <= 10.0
    assert 1.0 <= hard_schedule.difficulty <= 10.0


def test_a_card_with_no_ease_gets_the_default_not_the_worst_score(
    tmp_path: Path,
) -> None:
    """Factor 0 means "never rated", not "impossibly hard".

    The raw arithmetic would call it maximally difficult and bury a perfectly
    good card at the top of every queue for weeks.
    """
    result = read(build(tmp_path, [{"flds": "q\x1fa", "type": 2, "ivl": 5, "factor": 0}]))

    schedule = only(result.cards).schedule
    assert schedule is not None
    assert schedule.difficulty == 5.0


def test_an_unseen_card_arrives_unscheduled(tmp_path: Path) -> None:
    result = read(build(tmp_path, [{"flds": "q\x1fa", "type": 0}]))

    assert only(result.cards).schedule is None


def test_a_card_still_in_learning_arrives_unscheduled(tmp_path: Path) -> None:
    """Learning cards store seconds as a negative interval.

    Read as days it becomes a card due in the past with negative stability, so
    it is imported as new — which is nearly true, and safe.
    """
    result = read(build(tmp_path, [{"flds": "q\x1fa", "type": 1, "ivl": -600}]))

    assert only(result.cards).schedule is None


# ── Markup, which every real deck is full of ─────────────────────────────────


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("<div>Hello</div>", "Hello"),
        ("a<br>b", "a\nb"),
        ("&amp; &lt;tag&gt; &nbsp;x", "& <tag>  x"),
        ('<span style="color:red">red</span>', "red"),
        ("<b>bold</b> and <i>italic</i>", "bold and italic"),
    ],
)
def test_html_becomes_readable_text(tmp_path: Path, field: str, expected: str) -> None:
    result = read(build(tmp_path, [{"flds": f"{field}\x1fanswer"}]))

    assert only(result.cards).front == expected


# ── Refusals, each with something the learner can do about it ────────────────


def test_a_card_answered_only_with_an_image_is_reported_not_dropped(
    tmp_path: Path,
) -> None:
    """Media is not imported, so this card would arrive with a blank answer.

    Counting it is the difference between "312 cards imported" and "312 imported,
    40 skipped because their answers were images" — the second is trustworthy.
    """
    result = read(build(tmp_path, [{"flds": 'q\x1f<img src="heart.png">'}]))

    assert result.cards == ()
    assert sum(result.skipped.values()) == 1
    assert "media" in result.summary()


def test_the_compressed_format_says_how_to_export_it_differently(
    tmp_path: Path,
) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("collection.anki21b", b"\x28\xb5\x2f\xfd")

    with pytest.raises(AnkiImportError, match="Support older Anki versions"):
        read(buffer.getvalue())


def test_something_that_is_not_a_zip_is_refused_clearly() -> None:
    with pytest.raises(AnkiImportError, match=r"not a readable \.apkg"):
        read(b"this is a text file")


def test_a_zip_without_a_collection_is_refused(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("notes.txt", "hello")

    with pytest.raises(AnkiImportError, match="no collection"):
        read(buffer.getvalue())


# ── What the learner is told ─────────────────────────────────────────────────


def test_the_summary_counts_what_arrived_and_what_did_not(tmp_path: Path) -> None:
    result = read(
        build(
            tmp_path,
            [
                {"flds": "a\x1f1", "type": 2, "ivl": 30},
                {"flds": "b\x1f2"},
                {"flds": 'c\x1f<img src="x.png">'},
            ],
        )
    )

    summary = result.summary()
    assert "2 cards" in summary
    assert "1 with their review history" in summary
    assert "Skipped" in summary
