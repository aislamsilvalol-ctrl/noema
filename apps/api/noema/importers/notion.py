"""Reading a Notion export.

Notion's "Export → Markdown & CSV" produces a zip with no proprietary format
either, so this reads it the same way `noema.importers.obsidian` reads a vault —
but the shape is different enough to need its own reader:

* **Every filename carries a 32-character hex id**, appended to the title Notion
  uses to keep siblings with the same name apart — `Cell Biology
  1a2b3c4d5e6f78901a2b3c4d5e6f7890.md`. Stripped here, so the note arrives under
  the title a person actually gave it.
* **Sub-pages are folders**, named the same way, holding their children's `.md`
  files. Folder structure carries no meaning NOEMA's flat notebook does not
  already have, so only the leaf title is kept — the same choice the Obsidian
  reader makes for nested folders.
* **A database exports twice**: once as a `.csv` summary, and once as a folder
  holding one `.md` page per row. The `.csv` is a duplicate of pages already
  being read from that folder, not a note of its own, and is refused by name
  rather than silently skipped or, worse, imported as a second copy of the same
  material.
* **Links between pages are ordinary Markdown links** to another export file —
  `[Cell Biology](Cell%20Biology%201a2b...7890.md)` — not a wiki-link syntax, so
  the title is read from the link's target file, not its visible text.

Property values a database row page carries at the top of its Markdown are left
in the body rather than parsed out: Notion does not document that layout as a
stable format, and getting it wrong would eat real content rather than merely
leave a few extra lines — the same tradeoff the Obsidian reader makes by leaving
frontmatter's *presence* handled and its *fields* alone.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import unquote

__all__ = ["ImportedNote", "NotionImportError", "Result", "read"]

#: Notion appends this to every exported filename: the page id, hyphens removed.
_ID_SUFFIX = re.compile(r" [0-9a-f]{32}$")

#: A Markdown link whose target is another file from this same export.
_PAGE_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+\.md)\)")


class NotionImportError(Exception):
    """The file cannot be read, with a sentence a learner can act on."""


@dataclass(frozen=True, slots=True)
class ImportedNote:
    title: str
    content_md: str
    #: Titles this note links to, in the order they first appear. Read from the
    #: linked file's name, not resolved against the export — see the module
    #: docstring on why that stays the caller's job.
    links: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Result:
    notes: tuple[ImportedNote, ...]
    #: Why files were dropped, counted by reason — an import that silently loses
    #: half a workspace is worse than one that says it did.
    skipped: Counter[str]

    def summary(self) -> str:
        if not self.notes and not self.skipped:
            return "That file held no pages."

        text = f"{len(self.notes)} pages"
        if self.skipped:
            dropped = ", ".join(
                f"{count} {reason}" for reason, count in self.skipped.most_common()
            )
            text += f". Skipped: {dropped}"
        return f"{text}."


def read(data: bytes) -> Result:
    """Parse a zipped Notion export, returning pages and what was skipped."""
    try:
        package = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise NotionImportError(
            "That file is not a readable zip archive. In Notion, use "
            "Export → Markdown & CSV, and upload the zip it produces."
        ) from error

    with package:
        notes: list[ImportedNote] = []
        skipped: Counter[str] = Counter()
        seen_markdown = False

        for info in package.infolist():
            if info.is_dir():
                continue
            path = PurePosixPath(info.filename)
            suffix = path.suffix.lower()

            if suffix == ".csv":
                skipped["a database summary (its rows are imported as pages)"] += 1
                continue
            if suffix != ".md":
                skipped["not a Markdown file"] += 1
                continue

            seen_markdown = True
            note = _build(path, package.read(info), skipped=skipped)
            if note:
                notes.append(note)

        if not seen_markdown:
            raise NotionImportError(
                "That does not look like a Notion export — it contains no Markdown files."
            )

        return Result(notes=tuple(notes), skipped=skipped)


def _build(
    path: PurePosixPath, raw: bytes, *, skipped: Counter[str]
) -> ImportedNote | None:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        skipped["not valid UTF-8 text"] += 1
        return None

    title = _title_from_filename(path.stem)
    body = _strip_redundant_heading(text.strip(), title)
    if not body:
        skipped["empty"] += 1
        return None

    links = tuple(dict.fromkeys(_linked_titles(body)))
    return ImportedNote(title=title, content_md=body, links=links)


def _title_from_filename(stem: str) -> str:
    return _ID_SUFFIX.sub("", stem).strip() or "Untitled"


def _strip_redundant_heading(body: str, title: str) -> str:
    """Notion often opens a page's Markdown with `# <its own title>`.

    Kept as the note's own `title` field rather than duplicated in the body a
    second time — same reasoning as trimming a note's filename, applied to its
    first line instead.
    """
    first_line, _, rest = body.partition("\n")
    heading = first_line.removeprefix("#").strip()
    if heading.casefold() == title.casefold():
        return rest.strip()
    return body


def _linked_titles(body: str) -> list[str]:
    titles = []
    for match in _PAGE_LINK.finditer(body):
        target = PurePosixPath(unquote(match.group(1)))
        titles.append(_title_from_filename(target.stem))
    return titles
