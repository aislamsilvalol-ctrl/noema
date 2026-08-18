"""Reading zipped Notion exports."""

from __future__ import annotations

import io
import zipfile

import pytest

from noema.importers.notion import ImportedNote, NotionImportError, read

HASH_A = "1a2b3c4d5e6f78901a2b3c4d5e6f7890"
HASH_B = "aabbccddeeff00112233445566778899"


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


def test_the_id_suffix_is_stripped_from_the_title() -> None:
    result = read(zip_of({f"Cell Biology {HASH_A}.md": "Body text."}))

    assert only(result.notes).title == "Cell Biology"


def test_a_title_with_no_id_suffix_is_kept_as_is() -> None:
    result = read(zip_of({"Cell Biology.md": "Body text."}))

    assert only(result.notes).title == "Cell Biology"


def test_a_redundant_leading_heading_is_moved_into_the_title_field() -> None:
    result = read(
        zip_of({f"Cell Biology {HASH_A}.md": "# Cell Biology\n\nThe real content."})
    )

    note = only(result.notes)
    assert note.title == "Cell Biology"
    assert note.content_md == "The real content."


def test_a_heading_that_differs_from_the_title_is_kept_in_the_body() -> None:
    result = read(zip_of({f"Cell Biology {HASH_A}.md": "# Something else\n\nContent."}))

    assert only(result.notes).content_md == "# Something else\n\nContent."


def test_nested_sub_page_folders_are_read() -> None:
    result = read(zip_of({f"Parent {HASH_A}/Child {HASH_B}.md": "Child content."}))

    assert only(result.notes).title == "Child"


def test_many_pages_all_arrive() -> None:
    files = {f"Page {i} {HASH_A}.md": f"Body {i}" for i in range(20)}

    result = read(zip_of(files))

    assert {note.title for note in result.notes} == {f"Page {i}" for i in range(20)}


# ── Links ──────────────────────────────────────────────────────────────────────


def test_a_link_to_another_export_file_is_read_by_its_target_title() -> None:
    body = f"See [the other page](Mitochondria%20{HASH_B}.md) for more."
    result = read(zip_of({f"Note {HASH_A}.md": body}))

    assert only(result.notes).links == ("Mitochondria",)


def test_a_link_into_a_sub_page_folder_is_read_by_the_files_own_title() -> None:
    body = f"See [it](Parent%20{HASH_A}/Child%20{HASH_B}.md)."
    result = read(zip_of({f"Note {HASH_A}.md": body}))

    assert only(result.notes).links == ("Child",)


def test_a_repeated_link_is_kept_once() -> None:
    body = f"[a]({HASH_A}.md) and again [b]({HASH_A}.md)."
    result = read(zip_of({f"Note {HASH_B}.md": body}))

    assert len(only(result.notes).links) == 1


def test_an_external_link_is_not_read_as_a_page_link() -> None:
    result = read(
        zip_of({f"Note {HASH_A}.md": "See [Wikipedia](https://en.wikipedia.org)."})
    )

    assert only(result.notes).links == ()


# ── What gets skipped ────────────────────────────────────────────────────────


def test_a_database_csv_summary_is_skipped_not_imported_as_a_note() -> None:
    result = read(
        zip_of(
            {
                f"Tasks {HASH_A}.csv": "Name,Status\nA,Done\n",
                f"Tasks {HASH_A}/A {HASH_B}.md": "Row content.",
            }
        )
    )

    assert len(result.notes) == 1
    assert result.skipped["a database summary (its rows are imported as pages)"] == 1


def test_an_attachment_is_skipped_and_counted() -> None:
    result = read(
        zip_of({f"Note {HASH_A}.md": "Text.", "diagram.png": "not really a png"})
    )

    assert len(result.notes) == 1
    assert result.skipped["not a Markdown file"] == 1


def test_an_empty_page_is_skipped_as_empty() -> None:
    result = read(zip_of({f"Note {HASH_A}.md": "   \n\n  "}))

    assert result.notes == ()
    assert result.skipped["empty"] == 1


# ── Refusals ───────────────────────────────────────────────────────────────────


def test_a_file_that_is_not_a_zip_is_refused() -> None:
    with pytest.raises(NotionImportError):
        read(b"not a zip file at all")


def test_a_zip_with_no_markdown_in_it_is_refused() -> None:
    with pytest.raises(NotionImportError):
        read(zip_of({"photo.jpg": "not really a photo"}))


def test_an_empty_zip_is_refused() -> None:
    with pytest.raises(NotionImportError):
        read(zip_of({}))
