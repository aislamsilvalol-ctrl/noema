"""Reading a Zotero CSL-JSON export."""

from __future__ import annotations

import json

import pytest

from noema.importers.zotero import ImportedNote, ZoteroImportError, read


def only(notes: tuple[ImportedNote, ...]) -> ImportedNote:
    assert len(notes) == 1, f"expected one note, got {len(notes)}"
    return notes[0]


def csl(*items: dict[str, object]) -> bytes:
    return json.dumps(list(items)).encode()


# ── The notes themselves ──────────────────────────────────────────────────────


def test_title_becomes_the_note_title() -> None:
    result = read(csl({"id": "x", "type": "article-journal", "title": "The Chain Rule"}))

    assert only(result.notes).title == "The Chain Rule"


def test_authors_year_container_and_doi_form_the_byline() -> None:
    result = read(
        csl(
            {
                "id": "x",
                "type": "article-journal",
                "title": "The Chain Rule Revisited",
                "author": [
                    {"family": "Smith", "given": "Jane"},
                    {"family": "Doe", "given": "Alan"},
                ],
                "issued": {"date-parts": [[2020, 5]]},
                "container-title": "Journal of Calculus",
                "DOI": "10.1234/jc.2020.001",
            }
        )
    )

    body = only(result.notes).content_md
    assert body == (
        "Jane Smith, Alan Doe (2020). Journal of Calculus. "
        "https://doi.org/10.1234/jc.2020.001"
    )


def test_a_url_is_used_when_there_is_no_doi() -> None:
    result = read(
        csl(
            {
                "id": "x",
                "type": "webpage",
                "title": "An Article",
                "URL": "https://example.com/article",
            }
        )
    )

    assert "https://example.com/article" in only(result.notes).content_md


def test_a_doi_is_preferred_over_a_url_when_both_are_present() -> None:
    result = read(
        csl(
            {
                "id": "x",
                "type": "article-journal",
                "title": "An Article",
                "DOI": "10.1/x",
                "URL": "https://example.com/article",
            }
        )
    )

    body = only(result.notes).content_md
    assert "https://doi.org/10.1/x" in body
    assert "example.com" not in body


def test_a_literal_author_name_is_used_as_is() -> None:
    """CSL allows a corporate/organizational author with no given/family split."""
    result = read(
        csl(
            {
                "id": "x",
                "type": "report",
                "title": "Annual Report",
                "author": [{"literal": "World Health Organization"}],
            }
        )
    )

    assert "World Health Organization" in only(result.notes).content_md


def test_abstract_and_note_fields_are_included() -> None:
    result = read(
        csl(
            {
                "id": "x",
                "type": "article-journal",
                "title": "An Article",
                "abstract": "A survey of the chain rule.",
                "note": "Read before the exam.",
            }
        )
    )

    body = only(result.notes).content_md
    assert "A survey of the chain rule." in body
    assert "Read before the exam." in body


def test_an_item_with_nothing_but_a_title_still_produces_a_note() -> None:
    result = read(csl({"id": "x", "type": "webpage", "title": "Bare"}))

    note = only(result.notes)
    assert note.title == "Bare"
    assert note.content_md == ""


def test_notes_carry_no_links() -> None:
    """CSL-JSON has no wikilink equivalent — collections/relations aren't exported."""
    result = read(csl({"id": "x", "type": "webpage", "title": "x"}))

    assert only(result.notes).links == ()


# ── What gets skipped ────────────────────────────────────────────────────────


def test_an_item_with_no_title_is_skipped() -> None:
    result = read(csl({"id": "x", "type": "webpage"}))

    assert result.notes == ()
    assert result.skipped["no title"] == 1


def test_an_item_with_a_blank_title_is_skipped() -> None:
    result = read(csl({"id": "x", "type": "webpage", "title": "   "}))

    assert result.skipped["no title"] == 1


def test_a_non_object_array_entry_is_skipped() -> None:
    data = json.dumps(["not an object", {"id": "x", "type": "webpage", "title": "Real"}])

    result = read(data.encode())

    assert len(result.notes) == 1
    assert result.skipped["not a reference object"] == 1


# ── Failure ───────────────────────────────────────────────────────────────────


def test_malformed_json_is_refused() -> None:
    with pytest.raises(ZoteroImportError, match="not readable JSON"):
        read(b"not json at all")


def test_a_non_array_top_level_value_is_refused() -> None:
    with pytest.raises(ZoteroImportError, match="JSON array"):
        read(json.dumps({"items": []}).encode())


def test_non_utf8_bytes_are_refused() -> None:
    with pytest.raises(ZoteroImportError, match="UTF-8"):
        read(b"\xff\xfe\x00\x01")


# ── Summary ───────────────────────────────────────────────────────────────────


def test_summary_reports_notes_and_skips() -> None:
    result = read(
        csl(
            {"id": "a", "type": "webpage", "title": "Kept"},
            {"id": "b", "type": "webpage"},
        )
    )

    assert result.summary() == "1 notes. Skipped: 1 no title."


def test_summary_of_an_empty_export() -> None:
    assert read(csl()).summary() == "That file held no references."
