"""Upload validation.

Parsers are the largest untrusted-input surface in NOEMA, so what reaches them is
decided here: type by magic bytes rather than by filename, size caps per format, and
an outright refusal for archives and executables.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

from noema.core.errors import NoemaError
from noema.db.models import SourceKind

__all__ = ["RejectedUpload", "UploadCheck", "check_upload", "sniff_kind"]

#: Per-format ceilings in megabytes. A 300-page textbook is ~30 MB; a 100 MB CSV is
#: a database export that belongs somewhere else.
SIZE_LIMITS_MB: Final[dict[SourceKind, int]] = {
    SourceKind.PDF: 100,
    SourceKind.DOCX: 25,
    SourceKind.MD: 5,
    SourceKind.TXT: 5,
    SourceKind.CSV: 25,
    SourceKind.TRANSCRIPT: 5,
    SourceKind.PASTE: 1,
    SourceKind.URL: 5,
}

#: Leading bytes → format. Extensions are a claim by the uploader, not evidence.
MAGIC: Final[list[tuple[bytes, SourceKind]]] = [
    (b"%PDF-", SourceKind.PDF),
]

#: Container formats we refuse outright: a zip bomb or a macro-enabled document is
#: not something a learning tool needs to open.
FORBIDDEN_MAGIC: Final[list[tuple[bytes, str]]] = [
    (b"PK\x03\x04", "archive"),  # also .docx — handled before this check
    (b"\x1f\x8b", "gzip archive"),
    (b"Rar!", "archive"),
    (b"7z\xbc\xaf", "archive"),
    (b"\x7fELF", "executable"),
    (b"MZ", "executable"),
    (b"\xca\xfe\xba\xbe", "executable"),
    (b"\xd0\xcf\x11\xe0", "legacy Office document"),  # .doc/.xls, macro-capable
]

DOCX_CONTENT_MARKER: Final = b"word/document.xml"


class RejectedUpload(NoemaError):
    slug = "upload-rejected"
    title = "Upload rejected"
    status_code = 415


class UploadTooLarge(NoemaError):
    slug = "upload-too-large"
    title = "File too large"
    status_code = 413


@dataclass(frozen=True, slots=True)
class UploadCheck:
    kind: SourceKind
    byte_size: int
    checksum_sha256: str


def sniff_kind(data: bytes, filename: str | None = None) -> SourceKind:
    """Determine the format from content, using the filename only to disambiguate.

    A .docx is a zip, so it has to be recognised before archives are refused — by
    looking for the Word part inside it, not by trusting the extension.
    """
    for magic, kind in MAGIC:
        if data.startswith(magic):
            return kind

    if data.startswith(b"PK\x03\x04"):
        if DOCX_CONTENT_MARKER in data[:8192] or _looks_like_docx(data):
            return SourceKind.DOCX
        raise RejectedUpload("Archives are not accepted. Upload the documents inside it.")

    for magic, description in FORBIDDEN_MAGIC:
        if data.startswith(magic):
            raise RejectedUpload(f"{description.capitalize()} files are not accepted.")

    if b"\x00" in data[:8192]:
        raise RejectedUpload("This looks like a binary file rather than a document.")

    suffix = (
        (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    )
    text_kinds = {
        "md": SourceKind.MD,
        "markdown": SourceKind.MD,
        "csv": SourceKind.CSV,
        "tsv": SourceKind.CSV,
        "vtt": SourceKind.TRANSCRIPT,
        "srt": SourceKind.TRANSCRIPT,
        "txt": SourceKind.TXT,
    }
    if suffix in text_kinds:
        return text_kinds[suffix]

    # Unlabelled text: Markdown parses plain prose correctly, so it is the safer
    # default of the two.
    return SourceKind.MD


def check_upload(
    data: bytes,
    filename: str | None = None,
    *,
    declared_kind: SourceKind | None = None,
    max_upload_mb: int | None = None,
) -> UploadCheck:
    """Validate an upload and return what should be recorded about it."""
    if not data:
        raise RejectedUpload("The file is empty.")

    kind = sniff_kind(data, filename)

    if declared_kind is not None and declared_kind is not kind:
        raise RejectedUpload(f"This file is a {kind.value}, not a {declared_kind.value}.")

    limit_mb = min(
        SIZE_LIMITS_MB.get(kind, 25), max_upload_mb or SIZE_LIMITS_MB.get(kind, 25)
    )
    if len(data) > limit_mb * 1024 * 1024:
        raise UploadTooLarge(
            f"{kind.value.upper()} uploads are limited to {limit_mb} MB; "
            f"this file is {len(data) / 1024 / 1024:.1f} MB."
        )

    return UploadCheck(
        kind=kind,
        byte_size=len(data),
        checksum_sha256=hashlib.sha256(data).hexdigest(),
    )


def _looks_like_docx(data: bytes) -> bool:
    """Open the zip's central directory rather than guessing from the first bytes."""
    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return "word/document.xml" in archive.namelist()
    except (zipfile.BadZipFile, OSError):
        return False
