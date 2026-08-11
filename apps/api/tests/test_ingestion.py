"""Parsers and upload validation."""

from __future__ import annotations

import io
import zipfile

import pytest

from noema.db.models import SourceKind
from noema.ingestion.ir import BlockKind
from noema.ingestion.parsers import parse_source
from noema.ingestion.parsers.documents import parse_transcript
from noema.ingestion.parsers.text import parse_csv, parse_markdown, parse_text
from noema.ingestion.validation import (
    RejectedUpload,
    UploadTooLarge,
    check_upload,
    sniff_kind,
)

MARKDOWN = """# Neural Networks

Backpropagation computes gradients.

## The Chain Rule

- Derivative of a composition
- Applied layer by layer

```python
def grad(x):
    return 2 * x
```

> Attributed to Leibniz.
"""


# ── Markdown ──────────────────────────────────────────────────────────────────


def test_markdown_headings_carry_their_level() -> None:
    document = parse_markdown(MARKDOWN)
    headings = [b for b in document.blocks if b.kind is BlockKind.HEADING]

    assert [(h.text, h.level) for h in headings] == [
        ("Neural Networks", 1),
        ("The Chain Rule", 2),
    ]


def test_markdown_keeps_code_blocks_whole_with_their_language() -> None:
    code = [b for b in parse_markdown(MARKDOWN).blocks if b.kind is BlockKind.CODE]
    assert len(code) == 1
    assert code[0].language == "python"
    assert "def grad(x):" in code[0].text
    assert "```" not in code[0].text


def test_markdown_recognises_lists_and_quotes() -> None:
    kinds = {b.kind for b in parse_markdown(MARKDOWN).blocks}
    assert BlockKind.LIST_ITEM in kinds
    assert BlockKind.QUOTE in kinds


def test_markdown_title_is_extracted_as_metadata() -> None:
    assert parse_markdown(MARKDOWN).metadata["title"] == "Neural Networks"


def test_setext_headings_are_understood() -> None:
    document = parse_markdown("Introduction\n============\n\nText.")
    assert document.blocks[0].kind is BlockKind.HEADING
    assert document.blocks[0].level == 1


def test_a_hash_inside_a_code_block_is_not_a_heading() -> None:
    document = parse_markdown("```\n# not a heading\n```")
    assert all(b.kind is not BlockKind.HEADING for b in document.blocks)


# ── Plain text ────────────────────────────────────────────────────────────────


def test_plain_text_invents_no_structure() -> None:
    document = parse_text("First paragraph.\n\nSecond paragraph.")
    assert [b.kind for b in document.blocks] == [BlockKind.PARAGRAPH] * 2


# ── CSV ───────────────────────────────────────────────────────────────────────


def test_csv_becomes_a_schema_summary_not_one_chunk_per_row() -> None:
    rows = "\n".join(f"{i},concept-{i},0.{i}" for i in range(500))
    document = parse_csv(f"id,name,score\n{rows}")

    assert document.metadata["columns"] == ["id", "name", "score"]
    assert document.metadata["row_count"] == 500
    # A sample, not 500 near-identical vectors.
    assert len(document.blocks) < 10
    assert "500 rows" in document.text


def test_an_empty_csv_produces_nothing() -> None:
    assert parse_csv("").blocks == []


# ── Transcripts ───────────────────────────────────────────────────────────────


def test_transcript_timestamps_become_citation_anchors() -> None:
    vtt = """WEBVTT

1
00:00:12.500 --> 00:00:15.000
Gradient descent is iterative.

2
00:01:03.250 --> 00:01:06.000
Each step follows the slope.
"""
    document = parse_transcript(vtt)

    assert [b.timestamp for b in document.blocks] == [12.5, 63.25]
    assert "iterative" in document.blocks[0].text
    assert "WEBVTT" not in document.text


# ── Dispatch ──────────────────────────────────────────────────────────────────


def test_dispatch_routes_by_kind() -> None:
    document = parse_source(SourceKind.MD, MARKDOWN.encode())
    assert document.metadata["title"] == "Neural Networks"


def test_decoding_survives_a_stray_byte() -> None:
    """One bad character in a long document should not cost the user the upload."""
    document = parse_source(SourceKind.TXT, b"caf\xe9 au lait\n\nsecond")
    assert len(document.blocks) == 2


# ── Validation ────────────────────────────────────────────────────────────────


def test_pdfs_are_recognised_by_content_not_extension() -> None:
    assert sniff_kind(b"%PDF-1.7\n...", "notes.txt") is SourceKind.PDF


def test_a_docx_is_told_apart_from_a_plain_archive() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<w:document/>")
    assert sniff_kind(buffer.getvalue(), "essay.docx") is SourceKind.DOCX

    plain = io.BytesIO()
    with zipfile.ZipFile(plain, "w") as archive:
        archive.writestr("notes.txt", "hello")
    with pytest.raises(RejectedUpload, match="Archives"):
        sniff_kind(plain.getvalue(), "bundle.zip")


@pytest.mark.parametrize(
    ("data", "description"),
    [
        (b"\x7fELF\x02\x01", "executable"),
        (b"MZ\x90\x00", "executable"),
        (b"\x1f\x8b\x08", "gzip"),
        (b"\xd0\xcf\x11\xe0\xa1\xb1", "legacy Office"),
    ],
)
def test_dangerous_formats_are_refused(data: bytes, description: str) -> None:
    with pytest.raises(RejectedUpload):
        sniff_kind(data, f"payload-{description}")


def test_binary_content_masquerading_as_text_is_refused() -> None:
    with pytest.raises(RejectedUpload, match="binary"):
        sniff_kind(b"text then a null\x00and more", "notes.txt")


def test_the_extension_only_disambiguates_between_text_formats() -> None:
    assert sniff_kind(b"a,b\n1,2", "data.csv") is SourceKind.CSV
    assert (
        sniff_kind(b"00:00:01.000 --> 00:00:02.000", "talk.vtt") is SourceKind.TRANSCRIPT
    )
    assert sniff_kind(b"just prose", "notes.txt") is SourceKind.TXT


def test_size_limits_are_per_format() -> None:
    with pytest.raises(UploadTooLarge, match="MD"):
        check_upload(b"# " + b"x" * (6 * 1024 * 1024), "huge.md")


def test_the_deployment_cap_can_only_tighten_the_limit() -> None:
    payload = b"%PDF-1.7" + b"x" * (2 * 1024 * 1024)
    check_upload(payload, "fine.pdf")  # within the 100 MB format limit

    with pytest.raises(UploadTooLarge):
        check_upload(payload, "fine.pdf", max_upload_mb=1)


def test_an_empty_file_is_refused() -> None:
    with pytest.raises(RejectedUpload, match="empty"):
        check_upload(b"", "nothing.txt")


def test_a_declared_kind_that_contradicts_the_content_is_refused() -> None:
    with pytest.raises(RejectedUpload, match="not a"):
        check_upload(b"%PDF-1.7\n", "a.pdf", declared_kind=SourceKind.CSV)


def test_the_checksum_identifies_the_file_for_deduplication() -> None:
    first = check_upload(b"# Same content", "a.md")
    second = check_upload(b"# Same content", "renamed.md")
    different = check_upload(b"# Other content", "c.md")

    assert first.checksum_sha256 == second.checksum_sha256
    assert first.checksum_sha256 != different.checksum_sha256
