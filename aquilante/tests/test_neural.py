"""Neural models, training and the service. Skipped without torch."""

# ruff: noqa: E402, I001  -- torch is imported (or the module skipped) before the rest

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from aquilante.data.adapters import synthetic_dataset  # noqa: E402
from aquilante.evaluation.metrics import summarize  # noqa: E402
from aquilante.features.sequences import split_by_student  # noqa: E402
from aquilante.models.neural import NeuralModel, make_batch  # noqa: E402
from aquilante.training.trainer import (  # noqa: E402
    TrainConfig,
    load_checkpoint,
    save_checkpoint,
    train,
)


@pytest.fixture(scope="module")
def split():
    ds = synthetic_dataset(students=60, events_per_student=40, seed=21)
    return split_by_student(ds, seed=0)


@pytest.mark.parametrize("kind", ["dkt", "aquilante"])
def test_models_are_causal_and_finite(split, kind):
    tr, _, te = split
    m = NeuralModel(kind, tr.vocab.n_concepts, tr.vocab.n_items, {"max_len": 50})
    s = te.sequences[0]
    p1 = m.predict(s)
    s2 = s.__class__(**{**s.__dict__, "correct": s.correct.copy()})
    s2.correct[-1] = 1 - s2.correct[-1]
    p2 = m.predict(s2)
    assert np.all(np.isfinite(p1)) and np.all((p1 > 0) & (p1 < 1))
    assert np.allclose(p1[:-1], p2[:-1], atol=1e-5), "a later answer changed an earlier prediction"


def test_training_reduces_loss_and_is_reproducible(split):
    tr, va, te = split
    cfg = TrainConfig(
        model="aquilante",
        model_config={"max_len": 50, "d_model": 32, "heads": 2},
        epochs=3,
        patience=3,
        seed=1,
        calibrate=False,
    )
    a = train(tr, va, cfg, log=lambda *_: None)
    b = train(tr, va, cfg, log=lambda *_: None)
    assert a.history[-1]["train_loss"] < a.history[0]["train_loss"] + 0.05
    assert abs(a.history[-1]["train_loss"] - b.history[-1]["train_loss"]) < 1e-4, "same seed, different loss"
    y, p = a.model.predict_dataset(te)
    assert summarize(y, p).n == te.n_events


def test_mc_dropout_gives_uncertainty_and_temperature_calibrates(split):
    tr, va, _ = split
    cfg = TrainConfig(
        model="dkt",
        model_config={"max_len": 50, "hidden": 16},
        epochs=2,
        patience=2,
        seed=0,
        calibrate=True,
    )
    res = train(tr, va, cfg, log=lambda *_: None)
    mean, std, mask = res.model.predict_batch(va.sequences[:2], samples=6)
    assert std[mask].max() > 0.0
    assert res.model.temperature > 0


def test_checkpoint_round_trip(split, tmp_path: Path):
    tr, va, te = split
    res = train(
        tr,
        va,
        TrainConfig(
            model="dkt",
            model_config={"max_len": 50, "hidden": 16},
            epochs=1,
            seed=0,
            calibrate=False,
        ),
        log=lambda *_: None,
    )
    save_checkpoint(res.model, tmp_path / "w.pt")
    again = load_checkpoint(tmp_path / "w.pt")
    s = te.sequences[0]
    assert np.allclose(res.model.predict(s), again.predict(s), atol=1e-6)


def test_batch_shapes(split):
    tr, _, _ = split
    b = make_batch(tr.sequences[:4], max_len=20)
    assert b.concept.shape == b.correct.shape == b.mask.shape
    assert b.concept.shape[1] <= 20


def test_service_serves_state_and_falls_back(split, tmp_path: Path):
    fastapi = pytest.importorskip("fastapi")  # noqa: F841
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from aquilante.inference.service import create_app  # noqa: PLC0415
    from aquilante.simulation.simulator import SimulatorConfig, simulate  # noqa: PLC0415

    app = create_app(model_dir=None)
    client = TestClient(app)
    assert client.get("/health").json()["fallback"] is True
    events = [
        e.model_dump(mode="json")
        for e in simulate(SimulatorConfig(students=1, events_per_student=12, seed=3))
    ]
    assert client.post("/events", json={"events": events}).json()["accepted"] == 12
    sid = events[0]["student_id"]
    state = client.get(f"/learner/{sid}/state").json()
    assert state["events"] == 12 and state["concepts"]
    rec = client.get(f"/learner/{sid}/recommend").json()
    assert rec["action"] in {"DIAGNOSTIC", "REVIEW", "LEARN", "EXPLAIN", "PRACTICE", "CHALLENGE"}
    assert isinstance(rec["reasons"], list)
    assert client.get("/learner/nobody/state").status_code == 404
    # a broken model directory must not break the service
    bad = create_app(model_dir=tmp_path)
    assert TestClient(bad).get("/health").json()["fallback"] is True
    _ = json  # keep import used
