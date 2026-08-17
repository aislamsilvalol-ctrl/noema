"""Reading an Obsidian vault export.

An Obsidian vault is a plain folder of Markdown files — no proprietary format to
reverse-engineer, unlike Anki's SQLite. What this asks for is a zip of that
folder, made however the learner got their files into one: right-click the vault
folder and "Compress", or Obsidian's own export-as-zip if their platform has it.

Two things a vault has that a bare Markdown file does not:

* **Frontmatter.** A `---`-delimited YAML block at the top of a note, holding
  properties Obsidian's own UI reads. Parsing it would mean a YAML dependency
  for a feature this does not have anywhere to put — NOEMA notes have no
  properties panel — so it is stripped rather than parsed, the same "deliberately
  small" choice `noema.importers.anki` makes for HTML it cannot render either.
* **Wikilinks.** `[[Other Note]]` inside the body, which Obsidian resolves by
  title. These are read into `ImportedNote.links` as the titles they name, not
  resolved against the vault — resolving them needs the whole vault parsed
  first and the note IDs that only exist after the database write this module
  deliberately has no part of.

`.obsidian/` — the vault's own settings folder — and anything that is not a
`.md` file are not notes and are refused by name, in the same spirit as Anki
media: told plainly, not silently dropped.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath

__all__ = ["ImportedNote", "ObsidianImportError", "Result", "read"]

#: Obsidian's own link syntax: `[[Note]]`, `[[Note|Alias]]`, `[[Note#Heading]]`.
#: Only the target title is kept — an alias is what the *linking* note calls it,
#: not the name the target can be found under.
WIKILINK = re.compile(r"\[\[([^\]|#]+)")

#: A leading `---\n...\n---` block, Obsidian's property panel serialised as YAML.
FRONTMATTER = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n?", re.DOTALL)

#: The vault's own settings, never a note.
VAULT_CONFIG = ".obsidian/"


class ObsidianImportError(Exception):
    """The file cannot be read, with a sentence a learner can act on."""


@dataclass(frozen=True, slots=True)
class ImportedNote:
    title: str
    content_md: str
    #: Titles this note links to, in the order they first appear. Not resolved
    #: against the vault — see the module docstring.
    links: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Result:
    notes: tuple[ImportedNote, ...]
    #: Why files were dropped, counted by reason — an import that silently loses
    #: half a vault is worse than one that says it did.
    skipped: Counter[str]

    def summary(self) -> str:
        if not self.notes and not self.skipped:
            return "That file held no notes."

        text = f"{len(self.notes)} notes"
        if self.skipped:
            dropped = ", ".join(
                f"{count} {reason}" for reason, count in self.skipped.most_common()
            )
            text += f". Skipped: {dropped}"
        return f"{text}."


def read(data: bytes) -> Result:
    """Parse a zipped vault, returning notes and an account of what was skipped."""
    try:
        package = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise ObsidianImportError(
            "That file is not a readable zip archive. Compress the vault's "
            "folder — not a single note — and try again."
        ) from error

    with package:
        notes: list[ImportedNote] = []
        skipped: Counter[str] = Counter()
        seen_markdown = False

        for info in package.infolist():
            if info.is_dir():
                continue
            path = PurePosixPath(info.filename)
            if VAULT_CONFIG in info.filename:
                continue
            if path.suffix.lower() != ".md":
                skipped["not a Markdown file"] += 1
                continue

            seen_markdown = True
            note = _build(path, package.read(info), skipped=skipped)
            if note:
                notes.append(note)

        if not seen_markdown:
            raise ObsidianImportError(
                "That does not look like an Obsidian vault — it contains no "
                "Markdown files."
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

    body = FRONTMATTER.sub("", text, count=1).strip()
    if not body:
        skipped["empty"] += 1
        return None

    links = tuple(dict.fromkeys(match.strip() for match in WIKILINK.findall(body)))
    return ImportedNote(title=path.stem, content_md=body, links=links)
