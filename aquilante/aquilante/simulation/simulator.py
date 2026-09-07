"""A synthetic learner simulator.

Each simulated learner has a latent *skill* per concept that grows with
practice and decays with time; the probability of a correct answer is a
logistic function of skill minus item difficulty. The generating process is
deliberately close to a Rasch/IRT model with power-law forgetting, so that
(a) the baselines have something they *can* fit and (b) the sequence models
have something they *should* fit better than the baselines when learning
rates differ across learners.

Concepts are arranged in a prerequisite chain per subject: practising a
concept transfers a fraction of the gain to its prerequisite (you cannot do
derivatives without exercising algebra) and a weak prerequisite lowers the
effective skill on the dependent concept.

This is not a claim about how people learn. It is a data generator whose
parameters are known, which is what makes it useful for testing that the
pipeline recovers what it should. Results on synthetic data are never
evidence of real-world quality; the dataset registry marks them ``synthetic``.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np

from aquilante.data.schema import EventType, LearningEvent

SECONDS_PER_DAY = 86400.0


@dataclass(frozen=True)
class SimulatorConfig:
    students: int = 200
    subjects: int = 3
    concepts_per_subject: int = 8
    items_per_concept: int = 6
    events_per_student: int = 120
    seed: int = 7
    # learner population
    learning_rate: tuple[float, float] = (0.15, 0.55)  # uniform range, skill gain per success
    forgetting_rate: tuple[float, float] = (0.05, 0.35)  # uniform range, decay per log-day
    initial_skill_sd: float = 0.8
    # items
    difficulty_sd: float = 0.9
    # time between events, in days (log-normal)
    gap_days_median: float = 0.6
    gap_days_sigma: float = 1.1
    prerequisite_transfer: float = 0.35
    prerequisite_penalty: float = 0.5
    source: str = "synthetic"


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


@dataclass
class _Learner:
    student_id: str
    learning_rate: float
    forgetting_rate: float
    skill: np.ndarray  # latent skill per concept, logit scale
    last_practice: np.ndarray  # timestamp per concept, NaN if never
    sessions: int = 0
    extra: dict = field(default_factory=dict)


def simulate(config: SimulatorConfig) -> Iterator[LearningEvent]:
    """Yield events in time order per learner (learners are interleaved by id)."""
    rng = np.random.default_rng(config.seed)
    n_concepts = config.subjects * config.concepts_per_subject
    concept_ids = [f"s{s}:c{c}" for s in range(config.subjects) for c in range(config.concepts_per_subject)]
    # prerequisite of concept k within a subject is k-1
    prereq = np.full(n_concepts, -1, dtype=int)
    for s in range(config.subjects):
        for c in range(1, config.concepts_per_subject):
            k = s * config.concepts_per_subject + c
            prereq[k] = k - 1
    item_difficulty = rng.normal(0.0, config.difficulty_sd, size=(n_concepts, config.items_per_concept))
    # difficulty on the 0..1 scale the schema uses, by rank within the whole pool
    flat = item_difficulty.ravel()
    ranks = flat.argsort().argsort() / max(1, flat.size - 1)
    difficulty01 = ranks.reshape(item_difficulty.shape)

    t0 = 1_700_000_000.0  # a fixed epoch so runs are reproducible
    event_counter = 0
    for i in range(config.students):
        learner = _Learner(
            student_id=f"sim-{i:05d}",
            learning_rate=float(rng.uniform(*config.learning_rate)),
            forgetting_rate=float(rng.uniform(*config.forgetting_rate)),
            skill=rng.normal(0.2, config.initial_skill_sd, size=n_concepts),
            last_practice=np.full(n_concepts, np.nan),
        )
        t = t0 + float(rng.uniform(0, 30)) * SECONDS_PER_DAY
        # learners work through subjects mostly in prerequisite order, with noise
        focus = int(rng.integers(config.subjects))
        session = f"{learner.student_id}-s0"
        for n in range(config.events_per_student):
            gap_days = float(rng.lognormal(math.log(config.gap_days_median), config.gap_days_sigma))
            t += gap_days * SECONDS_PER_DAY
            if gap_days > 0.5:
                learner.sessions += 1
                session = f"{learner.student_id}-s{learner.sessions}"
            if rng.random() < 0.08:
                focus = int(rng.integers(config.subjects))
            # pick a concept: mostly the weakest-not-yet-mastered in the focus subject
            base = focus * config.concepts_per_subject
            sub = learner.skill[base : base + config.concepts_per_subject]
            if rng.random() < 0.7:
                c_local = int(np.argmax(sub < 1.0)) if (sub < 1.0).any() else int(rng.integers(len(sub)))
            else:
                c_local = int(rng.integers(len(sub)))
            k = base + c_local
            item = int(rng.integers(config.items_per_concept))

            # forgetting: skill decays with log time since last practice
            if not math.isnan(learner.last_practice[k]):
                days = max(1e-3, (t - learner.last_practice[k]) / SECONDS_PER_DAY)
                learner.skill[k] -= learner.forgetting_rate * math.log1p(days)
            effective = learner.skill[k]
            if prereq[k] >= 0 and learner.skill[prereq[k]] < 0.0:
                effective -= config.prerequisite_penalty * (-learner.skill[prereq[k]])
            p_correct = _sigmoid(effective - item_difficulty[k, item])
            correct = bool(rng.random() < p_correct)
            # response time: slower when uncertain, on a log-normal
            uncertainty = 1.0 - abs(2 * p_correct - 1)
            response_ms = int(rng.lognormal(math.log(9000 + 12000 * uncertainty), 0.45))
            hints = int(rng.random() < 0.15 * (1 - p_correct))
            confidence = float(np.clip(p_correct + rng.normal(0, 0.15), 0, 1)) if rng.random() < 0.4 else None

            # learning: a success raises skill by the learning rate, a failure by a third
            gain = learner.learning_rate * (1.0 if correct else 0.35)
            learner.skill[k] += gain
            if prereq[k] >= 0:
                learner.skill[prereq[k]] += config.prerequisite_transfer * gain
            learner.last_practice[k] = t

            event_counter += 1
            yield LearningEvent(
                event_id=f"{config.source}-{event_counter:09d}",
                student_id=learner.student_id,
                concept_id=concept_ids[k],
                item_id=f"{concept_ids[k]}:i{item}",
                timestamp=t,
                event_type=EventType.answer if rng.random() < 0.8 else EventType.recall,
                correct=correct,
                difficulty=float(difficulty01[k, item]),
                response_ms=response_ms,
                hints=hints,
                attempt=1,
                confidence=confidence,
                session_id=session,
                source=config.source,
                extra={"true_p": round(p_correct, 4)},
            )


def prerequisite_edges(config: SimulatorConfig) -> list[tuple[str, str]]:
    """(prerequisite, dependent) pairs of the simulated concept graph."""
    edges = []
    for s in range(config.subjects):
        for c in range(1, config.concepts_per_subject):
            edges.append((f"s{s}:c{c - 1}", f"s{s}:c{c}"))
    return edges
