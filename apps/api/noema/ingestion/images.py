"""Image upload validation, for a card's attached diagram.

A card's image illustrates a question — a screenshot or a diagram, not a scanned
document — so it gets its own small check by content rather than stretching
:mod:`noema.ingestion.validation` to cover a format family it was never meant to.
Same principle either way: the format is decided by magic bytes, never by a
filename or a declared content type.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from noema.core.errors import NoemaError

__all__ = [
    "CONTENT_TYPES",
    "ImageCheck",
    "ImageKind",
    "ImageTooLarge",
    "RejectedImage",
    "check_image_upload",
    "sniff_image_kind",
]

#: A card illustrates one question; it is not a place to store a 50 MB photo dump.
MAX_IMAGE_MB: Final = 5


class ImageKind(StrEnum):
    PNG = "png"
    JPEG = "jpeg"
    GIF = "gif"
    WEBP = "webp"


CONTENT_TYPES: Final[dict[ImageKind, str]] = {
    ImageKind.PNG: "image/png",
    ImageKind.JPEG: "image/jpeg",
    ImageKind.GIF: "image/gif",
    ImageKind.WEBP: "image/webp",
}

#: Leading bytes → format. WebP needs a second check: RIFF alone also covers
#: WAV and AVI, so the "WEBP" marker at offset 8 is what actually names it.
_MAGIC: Final[list[tuple[bytes, ImageKind]]] = [
    (b"\x89PNG\r\n\x1a\n", ImageKind.PNG),
    (b"\xff\xd8\xff", ImageKind.JPEG),
    (b"GIF87a", ImageKind.GIF),
    (b"GIF89a", ImageKind.GIF),
]


class RejectedImage(NoemaError):
    slug = "image-rejected"
    title = "Image rejected"
    status_code = 415


class ImageTooLarge(NoemaError):
    slug = "image-too-large"
    title = "Image too large"
    status_code = 413


@dataclass(frozen=True, slots=True)
class ImageCheck:
    kind: ImageKind
    byte_size: int
    checksum_sha256: str
    content_type: str


def sniff_image_kind(data: bytes) -> ImageKind:
    for magic, kind in _MAGIC:
        if data.startswith(magic):
            return kind

    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ImageKind.WEBP

    raise RejectedImage(
        "Not a recognised image format. PNG, JPEG, GIF and WebP are accepted."
    )


def check_image_upload(data: bytes, *, max_mb: int = MAX_IMAGE_MB) -> ImageCheck:
    """Validate an uploaded image and return what should be recorded about it."""
    if not data:
        raise RejectedImage("The image is empty.")

    kind = sniff_image_kind(data)

    if len(data) > max_mb * 1024 * 1024:
        raise ImageTooLarge(
            f"Images are limited to {max_mb} MB; this file is "
            f"{len(data) / 1024 / 1024:.1f} MB."
        )

    return ImageCheck(
        kind=kind,
        byte_size=len(data),
        checksum_sha256=hashlib.sha256(data).hexdigest(),
        content_type=CONTENT_TYPES[kind],
    )
