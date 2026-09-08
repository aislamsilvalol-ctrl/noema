"""Acquisition: fetch the official captions a registry record points at, once.

The cache this writes is private and derived-from, never a surface: a file per
lecture under a directory the caller names, plus a manifest line recording
where it came from, under which licence, what it hashes to and when it was
fetched. `docs/academic-knowledge-engine.md` says the raw transcript is a
cache used to derive structure — this is that cache, and nothing in the
product reads it directly.

Two rules are enforced here rather than trusted to the caller:

* **Only what the licence allows.** A record that is not `official` or whose
  licence does not permit derived use is skipped, with the reason recorded.
* **Once.** A lecture already in the manifest with the same URL is not
  re-fetched unless asked; the fetch is sequential with a pause between
  requests, because a university's servers are not a resource to be spent.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from noema.academic.registry import CaptionResource, SourceRecord
from noema.core.logging import get_logger

log = get_logger(__name__)

Fetch = Callable[[str], str]

#: Seconds between two requests to the same host. Politeness, not rate limits.
PAUSE = 1.0

#: The caption kind the pipeline reads. Transcript PDFs are recorded in the
#: registry but not parsed here — a PDF is a different acquisition.
PREFERRED = "vtt"


@dataclass(frozen=True, slots=True)
class Acquired:
    source_id: str
    path: Path | None
    url: str | None
    licence: str
    checksum: str | None
    bytes: int
    status: str  # fetched | cached | skipped:<reason> | failed:<error>

    @property
    def ok(self) -> bool:
        return self.status in {"fetched", "cached"}


def caption_for(record: SourceRecord, kind: str = PREFERRED) -> CaptionResource | None:
    for caption in record.captions:
        if caption.kind == kind:
            return caption
    return None


def _manifest(cache: Path) -> dict[str, dict[str, object]]:
    path = cache / "manifest.jsonl"
    if not path.exists():
        return {}
    rows: dict[str, dict[str, object]] = {}
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["source_id"]] = row
    return rows


def acquire(
    records: list[SourceRecord],
    cache: Path,
    fetch: Fetch,
    *,
    refetch: bool = False,
    pause: float = PAUSE,
) -> list[Acquired]:
    """Fetch each usable record's captions into ``cache``; return what happened."""
    cache.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(cache)
    results: list[Acquired] = []
    first = True
    for record in records:
        caption = caption_for(record)
        if not record.usable:
            reason = "trust" if record.trust.value != "official" else "licence"
            results.append(
                Acquired(
                    record.source_id,
                    None,
                    None,
                    record.licence.value,
                    None,
                    0,
                    f"skipped:{reason}",
                )
            )
            continue
        if caption is None:
            results.append(
                Acquired(
                    record.source_id,
                    None,
                    None,
                    record.licence.value,
                    None,
                    0,
                    "skipped:no_captions",
                )
            )
            continue
        known = manifest.get(record.source_id)
        target = cache / f"{record.source_id.replace(':', '_')}.vtt"
        if known and known.get("url") == caption.url and target.exists() and not refetch:
            results.append(
                Acquired(
                    record.source_id,
                    target,
                    caption.url,
                    record.licence.value,
                    str(known.get("checksum") or ""),
                    target.stat().st_size,
                    "cached",
                )
            )
            continue
        if not first:
            time.sleep(pause)
        first = False
        try:
            body = fetch(caption.url)
        except Exception as exc:
            log.warning(
                "academic.acquire.failed", source_id=record.source_id, error=str(exc)
            )
            results.append(
                Acquired(
                    record.source_id,
                    None,
                    caption.url,
                    record.licence.value,
                    None,
                    0,
                    f"failed:{type(exc).__name__}",
                )
            )
            continue
        target.write_text(body)
        checksum = "sha256:" + hashlib.sha256(body.encode()).hexdigest()[:16]
        size = len(body.encode())
        row: dict[str, object] = {
            "source_id": record.source_id,
            "university": record.university,
            "course_code": record.course_code,
            "title": record.title,
            "url": caption.url,
            "page_url": str(record.url),
            "licence": record.licence.value,
            "trust": record.trust.value,
            "language": caption.language,
            "checksum": checksum,
            "bytes": size,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "file": target.name,
        }
        with (cache / "manifest.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
        results.append(
            Acquired(
                record.source_id,
                target,
                caption.url,
                record.licence.value,
                checksum,
                size,
                "fetched",
            )
        )
    return results
