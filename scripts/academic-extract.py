#!/usr/bin/env python
"""Extract concepts, relations and evidenced claims from segmented lectures.

    # what it would cost and touch, without calling a model
    apps/api/.venv/bin/python scripts/academic-extract.py \
        --segments out/18-06-segments.jsonl --dry-run

    # the real run, one provider, one model
    ANTHROPIC_API_KEY=... apps/api/.venv/bin/python scripts/academic-extract.py \
        --segments out/18-06-segments.jsonl --out out/18-06-knowledge.jsonl \
        --provider anthropic --model claude-sonnet-5 --limit 40

Phase 3 of docs/academic-knowledge-engine.md. Reads the segments written by
scripts/academic-acquire.py and writes one JSON line per segment: its evidence
(lecture, start and end in milliseconds), the concepts, relations and claims
the model returned, each marked `source_supported` or `inferred`, each claim
with an epistemic tag. Nothing is written to the database — this produces a
file a reviewer reads before any of it becomes a `Concept` row.

**This spends money.** Every segment is one structured call. `--dry-run` prints
the segment count, the character volume and a rough token estimate first, and
`--limit` exists so the first real run is a sample, not a course.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

os.environ.setdefault("NOEMA_MASTER_KEY", base64.b64encode(b"0" * 32).decode())
os.environ.setdefault("NOEMA_SESSION_SECRET", base64.b64encode(b"1" * 32).decode())

from noema.academic.captions import Segment
from noema.academic.extraction import extract_segment
from noema.api.v1.deps import build_provider
from noema.core.config import get_settings
from noema.providers.gateway import AIGateway

#: Rough, and labelled as rough: a token is about four characters of English,
#: the prompt adds about 700, and the answer is bounded by the schema.
CHARS_PER_TOKEN = 4
PROMPT_TOKENS = 700
ANSWER_TOKENS = 400


def read_segments(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def segment_of(row: dict) -> Segment:
    return Segment(
        index=row["index"],
        start_ms=row["start_ms"],
        end_ms=row["end_ms"],
        text=row["text"],
        sentences=row["sentences"],
        quality=list(row.get("quality") or []),
    )


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--segments", required=True)
    parser.add_argument("--out")
    parser.add_argument("--provider", default="anthropic")
    parser.add_argument("--model")
    parser.add_argument("--limit", type=int, help="only the first N usable segments")
    parser.add_argument(
        "--skip-flagged",
        action="store_true",
        help="skip segments the segmenter flagged (spoken_math, repetitive, …)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = read_segments(Path(args.segments))
    usable = [
        row
        for row in rows
        if row["text"].strip() and not (args.skip_flagged and row.get("quality"))
    ]
    if args.limit:
        usable = usable[: args.limit]

    characters = sum(len(row["text"]) for row in usable)
    tokens_in = characters // CHARS_PER_TOKEN + PROMPT_TOKENS * len(usable)
    lectures = {row["source_id"] for row in usable}
    print(
        f"{len(rows)} segments read, {len(usable)} to extract, "
        f"from {len(lectures)} lectures"
    )
    print(
        f"about {tokens_in:,} input tokens and up to "
        f"{ANSWER_TOKENS * len(usable):,} output tokens — a rough estimate, "
        "not a quote"
    )
    if args.dry_run:
        print("dry run: no model was called")
        return 0
    if not args.out:
        print("--out is required for a real run", file=sys.stderr)
        return 2

    settings = get_settings()
    provider = await build_provider(args.provider, settings, credentials=None)
    gateway = AIGateway(provider)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    concepts = claims = inferred = empty = 0
    # A blocking write per segment, between calls that take seconds: buffering
    # this in memory would only risk losing an expensive run to a crash.
    with out.open("w") as f:  # noqa: ASYNC230
        for i, row in enumerate(usable, start=1):
            extraction = await extract_segment(
                gateway,
                segment_of(row),
                source_id=row["source_id"],
                lecture=str(row.get("lecture") or ""),
                course=str(row.get("course_code") or ""),
                model=args.model,
            )
            payload = extraction.as_dict()
            payload["lecture_url"] = row.get("lecture_url")
            payload["licence"] = row.get("licence")
            f.write(json.dumps(payload) + "\n")
            concepts += len(extraction.concepts)
            claims += len(extraction.claims)
            inferred += round(extraction.inferred_share * 100)
            empty += int(extraction.empty)
            if i % 20 == 0:
                print(f"  {i}/{len(usable)} segments, {concepts} concepts so far")

    print(
        f"{concepts} concepts and {claims} claims from {len(usable)} segments "
        f"({empty} yielded nothing); mean inferred share "
        f"{inferred / max(1, len(usable)):.0f}% → {out}"
    )
    print("Nothing was written to the database. A reviewer reads this file first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
