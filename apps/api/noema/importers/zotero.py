"""Reading a Zotero CSL-JSON export.

Zotero's own "Export Library... CSL JSON" produces a plain JSON array of CSL
items — no proprietary format to reverse-engineer. CSL-JSON is a versioned,
publicly documented schema (the Citation Style Language specification,
docs.citationstyles.org), not a Zotero-specific guess: field names like `author`,
`issued`, `container-title`, `DOI` are part of that spec, so this reads any CSL-JSON
export, not only one that happened to come from Zotero.

Each reference becomes one note. There is no wikilink-equivalent in CSL-JSON —
Zotero's own collections and item relations are not exported to this format at
all — so `links` is always empty, the same as an Anki import's cards carry no
note links either.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

__all__ = ["ImportedNote", "Result", "ZoteroImportError", "read"]


class ZoteroImportError(Exception):
    """The file cannot be read, with a sentence a learner can act on."""


@dataclass(frozen=True, slots=True)
class ImportedNote:
    title: str
    content_md: str
    links: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Result:
    notes: tuple[ImportedNote, ...]
    #: Why items were dropped, counted by reason — an import that silently loses
    #: half a library is worse than one that says it did.
    skipped: Counter[str]

    def summary(self) -> str:
        if not self.notes and not self.skipped:
            return "That file held no references."

        text = f"{len(self.notes)} notes"
        if self.skipped:
            dropped = ", ".join(
                f"{count} {reason}" for reason, count in self.skipped.most_common()
            )
            text += f". Skipped: {dropped}"
        return f"{text}."


def read(data: bytes) -> Result:
    """Parse a CSL-JSON export, returning notes and an account of what was skipped."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ZoteroImportError("That file is not valid UTF-8 text.") from error

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise ZoteroImportError(
            "That file is not readable JSON. Export from Zotero as "
            "Export Library... CSL JSON, and use that file as is."
        ) from error

    if not isinstance(parsed, list):
        raise ZoteroImportError(
            "That does not look like a CSL-JSON export — it should be a JSON "
            "array of references, not a single object."
        )

    notes: list[ImportedNote] = []
    skipped: Counter[str] = Counter()
    for item in parsed:
        if not isinstance(item, dict):
            skipped["not a reference object"] += 1
            continue
        note = _build(item, skipped=skipped)
        if note:
            notes.append(note)

    return Result(notes=tuple(notes), skipped=skipped)


def _build(item: dict[str, Any], *, skipped: Counter[str]) -> ImportedNote | None:
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        skipped["no title"] += 1
        return None

    body = "\n\n".join(part for part in _sections(item) if part)
    return ImportedNote(title=title.strip(), content_md=body, links=())


def _sections(item: dict[str, Any]) -> list[str]:
    return [_byline(item), _abstract(item), _note(item)]


def _byline(item: dict[str, Any]) -> str:
    """`Author One, Author Two (2024). Container Title. DOI/URL.` — everything a
    citation needs to be found again, minus the formatting rules of any one style;
    this is a note body, not a bibliography entry."""
    names = [n for n in (_name(author) for author in item.get("author") or []) if n]
    year = _year(item)
    container = item.get("container-title")
    doi = item.get("DOI")
    url = item.get("URL")

    head = ", ".join(names) if names else ""
    if year:
        head = f"{head} ({year})" if head else f"({year})"
    if container:
        head = f"{head}. {container}" if head else str(container)
    if head and not head.endswith("."):
        head += "."

    identifier = f"https://doi.org/{doi}" if doi else url
    if identifier:
        head = f"{head} {identifier}" if head else str(identifier)
    return head.strip()


def _name(author: Any) -> str:
    if not isinstance(author, dict):
        return ""
    literal = author.get("literal")
    if isinstance(literal, str) and literal.strip():
        return literal.strip()
    given = author.get("given") or ""
    family = author.get("family") or ""
    return " ".join(part for part in (given, family) if part).strip()


def _year(item: dict[str, Any]) -> str:
    issued = item.get("issued")
    if not isinstance(issued, dict):
        return ""
    parts = issued.get("date-parts")
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
        return ""
    first = parts[0]
    return str(first[0]) if first else ""


def _abstract(item: dict[str, Any]) -> str:
    abstract = item.get("abstract")
    return abstract.strip() if isinstance(abstract, str) else ""


def _note(item: dict[str, Any]) -> str:
    note = item.get("note")
    return note.strip() if isinstance(note, str) else ""
