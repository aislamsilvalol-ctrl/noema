"""The one check every zip importer runs before reading a member.

The upload limit bounds the *compressed* size. A zip of zeros inflates a
thousandfold, so a file under that limit can still ask for gigabytes of
memory the moment a member is read. The central directory states each
member's uncompressed size up front; refusing on those numbers costs nothing
and happens before a single byte is inflated.
"""

from __future__ import annotations

import zipfile

__all__ = ["MAX_MEMBER_BYTES", "MAX_TOTAL_BYTES", "reject_oversized"]

#: The largest single member an import will inflate.
MAX_MEMBER_BYTES = 50 * 1024 * 1024
#: The most an archive may inflate to in total.
MAX_TOTAL_BYTES = 200 * 1024 * 1024


def reject_oversized(package: zipfile.ZipFile, *, error: type[Exception]) -> None:
    """Raise ``error`` when the archive would inflate past either cap.

    The importer's own error class is raised so its route keeps translating
    it the way it translates every other unreadable file.
    """
    total = 0
    for info in package.infolist():
        if info.file_size > MAX_MEMBER_BYTES:
            raise error(
                f"That archive holds a file of {info.file_size // (1024 * 1024)} MB; "
                f"the limit is {MAX_MEMBER_BYTES // (1024 * 1024)} MB per file."
            )
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise error(
                "That archive unpacks to more than "
                f"{MAX_TOTAL_BYTES // (1024 * 1024)} MB. Split it and import "
                "the parts separately."
            )
