#!/usr/bin/env python
"""Fetch the official captions of the lectures in a registry file, and segment them.

    apps/api/.venv/bin/python scripts/academic-acquire.py \
        --registry registry/mit-18-06.jsonl --cache .cache/academic \
        --segments out/segments.jsonl

Reads the JSONL written by scripts/academic-register.py, downloads each usable
lecture's official `.vtt` once (skipping anything whose licence or trust does
not allow it), and writes the segmentation as JSONL: one line per segment with
its lecture, its start and end in milliseconds, its text and its quality flags.

The caption cache is private: it is the raw material Phase 3 extracts concepts
and claims from, not something the product serves. Keep it out of git.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from noema.academic.acquire import acquire
from noema.academic.captions import segments_for
from noema.academic.ocw import http_fetch
from noema.academic.registry import SourceRecord


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--registry", required=True, help="JSONL from scripts/academic-register.py"
    )
    parser.add_argument(
        "--cache", required=True, help="directory for the private caption cache"
    )
    parser.add_argument("--segments", help="write the segmentation here as JSONL")
    parser.add_argument("--refetch", action="store_true")
    parser.add_argument("--limit", type=int, help="only the first N lectures")
    args = parser.parse_args()

    records: list[SourceRecord] = []
    for line in Path(args.registry).read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("content_type") == "lecture_video":
            records.append(SourceRecord.model_validate(row))
    if args.limit:
        records = records[: args.limit]

    results = acquire(records, Path(args.cache), http_fetch, refetch=args.refetch)
    fetched = [r for r in results if r.ok]
    skipped = [r for r in results if not r.ok]
    new = sum(1 for r in results if r.status == "fetched")
    cached = sum(1 for r in results if r.status == "cached")
    print(
        f"{len(records)} lectures: {new} fetched, {cached} already cached, "
        f"{len(skipped)} not taken"
    )
    for r in skipped:
        print(f"  {r.source_id}: {r.status}")

    if not args.segments:
        return 0
    by_lecture = {r.source_id: r for r in records}
    out = Path(args.segments)
    out.parent.mkdir(parents=True, exist_ok=True)
    total = flagged = 0
    with out.open("w") as f:
        for result in fetched:
            record = by_lecture[result.source_id]
            segments = segments_for(result.path.read_text())
            total += len(segments)
            flagged += sum(1 for s in segments if s.quality)
            for s in segments:
                f.write(
                    json.dumps(
                        {
                            "source_id": record.source_id,
                            "university": record.university,
                            "course_code": record.course_code,
                            "lecture": record.title,
                            "lecture_url": str(record.url),
                            "youtube_id": record.youtube_id,
                            "licence": record.licence.value,
                            "order": record.order,
                            **s.as_dict(),
                        }
                    )
                    + "\n"
                )
    print(
        f"{total} segments from {len(fetched)} lectures, "
        f"{flagged} with a quality flag → {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
