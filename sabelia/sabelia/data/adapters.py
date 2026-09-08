"""Dataset adapters: anything → ``LearningEvent``.

Three sources, kept apart by ``kind``:

* ``synthetic`` — the simulator. For pipelines and tests. Never evidence.
* ``public`` — published research datasets, read from files the user has
  downloaded under the dataset's own licence. Sabelia never fetches them.
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

from sabelia.data.schema import EventType, LearningEvent, upgrade
from sabelia.features.sequences import Dataset, Vocab, build_dataset
from sabelia.simulation.simulator import SimulatorConfig, simulate


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


# ── EdNet KT1 (Riiid) ────────────────────────────────────────────────────


def ednet_kt1_events(
    root: Path,
    *,
    questions_csv: Path,
    max_users: int | None = None,
    sample_users: int | None = None,
    seed: int = 0,
) -> Iterator[LearningEvent]:
    """EdNet-KT1: one CSV per user (``u1.csv`` …) with timestamp (ms), solving_id,
    question_id, user_answer, elapsed_time (ms); correctness comes from
    ``questions.csv`` (question_id, correct_answer, tags, …) in the contents
    archive. Concept = the question's first tag; item = the question.
    CC BY-NC 4.0: research use. Download from the official repository
    (https://github.com/riiid/ednet); nothing is fetched here.

    ``max_users`` takes the lowest user ids, which is the order they
    registered in — a slice of the earliest users, not a sample of the
    population. ``sample_users`` takes that many learners spread across the
    whole set by a stable hash instead, and is what a benchmark should use.
    """
    answers: dict[str, str] = {}
    tags: dict[str, str] = {}
    with questions_csv.open(newline="") as f:
        for row in csv.DictReader(f):
            answers[row["question_id"]] = row["correct_answer"].strip().lower()
            first = (row.get("tags") or "").split(";")[0].strip()
            tags[row["question_id"]] = first or "untagged"
    users = sorted(root.glob("u*.csv"), key=lambda p: int(p.stem[1:]) if p.stem[1:].isdigit() else 0)
    if sample_users is not None:
        users = sorted(
            users,
            key=lambda p: hashlib.sha256(f"ednet:{seed}:{p.stem}".encode()).digest(),
        )[:sample_users]
        users.sort(key=lambda p: int(p.stem[1:]) if p.stem[1:].isdigit() else 0)
    elif max_users is not None:
        users = users[:max_users]
    for path in users:
        student = f"ednet-{path.stem}"
        with path.open(newline="") as f:
            for i, row in enumerate(csv.DictReader(f)):
                q = row["question_id"]
                if q not in answers:
                    continue
                elapsed = row.get("elapsed_time") or "0"
                yield LearningEvent(
                    event_id=f"{student}-{i}",
                    student_id=student,
                    concept_id=f"tag:{tags[q]}",
                    item_id=f"question:{q}",
                    timestamp=float(row["timestamp"]) / 1000.0,
                    event_type=EventType.answer,
                    correct=row["user_answer"].strip().lower() == answers[q],
                    response_ms=max(0, int(float(elapsed))),
                    session_id=row.get("solving_id"),
                    source="ednet-kt1",
                )


def ednet_kt1_dataset(
    root: Path,
    questions_csv: Path,
    max_users: int | None = None,
    sample_users: int | None = None,
    seed: int = 0,
) -> Dataset:
    version = file_version(questions_csv)
    if sample_users is not None:
        version += f"+s{sample_users}.{seed}"
    elif max_users is not None:
        version += f"+u{max_users}"
    return build_dataset(
        ednet_kt1_events(
            root,
            questions_csv=questions_csv,
            max_users=max_users,
            sample_users=sample_users,
            seed=seed,
        ),
        name="ednet-kt1",
        version=version,
        kind="public",
    )


# ── Duolingo half-life regression traces ─────────────────────────────────


def duolingo_hlr_events(
    path: Path, *, max_rows: int | None = None, user_fraction: float | None = None
) -> Iterator[LearningEvent]:
    """``settles.acl16.learning_traces.13m.csv(.gz)``: one row per (user, lexeme,
    session): p_recall, timestamp (s), delta (s since last practice), user_id,
    learning_language, ui_language, lexeme_id, lexeme_string, history_seen,
    history_correct, session_seen, session_correct. Emitted as ``recall``
    events; ``correct`` is whether every showing in the session was recalled
    (session_correct == session_seen), the strict reading. Concept and item are
    the lexeme. CC BY-NC 4.0 (Harvard Dataverse doi:10.7910/DVN/N8XJME).

    ``max_rows`` reads a prefix of the file, which is fast but truncates every
    learner's history at the same wall-clock moment. ``user_fraction`` instead
    streams the whole file and keeps every row of a stable pseudorandom subset
    of learners, so the sequences keep their real length and their real gaps —
    the sampling to use when the question is about time. The two can be
    combined (a fraction of learners within a prefix).
    """
    import gzip  # noqa: PLC0415

    def keep(user_id: str) -> bool:
        if user_fraction is None:
            return True
        h = hashlib.sha256(f"duolingo-hlr:{user_id}".encode()).digest()
        return int.from_bytes(h[:8], "big") / 2**64 < user_fraction

    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as f:  # type: ignore[operator]
        for i, row in enumerate(csv.DictReader(f)):
            if max_rows is not None and i >= max_rows:
                break
            if not keep(row["user_id"]):
                continue
            seen = int(row["session_seen"])
            right = int(row["session_correct"])
            yield LearningEvent(
                event_id=f"hlr-{i}",
                student_id=f"duo-{row['user_id']}",
                concept_id=f"lexeme:{row['learning_language']}:{row['lexeme_id']}",
                item_id=f"lexeme:{row['learning_language']}:{row['lexeme_id']}",
                timestamp=float(row["timestamp"]),
                event_type=EventType.recall,
                correct=(right >= seen and seen > 0),
                attempt=max(1, seen),
                source="duolingo-hlr",
                extra={"p_recall": float(row["p_recall"]), "delta_s": float(row["delta"])},
            )


def duolingo_hlr_dataset(
    path: Path, max_rows: int | None = None, user_fraction: float | None = None
) -> Dataset:
    version = (
        file_version(path)
        + (f"+r{max_rows}" if max_rows else "")
        + (f"+u{user_fraction:g}" if user_fraction else "")
    )
    return build_dataset(
        duolingo_hlr_events(path, max_rows=max_rows, user_fraction=user_fraction),
        name="duolingo-hlr",
        version=version,
        kind="public",
    )


# ── registry ─────────────────────────────────────────────────────────────

ADAPTERS = {
    "synthetic": lambda spec: synthetic_dataset(**(spec.get("config") or {})),
    "jsonl": lambda spec: jsonl_dataset(
        Path(spec["path"]), name=spec.get("name"), kind=spec.get("kind", "real")
    ),
    "assistments-2009": lambda spec: assistments_dataset(Path(spec["path"])),
    "ednet-kt1": lambda spec: ednet_kt1_dataset(
        Path(spec["path"]),
        Path(spec["questions"]),
        spec.get("max_users"),
        spec.get("sample_users"),
        spec.get("seed", 0),
    ),
    "duolingo-hlr": lambda spec: duolingo_hlr_dataset(
        Path(spec["path"]), spec.get("max_rows"), spec.get("user_fraction")
    ),
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
    "duolingo_hlr_dataset",
    "duolingo_hlr_events",
    "ednet_kt1_dataset",
    "ednet_kt1_events",
    "file_version",
    "jsonl_dataset",
    "load_dataset",
    "read_jsonl",
    "synthetic_dataset",
    "write_jsonl",
]
