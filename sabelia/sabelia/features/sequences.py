"""Per-learner interaction sequences, the input shape shared by every model.

A ``Sequence`` is one learner's graded events in time order, as integer
arrays: concept index, item index, correctness, and the derived temporal
features (log gap since the previous event, log gap since the previous
event *on the same concept*, how many times that concept was seen before and
how many of those were correct). Exposure events are dropped from the
graded arrays but counted as prior exposures.

Splits are **by learner**, never by event: a model that has seen a learner's
early events and is tested on their later ones is measured on a different,
easier task than predicting a learner it has never met. The split is a
deterministic hash of ``student_id`` and the seed, so it is stable across
runs and machines.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np

from sabelia.data.schema import EventType, LearningEvent

SECONDS_PER_DAY = 86400.0
PAD = 0  # index 0 of every vocabulary is the padding token


@dataclass
class Vocab:
    """Stable string → int maps. Index 0 is reserved for padding; 1 for unknown."""

    concepts: dict[str, int] = field(default_factory=lambda: {"<pad>": 0, "<unk>": 1})
    items: dict[str, int] = field(default_factory=lambda: {"<pad>": 0, "<unk>": 1})

    def concept(self, name: str, grow: bool = True) -> int:
        if name not in self.concepts:
            if not grow:
                return 1
            self.concepts[name] = len(self.concepts)
        return self.concepts[name]

    def item(self, name: str | None, grow: bool = True) -> int:
        key = name or "<unk>"
        if key not in self.items:
            if not grow:
                return 1
            self.items[key] = len(self.items)
        return self.items[key]

    @property
    def n_concepts(self) -> int:
        return len(self.concepts)

    @property
    def n_items(self) -> int:
        return len(self.items)

    def concept_names(self) -> list[str]:
        inv = {v: k for k, v in self.concepts.items()}
        return [inv[i] for i in range(len(inv))]

    def to_dict(self) -> dict:
        return {"concepts": self.concepts, "items": self.items}

    @classmethod
    def from_dict(cls, d: dict) -> Vocab:
        return cls(concepts=dict(d["concepts"]), items=dict(d["items"]))


@dataclass
class Sequence:
    student_id: str
    concept: np.ndarray  # int64 [T]
    item: np.ndarray  # int64 [T]
    correct: np.ndarray  # int8 [T]
    log_gap: np.ndarray  # float32 [T], log1p(days since previous graded event)
    log_gap_concept: np.ndarray  # float32 [T], log1p(days since previous event on this concept)
    prior_seen: np.ndarray  # int32 [T], previous events on this concept
    prior_correct: np.ndarray  # int32 [T], previous correct on this concept
    response_log_ms: np.ndarray  # float32 [T], log1p(response_ms) or 0 when unknown
    hints: np.ndarray  # int8 [T]
    difficulty: np.ndarray  # float32 [T], -1 when unknown
    timestamp: np.ndarray  # float64 [T]
    #: Counts over the learner's whole history, computed once on the full
    #: sequence so that a window keeps the values the full sequence had.
    #: Recomputed from a window they would restart at its first event, and a
    #: long learner's late events would read as a newcomer's.
    position: np.ndarray | None = None  # float [T]: events before t
    learner_correct: np.ndarray | None = None  # float [T]: right answers before t
    concept_streak: np.ndarray | None = None  # float [T]: rights in a row on this concept before t
    last_on_concept: np.ndarray | None = None  # float [T]: last outcome here, -1 if none

    def __len__(self) -> int:
        return int(len(self.correct))

    def window(self, start: int, end: int) -> Sequence:
        """The events in ``[start, end)``, with every feature sliced with them.

        The features are already causal — `prior_seen`, the gaps, the counts
        are computed from what came before each event — so a window keeps its
        meaning. What it loses is the model's view of anything older than the
        window, which is exactly what a windowed model can see anyway.
        """
        return Sequence(
            student_id=self.student_id,
            concept=self.concept[start:end],
            item=self.item[start:end],
            correct=self.correct[start:end],
            log_gap=self.log_gap[start:end],
            log_gap_concept=self.log_gap_concept[start:end],
            prior_seen=self.prior_seen[start:end],
            prior_correct=self.prior_correct[start:end],
            response_log_ms=self.response_log_ms[start:end],
            hints=self.hints[start:end],
            difficulty=self.difficulty[start:end],
            timestamp=self.timestamp[start:end],
            position=None if self.position is None else self.position[start:end],
            learner_correct=None if self.learner_correct is None else self.learner_correct[start:end],
            concept_streak=None if self.concept_streak is None else self.concept_streak[start:end],
            last_on_concept=None if self.last_on_concept is None else self.last_on_concept[start:end],
        )


@dataclass
class Dataset:
    name: str
    version: str
    kind: str  # "real" | "public" | "synthetic"
    vocab: Vocab
    sequences: list[Sequence]

    @property
    def n_events(self) -> int:
        return sum(len(s) for s in self.sequences)

    @property
    def n_students(self) -> int:
        return len(self.sequences)

    def describe(self) -> dict:
        lengths = np.array([len(s) for s in self.sequences]) if self.sequences else np.array([0])
        correct = np.concatenate([s.correct for s in self.sequences]) if self.sequences else np.array([])
        return {
            "name": self.name,
            "version": self.version,
            "kind": self.kind,
            "students": self.n_students,
            "events": self.n_events,
            "concepts": self.vocab.n_concepts - 2,
            "items": self.vocab.n_items - 2,
            "base_rate": float(correct.mean()) if correct.size else float("nan"),
            "seq_len_median": float(np.median(lengths)),
            "seq_len_max": int(lengths.max()),
        }


def build_dataset(
    events: Iterable[LearningEvent],
    *,
    name: str,
    version: str,
    kind: str,
    vocab: Vocab | None = None,
    grow_vocab: bool = True,
    min_events: int = 2,
) -> Dataset:
    """Group events by learner, sort by time, derive temporal features."""
    vocab = vocab or Vocab()
    by_student: dict[str, list[LearningEvent]] = defaultdict(list)
    for e in events:
        by_student[e.student_id].append(e)

    sequences: list[Sequence] = []
    for student_id in sorted(by_student):
        evs = sorted(by_student[student_id], key=lambda e: (e.timestamp, e.event_id))
        seen: dict[str, int] = defaultdict(int)
        right: dict[str, int] = defaultdict(int)
        last_any: float | None = None
        last_on: dict[str, float] = {}
        rows = []
        for e in evs:
            gap = 0.0 if last_any is None else max(0.0, (e.timestamp - last_any) / SECONDS_PER_DAY)
            gap_c = (
                0.0
                if e.concept_id not in last_on
                else max(0.0, (e.timestamp - last_on[e.concept_id]) / SECONDS_PER_DAY)
            )
            if e.event_type is EventType.exposure or e.correct is None:
                seen[e.concept_id] += 1
                last_on[e.concept_id] = e.timestamp
                last_any = e.timestamp
                continue
            rows.append(
                (
                    vocab.concept(e.concept_id, grow_vocab),
                    vocab.item(e.item_id, grow_vocab),
                    1 if e.correct else 0,
                    math.log1p(gap),
                    math.log1p(gap_c),
                    seen[e.concept_id],
                    right[e.concept_id],
                    math.log1p(e.response_ms) if e.response_ms else 0.0,
                    min(e.hints, 3),
                    -1.0 if e.difficulty is None else float(e.difficulty),
                    e.timestamp,
                )
            )
            seen[e.concept_id] += 1
            right[e.concept_id] += 1 if e.correct else 0
            last_on[e.concept_id] = e.timestamp
            last_any = e.timestamp
        if len(rows) < min_events:
            continue
        cols = list(zip(*rows, strict=True))
        position, learner_correct, streak, last = _history(
            np.asarray(cols[0], dtype=np.int64), np.asarray(cols[2], dtype=np.float64)
        )
        sequences.append(
            Sequence(
                student_id=student_id,
                concept=np.asarray(cols[0], dtype=np.int64),
                item=np.asarray(cols[1], dtype=np.int64),
                correct=np.asarray(cols[2], dtype=np.int8),
                log_gap=np.asarray(cols[3], dtype=np.float32),
                log_gap_concept=np.asarray(cols[4], dtype=np.float32),
                prior_seen=np.asarray(cols[5], dtype=np.int32),
                prior_correct=np.asarray(cols[6], dtype=np.int32),
                response_log_ms=np.asarray(cols[7], dtype=np.float32),
                hints=np.asarray(cols[8], dtype=np.int8),
                difficulty=np.asarray(cols[9], dtype=np.float32),
                timestamp=np.asarray(cols[10], dtype=np.float64),
                position=position,
                learner_correct=learner_correct,
                concept_streak=streak,
                last_on_concept=last,
            )
        )
    return Dataset(name=name, version=version, kind=kind, vocab=vocab, sequences=sequences)


def _history(
    concept: np.ndarray, correct: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Position, running rights, per-concept streak and last outcome — all before t."""
    n = len(correct)
    position = np.arange(n, dtype=np.float32)
    learner_correct = np.concatenate([[0.0], np.cumsum(correct)[:-1]]).astype(np.float32)
    streak_out = np.zeros(n, dtype=np.float32)
    last_out = np.full(n, -1.0, dtype=np.float32)
    streak: dict[int, float] = {}
    last: dict[int, float] = {}
    for t in range(n):
        c = int(concept[t])
        streak_out[t] = streak.get(c, 0.0)
        last_out[t] = last.get(c, -1.0)
        streak[c] = streak.get(c, 0.0) + 1 if correct[t] else 0.0
        last[c] = float(correct[t])
    return position, learner_correct, streak_out, last_out


def _bucket(student_id: str, seed: int) -> float:
    h = hashlib.sha256(f"{seed}:{student_id}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def split_by_student(
    dataset: Dataset, *, seed: int = 0, val: float = 0.1, test: float = 0.2
) -> tuple[Dataset, Dataset, Dataset]:
    """Deterministic train/val/test split on learner identity."""
    train, valid, tests = [], [], []
    for s in dataset.sequences:
        u = _bucket(s.student_id, seed)
        if u < test:
            tests.append(s)
        elif u < test + val:
            valid.append(s)
        else:
            train.append(s)
    mk = lambda part, seqs: Dataset(  # noqa: E731
        name=f"{dataset.name}/{part}",
        version=dataset.version,
        kind=dataset.kind,
        vocab=dataset.vocab,
        sequences=seqs,
    )
    return mk("train", train), mk("val", valid), mk("test", tests)
