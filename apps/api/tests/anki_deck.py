"""Building an `.apkg` for tests.

Kept out of the test modules so both the parser's tests and the database ones can
use it: importing one test module from another gives it two module names, which
mypy rightly refuses.

Built here rather than committed as a binary fixture, so what is under test is
legible in the diff. The tables mirror Anki's own — same columns, same order,
same kinds of value — because a parser tested against a convenient shape is a
parser tested against itself.
"""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path

__all__ = ["CREATED", "build"]

CREATED = datetime(2020, 1, 1, tzinfo=UTC)

SCHEMA = """
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

DECKS_TABLE = """
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
    connection.executescript(SCHEMA)
    if decks_table:
        connection.executescript(DECKS_TABLE)
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
                note.get("card_id", index),
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
