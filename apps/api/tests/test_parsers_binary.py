"""PDF and DOCX parsing.

Fixtures are generated with the same libraries that read them, so these tests carry
no binary blobs and stay readable in review. They skip where the optional
dependency is absent, which is the same contract the parsers themselves honour.
"""

from __future__ import annotations

import io

import pytest

from noema.db.models import SourceKind
from noema.ingestion.ir import BlockKind
from noema.ingestion.parsers import available, parse_source
from noema.ingestion.parsers.documents import ParseFailed, parse_docx, parse_pdf

pymupdf = pytest.importorskip("pymupdf", reason="PDF support is an optional extra")
docx = pytest.importorskip("docx", reason="DOCX support is an optional extra")

BODY = 11.0
TITLE = 24.0
SECTION = 15.0


def make_pdf(pages: list[list[tuple[str, float]]]) -> bytes:
    """Build a PDF from (text, font size) lines per page."""
    document = pymupdf.open()
    for lines in pages:
        page = document.new_page()
        y = 72.0
        for text, size in lines:
            page.insert_text((72, y), text, fontsize=size)
            y += size * 2.2
    return bytes(document.tobytes())


def make_docx(build) -> bytes:  # type: ignore[no-untyped-def]
    document = docx.Document()
    build(document)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# ── PDF ───────────────────────────────────────────────────────────────────────


def test_pdf_text_is_extracted_with_page_anchors() -> None:
    data = make_pdf(
        [
            [("Optimization", TITLE), ("Gradient descent steps downhill.", BODY)],
            [("It converges for convex functions.", BODY)],
        ]
    )

    document = parse_pdf(data, ocr=False)

    assert document.page_count == 2
    assert "Gradient descent" in document.text
    pages = {block.page for block in document.blocks}
    assert pages == {1, 2}, "every block must carry the page it came from"


def test_larger_type_is_inferred_as_a_heading() -> None:
    """PDFs have no heading markup, so the structure has to come from font size."""
    data = make_pdf(
        [
            [("Optimization", TITLE)]
            + [(f"Body line {i} at normal size.", BODY) for i in range(6)]
        ]
    )

    document = parse_pdf(data, ocr=False)
    headings = [b for b in document.blocks if b.kind is BlockKind.HEADING]

    assert [h.text for h in headings] == ["Optimization"]
    assert headings[0].page == 1


def test_two_heading_sizes_produce_two_levels() -> None:
    data = make_pdf(
        [
            [("Chapter", TITLE), ("Section", SECTION)]
            + [(f"Body line {i} at normal size.", BODY) for i in range(6)]
        ]
    )

    document = parse_pdf(data, ocr=False)
    levels = [b.level for b in document.blocks if b.kind is BlockKind.HEADING]

    assert levels == sorted(levels), "a bigger heading must not sort below a smaller one"
    assert len(set(levels)) == 2


def test_wrapped_lines_are_rejoined_into_paragraphs() -> None:
    """Extraction yields one block per visual line; unjoined, every chunk boundary
    would land mid-sentence and citations would quote half a clause."""
    data = make_pdf(
        [
            [
                ("The gradient of a function points in the direction of", BODY),
                ("steepest ascent, so descent follows its negative.", BODY),
            ]
        ]
    )

    document = parse_pdf(data, ocr=False)

    assert any(
        "steepest ascent" in b.text and "gradient" in b.text for b in document.blocks
    )


def test_a_page_ending_in_a_full_stop_starts_a_new_paragraph() -> None:
    data = make_pdf([[("First sentence ends here.", BODY), ("Second one begins.", BODY)]])

    document = parse_pdf(data, ocr=False)
    paragraphs = [b for b in document.blocks if b.kind is BlockKind.PARAGRAPH]

    assert len(paragraphs) == 2


def test_pdf_metadata_is_kept_when_present() -> None:
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "Body text.", fontsize=BODY)
    document.set_metadata({"title": "Convex Optimization", "author": "Boyd"})
    data = bytes(document.tobytes())

    parsed = parse_pdf(data, ocr=False)

    assert parsed.metadata["title"] == "Convex Optimization"
    assert parsed.metadata["author"] == "Boyd"


def test_a_file_that_is_not_a_pdf_fails_with_a_readable_message() -> None:
    with pytest.raises(ParseFailed, match="could not be opened"):
        parse_pdf(b"%PDF-1.7 but actually nonsense", ocr=False)


def test_an_image_only_page_yields_nothing_without_ocr() -> None:
    """The empty result is what triggers the OCR fallback in the pipeline."""
    document = pymupdf.open()
    document.new_page()
    data = bytes(document.tobytes())

    assert parse_pdf(data, ocr=False).is_empty


# ── DOCX ──────────────────────────────────────────────────────────────────────


def test_docx_heading_levels_survive() -> None:
    def build(document):  # type: ignore[no-untyped-def]
        document.add_heading("Optimization", level=1)
        document.add_paragraph("Gradient descent steps downhill.")
        document.add_heading("Convergence", level=2)
        document.add_paragraph("It converges for convex functions.")

    parsed = parse_docx(make_docx(build))
    headings = [(b.text, b.level) for b in parsed.blocks if b.kind is BlockKind.HEADING]

    assert headings == [("Optimization", 1), ("Convergence", 2)]


def test_docx_lists_and_tables_are_recognised() -> None:
    def build(document):  # type: ignore[no-untyped-def]
        document.add_paragraph("First item", style="List Bullet")
        document.add_paragraph("Second item", style="List Bullet")
        table = document.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "concept"
        table.cell(0, 1).text = "mastery"
        table.cell(1, 0).text = "chain rule"
        table.cell(1, 1).text = "38"

    parsed = parse_docx(make_docx(build))
    kinds = [b.kind for b in parsed.blocks]

    assert kinds.count(BlockKind.LIST_ITEM) == 2
    assert BlockKind.TABLE in kinds
    assert "chain rule" in parsed.text


def test_empty_paragraphs_are_dropped() -> None:
    def build(document):  # type: ignore[no-untyped-def]
        document.add_paragraph("Real content.")
        document.add_paragraph("")
        document.add_paragraph("   ")

    parsed = parse_docx(make_docx(build))
    assert len(parsed.blocks) == 1


def test_a_file_that_is_not_a_docx_fails_with_a_readable_message() -> None:
    with pytest.raises(ParseFailed, match="Word document"):
        parse_docx(b"PK\x03\x04 not really a docx")


# ── Dispatch ──────────────────────────────────────────────────────────────────


def test_dispatch_reaches_the_binary_parsers() -> None:
    data = make_pdf([[("Body text here.", BODY)]])
    assert "Body text" in parse_source(SourceKind.PDF, data).text


def test_availability_reflects_the_installed_extras() -> None:
    assert available(SourceKind.PDF)
    assert available(SourceKind.DOCX)
    assert available(SourceKind.MD), (
        "formats with no optional dependency are always available"
    )
