#!/usr/bin/env python
"""Fold extracted lectures into one atlas, with a plan a person approves.

    apps/api/.venv/bin/python scripts/academic-reconcile.py \
        --knowledge out/18-06-knowledge.jsonl --out out/18-06-atlas.json

Phase 4 of docs/academic-knowledge-engine.md. Reads the extraction file written
by scripts/academic-extract.py, folds the same concept seen in many lectures
into one entry, keeps the definitions that disagree rather than voting on them,
and plans `merge`, `review` or `create` against the product's own concepts.

Nothing is written to the database. The atlas is a file: what a reviewer reads,
and what Phase 5 (pedagogical retrieval) would read once a reviewer approves.
Without `--concepts`, every plan is `create` — which is the honest answer when
nothing was compared against.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from noema.academic.extraction import (
    Claim,
    Concept,
    Epistemic,
    Evidence,
    Extraction,
    Relation,
    RelationKind,
    Support,
)
from noema.academic.reconciliation import reconcile
from noema.knowledge.resolution import normalize_name


def evidence_of(row: dict) -> Evidence:
    return Evidence(
        source_id=row["source_id"],
        start_ms=row["start_ms"],
        end_ms=row["end_ms"],
        segment=row.get("segment", 0),
    )


def extraction_of(row: dict) -> Extraction:
    at = evidence_of(row)
    return Extraction(
        evidence=at,
        quality=list(row.get("quality") or []),
        concepts=[
            Concept(
                name=c["name"],
                definition=c.get("definition", ""),
                difficulty=float(c.get("difficulty", 0.5)),
                support=Support(c.get("support", "inferred")),
                evidence=evidence_of(c.get("evidence") or row),
            )
            for c in row.get("concepts") or []
        ],
        relations=[
            Relation(
                source=r["source"],
                target=r["target"],
                kind=RelationKind(r["kind"]),
                support=Support(r.get("support", "inferred")),
                evidence=evidence_of(r.get("evidence") or row),
            )
            for r in row.get("relations") or []
        ],
        claims=[
            Claim(
                text=c["text"],
                concept=c.get("concept", ""),
                epistemic=Epistemic(c["epistemic"]),
                support=Support(c.get("support", "inferred")),
                evidence=evidence_of(c.get("evidence") or row),
            )
            for c in row.get("claims") or []
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--knowledge", required=True, help="JSONL from academic-extract.py"
    )
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--concepts",
        help="JSON list of the product's concepts as [{id, name}] to plan against",
    )
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in Path(args.knowledge).read_text().splitlines()
        if line.strip()
    ]
    extractions = [extraction_of(row) for row in rows]

    known: list[tuple[str, str]] = []
    if args.concepts:
        known = [
            (str(c["id"]), normalize_name(str(c["name"])))
            for c in json.loads(Path(args.concepts).read_text())
        ]

    def nearest(key: str) -> list[tuple[str, str, float]]:
        # Exact normalised name only: this script has no embeddings, and a
        # similarity invented here would drive merges nobody could check.
        return [(cid, name, 1.0) for cid, name in known if name == key]

    atlas = reconcile(extractions, nearest=nearest if known else None)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(atlas.as_dict(), indent=2) + "\n")

    supported = sum(1 for c in atlas.concepts if c.source_supported)
    disagreeing = sum(1 for c in atlas.concepts if c.disagreements)
    plans: dict[str, int] = {}
    for concept in atlas.concepts:
        plans[concept.decision] = plans.get(concept.decision, 0) + 1
    print(
        f"{len(rows)} segments → {len(atlas.concepts)} concepts "
        f"({supported} source-supported), {len(atlas.edges)} edges, "
        f"{disagreeing} with sources that disagree"
    )
    print(
        "plan: " + ", ".join(f"{n} {decision}" for decision, n in sorted(plans.items()))
    )
    print(f"{len(atlas.to_review)} need a person to decide → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
