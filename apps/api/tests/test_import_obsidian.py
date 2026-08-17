"""Reading zipped Obsidian vaults."""

from __future__ import annotations

import io
import zipfile

import pytest

from noema.importers.obsidian import ImportedNote, ObsidianImportError, read


def zip_of(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def only(notes: tuple[ImportedNote, ...]) -> ImportedNote:
    assert len(notes) == 1, f"expected one note, got {len(notes)}"
    return notes[0]


# ── The notes themselves ──────────────────────────────────────────────────────


def test_a_plain_note_comes_across() -> None:
    result = read(zip_of({"Mitochondria.md": "The powerhouse of the cell."}))

    note = only(result.notes)
    assert note.title == "Mitochondria"
    assert note.content_md == "The powerhouse of the cell."
    assert note.links == ()


def test_frontmatter_is_stripped() -> None:
    text = "---\ntags: [biology]\ncreated: 2024-01-01\n---\nThe body of the note."
    result = read(zip_of({"Note.md": text}))

    assert only(result.notes).content_md == "The body of the note."


def test_a_note_that_is_only_frontmatter_is_skipped_as_empty() -> None:
    result = read(zip_of({"Note.md": "---\ntags: [x]\n---\n"}))

    assert result.notes == ()
    assert result.skipped["empty"] == 1


def test_wikilinks_are_read_as_the_titles_they_name() -> None:
    result = read(zip_of({"Note.md": "See [[Mitochondria]] and [[Cell Wall]]."}))

    assert only(result.notes).links == ("Mitochondria", "Cell Wall")


def test_a_wikilink_alias_keeps_only_the_target_title() -> None:
    result = read(zip_of({"Note.md": "See [[Mitochondria|the powerhouse]]."}))

    assert only(result.notes).links == ("Mitochondria",)


def test_a_wikilink_to_a_heading_keeps_only_the_note_title() -> None:
    result = read(zip_of({"Note.md": "See [[Mitochondria#Structure]]."}))

    assert only(result.notes).links == ("Mitochondria",)


def test_a_repeated_wikilink_is_kept_once() -> None:
    result = read(zip_of({"Note.md": "[[Mitochondria]] again: [[Mitochondria]]."}))

    assert only(result.notes).links == ("Mitochondria",)


def test_nested_folders_are_read() -> None:
    result = read(zip_of({"Biology/Cells/Mitochondria.md": "Text."}))

    assert only(result.notes).title == "Mitochondria"


def test_the_vault_settings_folder_is_not_a_note() -> None:
    result = read(
        zip_of(
            {
                "Note.md": "Text.",
                ".obsidian/workspace.json": "{}",
                ".obsidian/plugins/foo/data.json": "{}",
            }
        )
    )

    assert len(result.notes) == 1
    assert "not a Markdown file" not in result.skipped


def test_a_non_markdown_file_is_skipped_and_counted() -> None:
    result = read(zip_of({"Note.md": "Text.", "diagram.png": "not really a png"}))

    assert len(result.notes) == 1
    assert result.skipped["not a Markdown file"] == 1


def test_many_notes_all_arrive() -> None:
    files = {f"Note {i}.md": f"Body {i}" for i in range(20)}

    result = read(zip_of(files))

    assert {note.title for note in result.notes} == {f"Note {i}" for i in range(20)}


# ── Refusals ───────────────────────────────────────────────────────────────────


def test_a_file_that_is_not_a_zip_is_refused() -> None:
    with pytest.raises(ObsidianImportError):
        read(b"not a zip file at all")


def test_a_zip_with_no_markdown_in_it_is_refused() -> None:
    with pytest.raises(ObsidianImportError):
        read(zip_of({"photo.jpg": "not really a photo"}))


def test_an_empty_zip_is_refused() -> None:
    with pytest.raises(ObsidianImportError):
        read(zip_of({}))
