"""Card image validation — format by content, never by filename or claim."""

from __future__ import annotations

import pytest

from noema.ingestion.images import (
    ImageKind,
    ImageTooLarge,
    RejectedImage,
    check_image_upload,
    sniff_image_kind,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
GIF87 = b"GIF87a" + b"\x00" * 32
GIF89 = b"GIF89a" + b"\x00" * 32
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 32


def test_a_png_is_recognised_by_its_magic_bytes() -> None:
    assert sniff_image_kind(PNG) is ImageKind.PNG


def test_a_jpeg_is_recognised_by_its_magic_bytes() -> None:
    assert sniff_image_kind(JPEG) is ImageKind.JPEG


def test_both_gif_variants_are_recognised() -> None:
    assert sniff_image_kind(GIF87) is ImageKind.GIF
    assert sniff_image_kind(GIF89) is ImageKind.GIF


def test_a_webp_is_recognised_by_its_riff_and_webp_markers() -> None:
    assert sniff_image_kind(WEBP) is ImageKind.WEBP


def test_a_bare_riff_that_is_not_webp_is_rejected() -> None:
    """RIFF alone also covers WAV and AVI — the WEBP marker is what actually names it."""
    wav = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"\x00" * 32
    with pytest.raises(RejectedImage):
        sniff_image_kind(wav)


def test_unrecognised_content_is_rejected() -> None:
    with pytest.raises(RejectedImage):
        sniff_image_kind(b"not an image at all")


def test_a_pdf_is_rejected_even_though_it_is_a_real_file_format() -> None:
    """A card image is not a document — the wrong kind of real file is still wrong."""
    with pytest.raises(RejectedImage):
        sniff_image_kind(b"%PDF-1.4\n" + b"\x00" * 32)


def test_check_image_upload_rejects_empty_data() -> None:
    with pytest.raises(RejectedImage):
        check_image_upload(b"")


def test_check_image_upload_returns_the_kind_size_checksum_and_content_type() -> None:
    check = check_image_upload(PNG)

    assert check.kind is ImageKind.PNG
    assert check.byte_size == len(PNG)
    assert check.content_type == "image/png"
    assert len(check.checksum_sha256) == 64


def test_check_image_upload_enforces_the_size_ceiling() -> None:
    oversized = PNG + b"\x00" * (5 * 1024 * 1024)
    with pytest.raises(ImageTooLarge):
        check_image_upload(oversized, max_mb=5)


def test_check_image_upload_allows_a_custom_smaller_ceiling() -> None:
    check_image_upload(PNG, max_mb=1)  # under 1 MB, should not raise
    with pytest.raises(ImageTooLarge):
        check_image_upload(PNG + b"\x00" * (2 * 1024 * 1024), max_mb=1)
