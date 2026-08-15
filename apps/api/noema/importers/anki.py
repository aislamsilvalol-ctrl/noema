"""Reading an Anki `.apkg` export.

An `.apkg` is a zip holding a SQLite database and the media that goes with it.
Nothing here is documented as a public format, so this reads the tables it needs
and refuses politely when it meets a shape it does not recognise, rather than
guessing and importing nonsense.

**Scheduling history is the point.** Anyone can re-enter card text; nobody can
re-earn four years of intervals. So the intervals come across, and the mapping
below is an approximation stated out loud rather than a silent conversion:

* Anki's interval is the number of days it decided to wait. FSRS stability is
  the interval at which recall probability falls to 90%. These are close enough
  in meaning that carrying the interval over as stability puts a card back where
  it was, give or take a day — far closer than the alternative, which is
  starting from zero and re-reviewing thousands of cards you already know.
* Anki's ease factor and FSRS difficulty both mean "how hard is this for you",
  in opposite directions and on different scales. The map below is monotonic and
  approximately right; it is not a conversion anyone should treat as exact.

The imported schedule is therefore an informed starting position, and FSRS will
correct it from the learner's next few reviews. That is the honest claim, and it
is the one the importer makes in the interface.

Two deliberate refusals:

* `collection.anki21b` is zstd-compressed. Supporting it means a dependency
  carried by every install, to read a file Anki can export in another format on
  request, so this asks for that export instead of taking the dependency.
* Media is not imported. A card whose answer is an image would come across as a
  card with a missing answer, which is worse than being told plainly that it was
  skipped and why.
"""

from __future__ import annotations

import html
import json
import re
import sqlite3
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

__all__ = ["AnkiImportError", "ImportedCard", "ImportedSchedule", "Result", "read"]

#: Anki separates a note's fields with this character.
FIELD_SEPARATOR = "\x1f"

#: `{{c1::...}}` — the same syntax `noema.engines.cloze` already expands, so a
#: cloze note needs no rewriting at all. Detected from the text rather than from
#: the note type, because the note type is stored as protobuf in newer
#: collections and the text is unambiguous in every version.
CLOZE = re.compile(r"\{\{c\d+::")

#: Anki's card types, in the order the schema numbers them.
STATES = {0: "new", 1: "learning", 2: "review", 3: "relearning"}

#: Below this, a card was never really studied — Anki uses the `due` column for
#: something else entirely in the new queue, and reading it as a date produces
#: dates in 1970 or 2050. Such cards come across unscheduled.
STUDIED = {"review", "relearning"}

#: Anki ease is permille, floored at 1300 by the algorithm and typically 2500 on
#: a fresh card. FSRS difficulty runs 1 (easy) to 10 (hard), the other way round.
EASE_EASY = 3100.0
EASE_HARD = 1300.0
DIFFICULTY_MIN = 1.0
DIFFICULTY_MAX = 10.0
DEFAULT_DIFFICULTY = 5.0

#: An interval of zero would tell FSRS the card is due immediately and known not
#: at all, which is false for a card that has been reviewed. Half a day is the
#: smallest honest floor.
MIN_STABILITY = 0.5


class AnkiImportError(Exception):
    """The file cannot be read, with a sentence a learner can act on."""


@dataclass(frozen=True, slots=True)
class ImportedSchedule:
    """Where Anki had this card, translated into what FSRS needs."""

    stability: float
    difficulty: float
    reps: int
    lapses: int
    state: str
    due_at: datetime


@dataclass(frozen=True, slots=True)
class ImportedCard:
    front: str
    back: str
    #: "basic", "reverse" or "cloze" — matching `noema.db.models.CardType`.
    type: str
    tags: tuple[str, ...]
    deck: str
    #: Absent for a card Anki had never scheduled. Importing those as new is
    #: correct: they were new.
    schedule: ImportedSchedule | None


@dataclass(frozen=True, slots=True)
class Result:
    cards: tuple[ImportedCard, ...]
    #: Why rows were dropped, counted by reason. Shown to the learner: an import
    #: that silently loses 300 cards is worse than one that says it did.
    skipped: Counter[str]

    def summary(self) -> str:
        if not self.cards and not self.skipped:
            return "That file held no cards."

        scheduled = sum(1 for card in self.cards if card.schedule)
        text = f"{len(self.cards)} cards, {scheduled} with their review history"
        if self.skipped:
            dropped = ", ".join(
                f"{count} {reason}" for reason, count in self.skipped.most_common()
            )
            text += f". Skipped: {dropped}"
        return f"{text}."


def read(data: bytes) -> Result:
    """Parse an `.apkg`, returning cards and an account of what was skipped."""
    with tempfile.TemporaryDirectory() as workspace:
        collection = _extract(data, Path(workspace))
        # Read-only, and via URI so SQLite cannot be talked into writing to the
        # learner's uploaded file.
        connection = sqlite3.connect(f"file:{collection}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            return _read_collection(connection)
        except sqlite3.DatabaseError as error:  # pragma: no cover - corrupt files
            raise AnkiImportError(
                "That file's database could not be read. It may be damaged — "
                "try exporting it from Anki again."
            ) from error
        finally:
            connection.close()


def _extract(data: bytes, workspace: Path) -> Path:
    archive = workspace / "package.apkg"
    archive.write_bytes(data)

    try:
        with zipfile.ZipFile(archive) as package:
            names = set(package.namelist())

            # `anki21` is the newer schema and wins when both are present; the
            # older `anki2` is then a stub kept for backwards compatibility and
            # reading it would import an empty collection.
            for candidate in ("collection.anki21", "collection.anki2"):
                if candidate in names:
                    target = workspace / candidate
                    target.write_bytes(package.read(candidate))
                    return target

            if "collection.anki21b" in names:
                raise AnkiImportError(
                    "That export uses Anki's newer compressed format. In Anki, "
                    "export again with “Support older Anki versions” ticked, and "
                    "this will read it."
                )

            raise AnkiImportError(
                "That does not look like an Anki export — it contains no collection."
            )
    except zipfile.BadZipFile as error:
        raise AnkiImportError(
            "That file is not a readable .apkg. An .apkg is a zip archive; this "
            "one could not be opened as one."
        ) from error


def _read_collection(connection: sqlite3.Connection) -> Result:
    created = _created_at(connection)
    decks = _deck_names(connection)

    cards: list[ImportedCard] = []
    skipped: Counter[str] = Counter()

    query = """
        SELECT c.ord, c.type, c.due, c.ivl, c.factor, c.reps, c.lapses, c.did,
               n.flds, n.tags
        FROM cards c JOIN notes n ON n.id = c.nid
    """
    for row in connection.execute(query):
        card = _build(row, created=created, decks=decks, skipped=skipped)
        if card:
            cards.append(card)

    return Result(cards=tuple(cards), skipped=skipped)


def _build(
    row: sqlite3.Row,
    *,
    created: datetime,
    decks: dict[int, str],
    skipped: Counter[str],
) -> ImportedCard | None:
    fields = [_to_text(field) for field in str(row["flds"]).split(FIELD_SEPARATOR)]
    fields = [field for field in fields if field]

    if not fields:
        skipped["empty"] += 1
        return None

    is_cloze = bool(CLOZE.search(fields[0]))

    if is_cloze:
        front, back = fields[0], ""
    elif len(fields) < 2:
        # A card with a question and no answer cannot be reviewed. Usually the
        # answer was an image, which is not imported.
        skipped["missing an answer, or answered only with media"] += 1
        return None
    else:
        front, back = fields[0], fields[1]

    ordinal = int(row["ord"])
    if is_cloze:
        card_type = "cloze"
    elif ordinal > 0:
        # Anki generates one card per template; the second is conventionally the
        # reverse. Beyond that the templates are arbitrary and cannot be mapped
        # without rendering them, so front and back stay as they are.
        card_type = "reverse"
    else:
        card_type = "basic"

    if card_type == "reverse":
        front, back = back, front

    return ImportedCard(
        front=front,
        back=back,
        type=card_type,
        tags=tuple(sorted({tag for tag in str(row["tags"]).split() if tag})),
        deck=decks.get(int(row["did"]), "Imported"),
        schedule=_schedule(row, created=created),
    )


def _schedule(row: sqlite3.Row, *, created: datetime) -> ImportedSchedule | None:
    state = STATES.get(int(row["type"]))
    if state not in STUDIED:
        return None

    interval = int(row["ivl"])
    if interval <= 0:
        # Negative intervals are seconds, used while a card is still in learning.
        # Such a card has no meaningful long-term stability yet.
        return None

    # For a review card, `due` counts days from the collection's creation day.
    due_at = created + timedelta(days=int(row["due"]))

    return ImportedSchedule(
        stability=max(MIN_STABILITY, float(interval)),
        difficulty=_difficulty(float(row["factor"])),
        reps=max(0, int(row["reps"])),
        lapses=max(0, int(row["lapses"])),
        state="review",
        due_at=due_at,
    )


def _difficulty(ease: float) -> float:
    """Anki ease → FSRS difficulty: monotonic, inverted, clamped.

    A card that was never given an ease (factor 0) gets the FSRS default rather
    than being called maximally hard, which is what the raw arithmetic would
    say and would bury a fine card at the top of every queue.
    """
    if ease <= 0:
        return DEFAULT_DIFFICULTY

    position = (EASE_EASY - ease) / (EASE_EASY - EASE_HARD)
    difficulty = DIFFICULTY_MIN + position * (DIFFICULTY_MAX - DIFFICULTY_MIN)
    return min(DIFFICULTY_MAX, max(DIFFICULTY_MIN, difficulty))


def _created_at(connection: sqlite3.Connection) -> datetime:
    row = connection.execute("SELECT crt FROM col LIMIT 1").fetchone()
    if row is None:
        raise AnkiImportError(
            "That collection has no header row, so it cannot be read. Try "
            "exporting it from Anki again."
        )
    return datetime.fromtimestamp(int(row["crt"]), tz=UTC)


def _deck_names(connection: sqlite3.Connection) -> dict[int, str]:
    """Deck names, from whichever of the two layouts this collection uses."""
    if _has_table(connection, "decks"):
        # Newer collections keep decks in their own table, with `\x1f` between
        # the levels of a nested name.
        return {
            int(row["id"]): str(row["name"]).replace(FIELD_SEPARATOR, "::")
            for row in connection.execute("SELECT id, name FROM decks")
        }

    row = connection.execute("SELECT decks FROM col LIMIT 1").fetchone()
    if row is None or not row["decks"]:
        return {}

    try:
        blob = json.loads(row["decks"])
    except (json.JSONDecodeError, TypeError):  # pragma: no cover - corrupt files
        return {}

    return {int(key): str(deck.get("name", "Imported")) for key, deck in blob.items()}


def _has_table(connection: sqlite3.Connection, name: str) -> bool:
    found = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return found is not None


def _to_text(field: str) -> str:
    """Anki fields are HTML fragments; cards here are Markdown.

    Deliberately small: a real HTML-to-Markdown conversion would need a
    dependency and would still get someone's hand-written CSS wrong. Line breaks
    are what actually carry meaning in a flashcard, so those are preserved and
    the rest of the markup is dropped.
    """
    text = re.sub(r"(?i)<\s*(br|/div|/p|/li)\s*/?\s*>", "\n", field)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    # Collapse the runs of blank lines that stripping tags tends to leave.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()
