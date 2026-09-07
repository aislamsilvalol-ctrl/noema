"""The inference service: a small, typed HTTP surface for a product.

    POST /events              append learning events (pseudonymous ids only)
    GET  /learner/{id}/state  mastery · confidence · recall per concept
    GET  /learner/{id}/recall?concept=…&days_ahead=…
    GET  /learner/{id}/recommend
    GET  /health              which model is serving, and whether it is the fallback

State is kept in memory per process here; a deployment plugs a store into
``EventStore``. The service never fails a request because the neural model
failed: the heuristic answers and ``model`` in the response says so.
"""

import json
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel

from aquilante.data.schema import LearningEvent
from aquilante.features.sequences import Vocab
from aquilante.inference.learner import Learner
from aquilante.memory.forgetting import HalfLifeModel


class EventsIn(BaseModel):
    events: list[LearningEvent]


class EventStore:
    def __init__(self):
        self._by_student: dict[str, list[LearningEvent]] = defaultdict(list)

    def append(self, events: list[LearningEvent]) -> int:
        for e in events:
            self._by_student[e.student_id].append(e)
        return len(events)

    def events(self, student_id: str) -> list[LearningEvent]:
        return list(self._by_student.get(student_id, []))


def load_model(model_dir: Path | None):
    if model_dir is None:
        return None, Vocab(), "heuristic"
    try:
        from aquilante.training.trainer import load_checkpoint  # noqa: PLC0415

        model = load_checkpoint(model_dir / "weights.pt")
        vocab = Vocab.from_dict(json.loads((model_dir / "vocab.json").read_text()))
        meta = json.loads((model_dir / "model.json").read_text())
        return model, vocab, f"{meta['name']}@{meta['version']}"
    except Exception as exc:  # a missing torch or a bad file: serve the heuristic, say so
        return None, Vocab(), f"heuristic(fallback: {type(exc).__name__})"


def create_app(*, model_dir: Path | None = None, prerequisites: dict[str, list[str]] | None = None):
    from fastapi import FastAPI, HTTPException  # noqa: PLC0415

    model, vocab, model_label = load_model(model_dir)
    forgetting = HalfLifeModel()
    store = EventStore()
    app = FastAPI(
        title="Aquilante",
        version="0.1.0",
        description="Adaptive Neural Learner Modeling Engine — inference service",
    )

    def learner_for(student_id: str) -> Learner:
        lr = Learner(student_id, vocab=vocab, model=model, forgetting=forgetting, prerequisites=prerequisites)
        lr.observe_many(store.events(student_id))
        return lr

    @app.get("/health")
    def health():
        return {"status": "ok", "model": model_label, "fallback": model is None}

    @app.post("/events")
    def post_events(body: EventsIn):
        n = store.append(body.events)
        return {"accepted": n}

    @app.get("/learner/{student_id}/state")
    def state(student_id: str):
        if not store.events(student_id):
            raise HTTPException(404, "no events for this learner")
        return learner_for(student_id).state().as_dict()

    @app.get("/learner/{student_id}/recall")
    def recall(student_id: str, concept: str, days_ahead: float = 0.0):
        lr = learner_for(student_id)
        return {
            "concept_id": concept,
            "days_ahead": days_ahead,
            "recall": round(lr.predict_recall(concept, days_ahead=days_ahead), 4),
        }

    @app.get("/learner/{student_id}/recommend")
    def rec(student_id: str):
        return learner_for(student_id).recommend().as_dict()

    return app
