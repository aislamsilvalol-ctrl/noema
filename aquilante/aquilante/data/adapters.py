"""Dataset adapters: anything → ``LearningEvent``.

Three sources, kept apart by ``kind``:

* ``synthetic`` — the simulator. For pipelines and tests. Never evidence.
* ``public`` — published research datasets, read from files the user has
  downloaded under the dataset's own licence. Aquilante never fetches them.
* ``real`` — a product's own events (Noema exports pseudonymised JSONL).

Every adapter records a **dataset version**: a content hash of the file (or
of the simulator config), so an experiment can say exactly which data it saw.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable, Iterator
from dataclasses import asdict
from pathlib import Path

from aquilante.data.schema import EventType, LearningEvent, upgrade
from aquilante.features.sequences import Dataset, Vocab, build_dataset
from aquilante.simulation.simulator import SimulatorConfig, simulate


def file_version(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()[:16]


# ── synthetic ────────────────────────────────────────────────────────────


def synthetic_dataset(config: SimulatorConfig | None = None, **kwargs) -> Dataset:
    config = config or SimulatorConfig(**kwargs)
    version = "sim:" + hashlib.sha256(json.dumps(asdict(config), sort_keys=True).encode()).hexdigest()[:12]
    return build_dataset(simulate(config), name="synthetic", version=version, kind="synthetic")


# ── JSONL of LearningEvent (Noema exports, or anyone's) ──────────────────


def read_jsonl(path: Path) -> Iterator[LearningEvent]:
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                yield upgrade(json.loads(line))


def jsonl_dataset(path: Path, *, name: str | None = None, kind: str = "real") -> Dataset:
    return build_dataset(read_jsonl(path), name=name or path.stem, version=file_version(path), kind=kind)


def write_jsonl(events: Iterable[LearningEvent], path: Path) -> int:
    n = 0
    with path.open("w") as f:
        for e in events:
            f.write(e.model_dump_json() + "\n")
            n += 1
    return n


# ── ASSISTments 2009-2010 skill builder ──────────────────────────────────

ASSISTMENTS_COLUMNS = {
    "order_id": "order_id",
    "user_id": "user_id",
    "problem_id": "problem_id",
    "skill_id": "skill_id",
    "skill_name": "skill_name",
    "correct": "correct",
    "original": "original",
    "attempt_count": "attempt_count",
    "ms_first_response": "ms_first_response",
    "hint_count": "hint_count",
}


def assistments_events(
    path: Path, *, drop_scaffolding: bool = True, dedupe: bool = True
) -> Iterator[LearningEvent]:
    """The 2009-2010 skill-builder CSV (``skill_builder_data.csv``).

    Known issues, handled as the literature recommends (Xiong et al. 2016):
    rows without a skill are dropped; scaffolding rows (``original == 0``) are
    dropped by default; a problem tagged with several skills appears once per
    skill in the file and is kept once (first skill) when ``dedupe`` is set.
    The file carries no timestamp; ``order_id`` is used as the time axis,
    which preserves order but makes the day gaps meaningless — the temporal
    features are then flat and models cannot use forgetting on it. Say so
    when reporting.
    """
    seen_orders: set[str] = set()
    with path.open(newline="", encoding="latin-1") as f:
        reader = csv.DictReader(f)
        for row in reader:
            skill = (row.get("skill_id") or "").strip()
            if not skill or skill.lower() == "nan":
                continue
            if drop_scaffolding and (row.get("original") or "1").strip() == "0":
                continue
            order = row["order_id"].strip()
            if dedupe:
                if order in seen_orders:
                    continue
                seen_orders.add(order)
            ms = row.get("ms_first_response")
            try:
                response_ms = int(float(ms)) if ms not in (None, "", "nan") else None
            except ValueError:
                response_ms = None
            attempts = row.get("attempt_count") or "1"
            yield LearningEvent(
                event_id=f"assist09-{order}",
                student_id=f"assist09-u{row['user_id'].strip()}",
                concept_id=f"skill:{skill.split('_')[0]}",
                item_id=f"problem:{row['problem_id'].strip()}",
                timestamp=float(int(order)),  # order, not seconds; see docstring
                event_type=EventType.answer,
                correct=(row["correct"].strip() == "1"),
                response_ms=max(0, response_ms) if response_ms is not None else None,
                hints=int(float(row.get("hint_count") or 0)),
                attempt=max(1, int(float(attempts))),
                source="assistments-2009",
            )


def assistments_dataset(path: Path) -> Dataset:
    return build_dataset(
        assistments_events(path), name="assistments-2009", version=file_version(path), kind="public"
    )


# ── registry ─────────────────────────────────────────────────────────────

ADAPTERS = {
    "synthetic": lambda spec: synthetic_dataset(**(spec.get("config") or {})),
    "jsonl": lambda spec: jsonl_dataset(
        Path(spec["path"]), name=spec.get("name"), kind=spec.get("kind", "real")
    ),
    "assistments-2009": lambda spec: assistments_dataset(Path(spec["path"])),
}


def load_dataset(spec: dict) -> Dataset:
    """``{"adapter": "synthetic", "config": {...}}`` or ``{"adapter": "assistments-2009", "path": ...}``."""
    adapter = spec.get("adapter")
    if adapter not in ADAPTERS:
        raise KeyError(f"unknown dataset adapter {adapter!r}; known: {sorted(ADAPTERS)}")
    return ADAPTERS[adapter](spec)


__all__ = [
    "ADAPTERS",
    "Vocab",
    "assistments_dataset",
    "assistments_events",
    "file_version",
    "jsonl_dataset",
    "load_dataset",
    "read_jsonl",
    "synthetic_dataset",
    "write_jsonl",
]
