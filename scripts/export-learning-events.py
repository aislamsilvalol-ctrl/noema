#!/usr/bin/env python
"""Export pseudonymous learning events as JSONL for the Sabelia pipeline.

    NOEMA_EXPORT_SECRET=... DATABASE_URL=... \\
      apps/api/.venv/bin/python scripts/export-learning-events.py --since 2026-01-01 --out events.jsonl

The secret decides the pseudonyms: the same secret gives the same ids across
exports, so sequences continue; a new secret is a new population. Keep it
with the other secrets, never in the repository. No text leaves the
database; see noema/services/learning_export.py for exactly what does.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from noema.db.base import get_sessionmaker  # noqa: E402
from noema.services.learning_export import export_events, to_jsonl  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", default=None, help="ISO date, inclusive")
    parser.add_argument("--until", default=None, help="ISO date, exclusive")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    secret = os.environ.get("NOEMA_EXPORT_SECRET", "")
    if len(secret) < 16:
        print("NOEMA_EXPORT_SECRET must be set (16+ characters)", file=sys.stderr)
        return 2
    since = datetime.fromisoformat(args.since).replace(tzinfo=UTC) if args.since else None
    until = datetime.fromisoformat(args.until).replace(tzinfo=UTC) if args.until else None
    n = 0
    async with get_sessionmaker()() as db:
        with Path(args.out).open("w") as f:
            async for event in export_events(db, secret=secret, since=since, until=until):
                f.write(to_jsonl(event) + "\n")
                n += 1
    print(f"wrote {n} events to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
