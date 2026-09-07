"""The Learner: Aquilante's public object.

    learner = Learner(model=..., forgetting=..., vocab=...)
    learner.observe(event)            # any number of times, in any order of arrival
    state = learner.state(now=...)    # mastery, confidence, recall per concept
    learner.predict_recall("s0:c3", days_ahead=7)
    learner.recommend()               # next action with reason codes

The state is **derived**, never stored as truth: it is recomputed from the
event history each time, so a better model can re-read the same events and
give a better state. Three quantities per concept:

* ``mastery`` — the sequence model's probability that the learner would
  answer an item on this concept correctly *right now*, if asked. With MC
  dropout, the mean over samples.
* ``confidence`` — how much to trust that number: ``1 − 2·std`` of the MC
  samples, shrunk by how little evidence there is (``attempts / (attempts+3)``).
  Low confidence is a call for a diagnostic question, not a claim.
* ``recall`` — the forgetting model's probability of recall at ``now``,
  given the gap since the last practice of the concept.

Without a neural model (or when it is unavailable), the mastery falls back
to the recency-weighted heuristic — the same one the benchmark measures as a
baseline — so the object always answers, and the answer says which model
produced it (``state.model``).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np

from aquilante.data.schema import LearningEvent
from aquilante.features.sequences import SECONDS_PER_DAY, Sequence, Vocab, build_dataset
from aquilante.memory.forgetting import HalfLifeModel, recall_probability
from aquilante.policy.rules import Recommendation, recommend


@dataclass
class ConceptState:
    concept_id: str
    mastery: float
    confidence: float
    recall: float
    attempts: int
    correct: int
    last_practiced: float | None
    days_since: float | None
    wrong_streak: int
    half_life_days: float | None

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        for k in ("mastery", "confidence", "recall"):
            d[k] = round(d[k], 4)
        if d["days_since"] is not None:
            d["days_since"] = round(d["days_since"], 2)
        if d["half_life_days"] is not None:
            d["half_life_days"] = round(d["half_life_days"], 2)
        return d


@dataclass
class LearnerState:
    student_id: str
    as_of: float
    model: str
    concepts: dict[str, ConceptState] = field(default_factory=dict)
    events: int = 0

    def as_dict(self) -> dict:
        return {
            "student_id": self.student_id,
            "as_of": self.as_of,
            "model": self.model,
            "events": self.events,
            "concepts": {k: v.as_dict() for k, v in self.concepts.items()},
        }


class Learner:
    def __init__(
        self,
        student_id: str,
        *,
        vocab: Vocab | None = None,
        model=None,
        forgetting: HalfLifeModel | None = None,
        prerequisites: dict[str, list[str]] | None = None,
        mc_samples: int = 8,
    ):
        self.student_id = student_id
        self.vocab = vocab or Vocab()
        self.model = model  # a NeuralModel or a SequenceModel, or None
        self.forgetting = forgetting or HalfLifeModel()
        self.prerequisites = prerequisites or {}
        self.mc_samples = mc_samples
        self._events: list[LearningEvent] = []

    # ── events ────────────────────────────────────────────────────────
    def observe(self, event: LearningEvent) -> None:
        if event.student_id != self.student_id:
            raise ValueError("event belongs to another learner")
        self._events.append(event)

    def observe_many(self, events) -> None:
        for e in events:
            self.observe(e)

    @property
    def events(self) -> list[LearningEvent]:
        return sorted(self._events, key=lambda e: (e.timestamp, e.event_id))

    def _sequence(self) -> Sequence | None:
        ds = build_dataset(
            self.events,
            name="live",
            version="live",
            kind="real",
            vocab=self.vocab,
            grow_vocab=False,
            min_events=1,
        )
        return ds.sequences[0] if ds.sequences else None

    # ── state ─────────────────────────────────────────────────────────
    def _mastery_now(
        self, seq: Sequence | None, concepts: list[str]
    ) -> tuple[dict[str, float], dict[str, float], str]:
        """Mastery per concept now = model's prediction for a hypothetical next event on that concept."""
        if seq is None or not concepts:
            return {}, {}, "none"
        from aquilante.models.baselines import MasteryHeuristic  # noqa: PLC0415

        means, stds = {}, {}
        model_name = "mastery_heuristic"
        if self.model is not None and hasattr(self.model, "predict_batch"):
            model_name = getattr(self.model, "name", "neural")
            probes = []
            for c in concepts:
                idx = self.vocab.concept(c, grow=False)
                probes.append(_append_probe(seq, idx))
            try:
                mean, std, mask = self.model.predict_batch(probes, samples=self.mc_samples)
                for i, c in enumerate(concepts):
                    last = int(mask[i].sum()) - 1
                    means[c], stds[c] = float(mean[i][last]), float(std[i][last])
                return means, stds, model_name
            except Exception:  # the model is a helper, never a point of failure
                model_name = "mastery_heuristic(fallback)"
        h = MasteryHeuristic()
        h.concept_prior.p = 0.5
        for c in concepts:
            idx = self.vocab.concept(c, grow=False)
            probe = _append_probe(seq, idx)
            means[c] = float(h.predict(probe)[-1])
            stds[c] = 0.25
        return means, stds, model_name

    def state(self, now: float | None = None) -> LearnerState:
        now = now or time.time()
        evs = self.events
        seq = self._sequence()
        concepts = sorted({e.concept_id for e in evs})
        means, stds, model_name = self._mastery_now(seq, concepts)
        out = LearnerState(student_id=self.student_id, as_of=now, model=model_name, events=len(evs))
        for c in concepts:
            graded = [e for e in evs if e.concept_id == c and e.correct is not None]
            attempts, right = len(graded), sum(1 for e in graded if e.correct)
            last = max((e.timestamp for e in evs if e.concept_id == c), default=None)
            days = None if last is None else max(0.0, (now - last) / SECONDS_PER_DAY)
            streak = 0
            for e in reversed(graded):
                if e.correct:
                    break
                streak += 1
            diff = [e.difficulty for e in graded if e.difficulty is not None]
            h = (
                self.forgetting.half_life(right, attempts - right, float(np.mean(diff)) if diff else -1.0)
                if attempts
                else None
            )
            recall = recall_probability(h, days) if (h is not None and days is not None) else 0.0
            evidence = attempts / (attempts + 3.0)
            conf = max(0.0, min(1.0, (1.0 - 2.0 * stds.get(c, 0.25)) * evidence))
            out.concepts[c] = ConceptState(
                concept_id=c,
                mastery=means.get(c, 0.5),
                confidence=conf,
                recall=recall,
                attempts=attempts,
                correct=right,
                last_practiced=last,
                days_since=days,
                wrong_streak=streak,
                half_life_days=h,
            )
        return out

    def predict_recall(self, concept_id: str, *, days_ahead: float = 0.0, now: float | None = None) -> float:
        s = self.state(now).concepts.get(concept_id)
        if s is None or s.half_life_days is None or s.days_since is None:
            return 0.0
        return recall_probability(s.half_life_days, s.days_since + days_ahead)

    def recommend(self, *, now: float | None = None, in_scope: list[str] | None = None) -> Recommendation:
        st = self.state(now)
        states = {
            c: {
                "mastery": s.mastery,
                "confidence": s.confidence,
                "recall": s.recall,
                "days_since": s.days_since,
                "attempts": s.attempts,
                "last_correct": None,
                "wrong_streak": s.wrong_streak,
            }
            for c, s in st.concepts.items()
        }
        return recommend(states, prerequisites=self.prerequisites, in_scope=in_scope)


def _append_probe(seq: Sequence, concept_idx: int) -> Sequence:
    """The sequence plus one hypothetical event on `concept_idx` now (its target is unknown, set 0)."""
    seen = int((seq.concept == concept_idx).sum())
    right = int(seq.correct[seq.concept == concept_idx].sum())
    last_t = seq.timestamp[-1]
    last_c = seq.timestamp[seq.concept == concept_idx]
    gap_c = 0.0 if len(last_c) == 0 else max(0.0, (last_t - last_c[-1]) / SECONDS_PER_DAY)
    return Sequence(
        student_id=seq.student_id,
        concept=np.append(seq.concept, concept_idx),
        item=np.append(seq.item, 1),
        correct=np.append(seq.correct, 0).astype(np.int8),
        log_gap=np.append(seq.log_gap, 0.0).astype(np.float32),
        log_gap_concept=np.append(seq.log_gap_concept, math.log1p(gap_c)).astype(np.float32),
        prior_seen=np.append(seq.prior_seen, seen).astype(np.int32),
        prior_correct=np.append(seq.prior_correct, right).astype(np.int32),
        response_log_ms=np.append(seq.response_log_ms, 0.0).astype(np.float32),
        hints=np.append(seq.hints, 0).astype(np.int8),
        difficulty=np.append(seq.difficulty, -1.0).astype(np.float32),
        timestamp=np.append(seq.timestamp, last_t),
    )
