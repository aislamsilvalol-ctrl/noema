"""Writing an Anki `.apkg` export.

The reverse trip of `noema.importers.anki`, with the same honesty about what does
and does not carry across cleanly:

* Anki paces its short-term learning queue in seconds against its own scheduler
  run, not in days since the collection was created — there is no faithful way to
  restate a card that is mid learning-step in that scheme. Only `review` and
  `relearning` cards, which Anki already times in whole days, carry their
  interval and ease across; everything else leaves as a fresh new card, the same
  one-way trip the importer makes when a card arrives unscheduled.
* FSRS stability becomes an Anki interval, and FSRS difficulty becomes an Anki
  ease factor, by inverting the importer's own approximations — monotonic and
  close, not exact, for the reasons documented there.
* A card whose answer depends on an image is not exported: media was never
  carried in, so it cannot be carried back out, and a card claiming to hold an
  answer it does not have is worse than one plainly left behind.

The `.apkg` this writes targets Anki's legacy "schema 11" collection format — the
one every Anki client has read without a plugin for well over a decade, and the
format third-party export tools target for exactly that reason. It has not been
exercised against a live Anki client in this environment: `tests/test_export_anki.py`
round-trips every export back through `noema.importers.anki.read` and asserts on
the generated SQLite's structure directly, which is the strongest check available
here short of that.
"""

from __future__ import annotations

import hashlib
import html
import itertools
import json
import re
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from secrets import token_urlsafe

from noema.engines.cloze import BLANK

__all__ = ["ExportCard", "ExportSchedule", "write"]

#: Matches `noema.importers.anki.FIELD_SEPARATOR` — Anki's own note-field split.
FIELD_SEPARATOR = "\x1f"

#: The inverse of `noema.importers.anki._difficulty` — see the docstring there.
EASE_EASY = 3100.0
EASE_HARD = 1300.0
DIFFICULTY_MIN = 1.0
DIFFICULTY_MAX = 10.0

#: Anki's floors: an interval of zero reads as "not yet studied", and ease below
#: this is not a value the algorithm itself ever produces.
MIN_INTERVAL_DAYS = 1
MIN_EASE = 1300
MAX_EASE = 3100

#: `noema.engines.cloze.expand` blanks a deletion as `BLANK` or `BLANK(hint)`.
_BLANK_PATTERN = re.compile(re.escape(BLANK) + r"(?:\(([^)]*)\))?")
_CLOZE_MARKUP = re.compile(r"\{\{c\d+::")

_BASIC_MODEL_ID = 1
_CLOZE_MODEL_ID = 2
_DEFAULT_DECK_ID = 1
_DECK_ID = 2
_DECK_CONF_ID = 1

#: Types that map onto a plain front/back Anki note. `cloze` is handled on its
#: own; `image` cannot be, and is the caller's responsibility to filter out.
BASIC_TYPES = frozenset({"basic", "reverse", "concept", "definition", "code"})


@dataclass(frozen=True, slots=True)
class ExportSchedule:
    """What FSRS had for this card, translated into what Anki needs."""

    stability: float
    difficulty: float
    reps: int
    lapses: int
    due_at: datetime


@dataclass(frozen=True, slots=True)
class ExportCard:
    front: str
    back: str
    #: One of `BASIC_TYPES` or `"cloze"`.
    type: str
    tags: tuple[str, ...]
    #: Absent for a new or mid-learning card — see the module docstring.
    schedule: ExportSchedule | None


def write(cards: list[ExportCard], *, deck_name: str, created: datetime) -> bytes:
    """Build a `.apkg` holding `cards` in a single deck named `deck_name`.

    `created` becomes the collection's creation time, and every card's `due_at`
    is stated as an offset from it — the same anchor the importer reads.
    """
    with tempfile.TemporaryDirectory() as workspace:
        db_path = Path(workspace) / "collection.anki2"
        connection = sqlite3.connect(db_path)
        try:
            _create_schema(connection)
            _write_header(connection, deck_name=deck_name, created=created)
            _write_cards(connection, cards, created=created)
            connection.commit()
        finally:
            connection.close()

        return _package(db_path)


def _package(db_path: Path) -> bytes:
    archive = db_path.parent / "export.apkg"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        package.write(db_path, "collection.anki2")
        # No media leaves with a card (see the module docstring), so the media
        # manifest — a required member of the package — maps nothing.
        package.writestr("media", "{}")
    return archive.read_bytes()


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE col (
            id integer primary key, crt integer not null, mod integer not null,
            scm integer not null, ver integer not null, dty integer not null,
            usn integer not null, ls integer not null, conf text not null,
            models text not null, decks text not null, dconf text not null,
            tags text not null
        );
        CREATE TABLE notes (
            id integer primary key, guid text not null, mid integer not null,
            mod integer not null, usn integer not null, tags text not null,
            flds text not null, sfld text not null, csum integer not null,
            flags integer not null, data text not null
        );
        CREATE TABLE cards (
            id integer primary key, nid integer not null, did integer not null,
            ord integer not null, mod integer not null, usn integer not null,
            type integer not null, queue integer not null, due integer not null,
            ivl integer not null, factor integer not null, reps integer not null,
            lapses integer not null, left integer not null, odue integer not null,
            odid integer not null, flags integer not null, data text not null
        );
        CREATE TABLE revlog (
            id integer primary key, cid integer not null, usn integer not null,
            ease integer not null, ivl integer not null, lastIvl integer not null,
            factor integer not null, time integer not null, type integer not null
        );
        CREATE TABLE graves (
            usn integer not null, oid integer not null, type integer not null
        );
        CREATE INDEX ix_notes_usn ON notes (usn);
        CREATE INDEX ix_cards_usn ON cards (usn);
        CREATE INDEX ix_cards_nid ON cards (nid);
        CREATE INDEX ix_cards_sched ON cards (did, queue, due);
        CREATE INDEX ix_revlog_cid ON revlog (cid);
        CREATE INDEX ix_notes_csum ON notes (csum);
        """
    )


def _write_header(
    connection: sqlite3.Connection, *, deck_name: str, created: datetime
) -> None:
    now_ms = int(created.timestamp() * 1000)
    crt = int(created.timestamp())

    models = {
        str(_BASIC_MODEL_ID): _basic_model(now_ms),
        str(_CLOZE_MODEL_ID): _cloze_model(now_ms),
    }
    decks = {
        str(_DEFAULT_DECK_ID): _deck(_DEFAULT_DECK_ID, "Default", now_ms),
        str(_DECK_ID): _deck(_DECK_ID, deck_name, now_ms),
    }
    dconf = {str(_DECK_CONF_ID): _deck_conf(now_ms)}
    conf = {
        "nextPos": 1,
        "estTimes": True,
        "activeDecks": [_DECK_ID],
        "sortType": "noteFld",
        "timeLim": 0,
        "sortBackwards": False,
        "addToCur": True,
        "curDeck": _DECK_ID,
        "newBury": True,
        "newSpread": 0,
        "dueCounts": True,
        "curModel": str(_BASIC_MODEL_ID),
        "collapseTime": 1200,
    }

    connection.execute(
        "INSERT INTO col VALUES (1,?,?,?,11,0,0,0,?,?,?,?,'{}')",
        (
            crt,
            now_ms,
            now_ms,
            json.dumps(conf),
            json.dumps(models),
            json.dumps(decks),
            json.dumps(dconf),
        ),
    )


def _basic_model(now_ms: int) -> dict[str, object]:
    return {
        "id": _BASIC_MODEL_ID,
        "name": "Basic",
        "type": 0,
        "mod": now_ms // 1000,
        "usn": -1,
        "sortf": 0,
        "did": _DECK_ID,
        "tmpls": [
            {
                "name": "Card 1",
                "ord": 0,
                "qfmt": "{{Front}}",
                "afmt": "{{FrontSide}}<hr id=answer>{{Back}}",
                "did": None,
                "bqfmt": "",
                "bafmt": "",
                "bfont": "Arial",
                "bsize": 12,
            }
        ],
        "flds": [_field("Front", 0), _field("Back", 1)],
        "css": _default_css(),
        "latexPre": "\\documentclass[12pt]{article}\n\\special{papersize=3in,5in}\n"
        "\\usepackage[utf8]{inputenc}\n\\usepackage{amssymb,amsmath}\n"
        "\\pagestyle{empty}\n\\setlength{\\parindent}{0in}\n\\begin{document}\n",
        "latexPost": "\\end{document}",
        "req": [[0, "any", [0]]],
        "tags": [],
        "vers": [],
    }


def _cloze_model(now_ms: int) -> dict[str, object]:
    return {
        "id": _CLOZE_MODEL_ID,
        "name": "Cloze",
        "type": 1,
        "mod": now_ms // 1000,
        "usn": -1,
        "sortf": 0,
        "did": _DECK_ID,
        "tmpls": [
            {
                "name": "Cloze",
                "ord": 0,
                "qfmt": "{{cloze:Text}}",
                "afmt": "{{cloze:Text}}<br>{{Extra}}",
                "did": None,
                "bqfmt": "",
                "bafmt": "",
                "bfont": "Arial",
                "bsize": 12,
            }
        ],
        "flds": [_field("Text", 0), _field("Extra", 1)],
        "css": _default_css() + "\n.cloze { font-weight: bold; color: blue; }",
        "latexPre": "\\documentclass[12pt]{article}\n\\special{papersize=3in,5in}\n"
        "\\usepackage[utf8]{inputenc}\n\\usepackage{amssymb,amsmath}\n"
        "\\pagestyle{empty}\n\\setlength{\\parindent}{0in}\n\\begin{document}\n",
        "latexPost": "\\end{document}",
        "req": [[0, "any", [0]]],
        "tags": [],
        "vers": [],
    }


def _field(name: str, ord_: int) -> dict[str, object]:
    return {
        "name": name,
        "ord": ord_,
        "sticky": False,
        "rtl": False,
        "font": "Arial",
        "size": 20,
        "media": [],
    }


def _default_css() -> str:
    return (
        ".card { font-family: arial; font-size: 20px; text-align: center; "
        "color: black; background-color: white; }"
    )


def _deck(deck_id: int, name: str, now_ms: int) -> dict[str, object]:
    return {
        "id": deck_id,
        "mod": now_ms // 1000,
        "name": name,
        "usn": -1,
        "lrnToday": [0, 0],
        "revToday": [0, 0],
        "newToday": [0, 0],
        "timeToday": [0, 0],
        "collapsed": True,
        "browserCollapsed": True,
        "desc": "",
        "dyn": 0,
        "conf": _DECK_CONF_ID,
        "extendNew": 10,
        "extendRev": 50,
    }


def _deck_conf(now_ms: int) -> dict[str, object]:
    return {
        "id": _DECK_CONF_ID,
        "mod": now_ms // 1000,
        "name": "Default",
        "usn": -1,
        "maxTaken": 60,
        "autoplay": True,
        "timer": 0,
        "replayq": True,
        "new": {
            "bury": False,
            "delays": [1, 10],
            "initialFactor": 2500,
            "ints": [1, 4, 0],
            "order": 1,
            "perDay": 20,
        },
        "rev": {
            "bury": False,
            "ease4": 1.3,
            "ivlFct": 1,
            "maxIvl": 36500,
            "perDay": 200,
            "hardFactor": 1.2,
        },
        "lapse": {
            "delays": [10],
            "leechAction": 1,
            "leechFails": 8,
            "minInt": 1,
            "mult": 0,
        },
    }


def _write_cards(
    connection: sqlite3.Connection, cards: list[ExportCard], *, created: datetime
) -> None:
    now_ms = int(created.timestamp() * 1000)
    # Anki ids are unique per table and conventionally millisecond timestamps;
    # two counters from the same instant satisfy both without ever colliding.
    note_ids = itertools.count(now_ms)
    card_ids = itertools.count(now_ms + 1_000_000_000)

    for position, card in enumerate(cards, start=1):
        fields = _fields_for(card)
        if fields is None:
            continue
        model_id = _CLOZE_MODEL_ID if card.type == "cloze" else _BASIC_MODEL_ID

        note_id = next(note_ids)
        sort_field = fields[0]
        connection.execute(
            "INSERT INTO notes VALUES (?,?,?,?,-1,?,?,?,?,0,'')",
            (
                note_id,
                token_urlsafe(8),
                model_id,
                now_ms // 1000,
                " ".join(card.tags),
                FIELD_SEPARATOR.join(fields),
                sort_field,
                _checksum(sort_field),
            ),
        )

        card_id = next(card_ids)
        type_, queue, due, ivl, factor, reps, lapses = _schedule_fields(
            card.schedule, created=created, position=position
        )
        connection.execute(
            "INSERT INTO cards VALUES (?,?,?,0,?,-1,?,?,?,?,?,?,?,0,0,0,0,'')",
            (
                card_id,
                note_id,
                _DECK_ID,
                now_ms // 1000,
                type_,
                queue,
                due,
                ivl,
                factor,
                reps,
                lapses,
            ),
        )


def _fields_for(card: ExportCard) -> tuple[str, str] | None:
    if card.type == "cloze":
        text = _cloze_text(card)
        if text is None:
            return None
        return (_render(text), "")
    if card.type not in BASIC_TYPES:
        # Notably `image`: media never left with the import, so it cannot leave
        # with the export either. The caller is expected to filter these out
        # ahead of time and count them as skipped; this is the backstop.
        return None
    return (_render(card.front), _render(card.back))


def _cloze_text(card: ExportCard) -> str | None:
    """The raw `{{c1::...}}` text Anki's cloze template expects.

    A card imported from Anki already carries this markup verbatim in `front`
    (the importer never expands it — see `noema.importers.anki`). A card
    generated inside NOEMA carries it pre-rendered instead, as `front` with the
    deletion blanked and `back` holding what was hidden, so it is rebuilt here.
    """
    if _CLOZE_MARKUP.search(card.front):
        return card.front

    match = _BLANK_PATTERN.search(card.front)
    if match is None:
        return None

    hint = match.group(1)
    if "}}" in card.back or (hint and "}}" in hint):
        # The answer itself would break out of the cloze markup it is being
        # placed inside. Better to leave the card behind than emit one that
        # reads wrong in Anki.
        return None

    deletion = f"{{{{c1::{card.back}::{hint}}}}}" if hint else f"{{{{c1::{card.back}}}}}"
    return _BLANK_PATTERN.sub(deletion, card.front, count=1)


def _render(text: str) -> str:
    """Markdown-ish plain text → the HTML Anki's field editor expects.

    The inverse of the importer's `_to_text`: escape first so a literal `<` in
    the source is not mistaken for markup, then turn line breaks into the only
    thing that renders as a line break in an Anki field.
    """
    return html.escape(text).replace("\n", "<br>")


def _schedule_fields(
    schedule: ExportSchedule | None, *, created: datetime, position: int
) -> tuple[int, int, int, int, int, int, int]:
    if schedule is None:
        # `type=0, queue=0`: new. `due` is queue position, not a date — see the
        # module docstring for why a mid-learning card also lands here.
        return (0, 0, position, 0, 0, 0, 0)

    due = max(MIN_INTERVAL_DAYS, (schedule.due_at - created).days)
    ivl = max(MIN_INTERVAL_DAYS, round(schedule.stability))
    factor = round(_ease(schedule.difficulty))
    return (2, 2, due, ivl, factor, max(0, schedule.reps), max(0, schedule.lapses))


def _ease(difficulty: float) -> float:
    """The inverse of `noema.importers.anki._difficulty`."""
    position = (difficulty - DIFFICULTY_MIN) / (DIFFICULTY_MAX - DIFFICULTY_MIN)
    ease = EASE_EASY - position * (EASE_EASY - EASE_HARD)
    return min(MAX_EASE, max(MIN_EASE, ease))


def _checksum(field: str) -> int:
    """Anki's own duplicate-detection checksum: the first 32 bits of a SHA-1."""
    digest = hashlib.sha1(field.encode()).hexdigest()  # noqa: S324 — Anki's format, not ours
    return int(digest[:8], 16)
