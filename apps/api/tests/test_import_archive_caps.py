"""A zip that would inflate past the caps is refused before any member is read."""

from __future__ import annotations

import io
import zipfile

import pytest

from noema.importers import _archive, anki, notion, obsidian
from noema.importers._archive import MAX_MEMBER_BYTES, reject_oversized

MB = 1024 * 1024


def zip_of(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_a_member_over_the_cap_is_refused_on_its_declared_size() -> None:
    """The central directory says how big a member inflates to; that number
    is enough to refuse on, without inflating anything."""
    package = zipfile.ZipFile(io.BytesIO(zip_of({"a.md": b"tiny"})))
    package.infolist()[0].file_size = MAX_MEMBER_BYTES + 1

    with pytest.raises(ValueError, match="limit is 50 MB per file"):
        reject_oversized(package, error=ValueError)


def test_members_under_the_cap_that_add_up_past_the_total_are_refused() -> None:
    members = {f"{n}.md": b"x" for n in range(5)}
    package = zipfile.ZipFile(io.BytesIO(zip_of(members)))
    for info in package.infolist():
        info.file_size = MAX_MEMBER_BYTES  # five of them: 250 MB in all

    with pytest.raises(ValueError, match="more than 200 MB"):
        reject_oversized(package, error=ValueError)


def test_an_archive_within_both_caps_passes() -> None:
    package = zipfile.ZipFile(io.BytesIO(zip_of({"a.md": b"a", "b.md": b"b"})))
    for info in package.infolist():
        info.file_size = 50 * MB

    reject_oversized(package, error=ValueError)


@pytest.fixture
def tiny_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_archive, "MAX_MEMBER_BYTES", 16)
    monkeypatch.setattr(_archive, "MAX_TOTAL_BYTES", 24)


def test_obsidian_refuses_with_its_own_error(tiny_caps: None) -> None:
    with pytest.raises(obsidian.ObsidianImportError, match="per file"):
        obsidian.read(zip_of({"Note.md": b"x" * 17}))
    with pytest.raises(obsidian.ObsidianImportError, match="unpacks to more"):
        obsidian.read(zip_of({"A.md": b"x" * 13, "B.md": b"x" * 13}))

    assert len(obsidian.read(zip_of({"Note.md": b"x" * 16})).notes) == 1


def test_notion_refuses_with_its_own_error(tiny_caps: None) -> None:
    with pytest.raises(notion.NotionImportError, match="per file"):
        notion.read(zip_of({"Page 0123456789abcdef0123456789abcdef.md": b"x" * 17}))


def test_anki_refuses_before_extracting_the_collection(tiny_caps: None) -> None:
    with pytest.raises(anki.AnkiImportError, match="per file"):
        anki.read(zip_of({"collection.anki21": b"x" * 17}))
