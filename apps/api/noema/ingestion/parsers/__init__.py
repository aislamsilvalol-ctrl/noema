"""Parser dispatch.

Adding a format means writing a function that returns a :class:`ParsedDocument` and
registering it here. Nothing downstream changes.
"""

from __future__ import annotations

from noema.db.models import SourceKind
from noema.ingestion.ir import ParsedDocument
from noema.ingestion.parsers.documents import (
    ParseFailed,
    ParserUnavailable,
    parse_docx,
    parse_html,
    parse_pdf,
    parse_transcript,
)
from noema.ingestion.parsers.text import parse_csv, parse_markdown, parse_text

__all__ = ["ParseFailed", "ParserUnavailable", "parse_source"]

#: Formats whose parsers need an optional dependency, so the API can say what it
#: supports before a user spends time on an upload.
OPTIONAL: dict[SourceKind, str] = {
    SourceKind.PDF: "pymupdf",
    SourceKind.DOCX: "python-docx",
    SourceKind.URL: "trafilatura",
}


def parse_source(
    kind: SourceKind, data: bytes, *, url: str | None = None, ocr: bool = True
) -> ParsedDocument:
    """Parse raw bytes into the shared IR."""
    if kind is SourceKind.PDF:
        return parse_pdf(data, ocr=ocr)
    if kind is SourceKind.DOCX:
        return parse_docx(data)

    text = _decode(data)

    if kind is SourceKind.URL:
        return parse_html(text, url=url)
    if kind is SourceKind.CSV:
        return parse_csv(text)
    if kind is SourceKind.TRANSCRIPT:
        return parse_transcript(text)
    if kind in {SourceKind.MD, SourceKind.PASTE}:
        return parse_markdown(text)
    return parse_text(text)


def available(kind: SourceKind) -> bool:
    """Whether this deployment can actually parse the format."""
    module = OPTIONAL.get(kind)
    if module is None:
        return True

    import importlib.util

    return importlib.util.find_spec(module.replace("-", "_")) is not None


#: UTF-16 accepts almost any even-length byte string and turns Latin-1 text into
#: fluent-looking mojibake, so it is only used when the BOM says so.
UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")


def _decode(data: bytes) -> str:
    """Decode text, falling back rather than failing on a stray byte.

    A single bad character in a 300-page document should not cost the user the
    upload — but silently mis-decoding the whole file is worse than an error, so
    the fallback order is deliberate rather than exhaustive.
    """
    if data.startswith(UTF16_BOMS):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass

    # Latin-1 maps every byte to some character, so this always succeeds. It is the
    # right last resort: a handful of wrong accents beats losing the document.
    return data.decode("latin-1")
