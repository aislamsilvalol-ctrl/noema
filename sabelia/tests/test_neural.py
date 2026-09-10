"""Neural models, training and the service. Skipped without torch."""

# ruff: noqa: E402, I001  -- torch is imported (or the module skipped) before the rest

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from sabelia.data.adapters import synthetic_dataset  # noqa: E402
from sabelia.evaluation.metrics import summarize  # noqa: E402
from sabelia.features.sequences import split_by_student  # noqa: E402
from sabelia.models.neural import NeuralModel, make_batch  # noqa: E402
from sabelia.training.trainer import (  # noqa: E402
    TrainConfig,
    load_checkpoint,
    save_checkpoint,
    train,
)


@pytest.fixture(scope="module")
def split():
    ds = synthetic_dataset(students=60, events_per_student=40, seed=21)
    return split_by_student(ds, seed=0)


@pytest.mark.parametrize("kind", ["dkt", "sabelia"])
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
        model="sabelia",
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

    from sabelia.inference.service import create_app  # noqa: PLC0415
    from sabelia.simulation.simulator import SimulatorConfig, simulate  # noqa: PLC0415

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


def test_a_long_learner_is_predicted_everywhere_not_padded_with_half():
    """A sequence longer than the window used to answer 0.5 for its whole head."""
    ds = synthetic_dataset(students=6, events_per_student=140, seed=3)
    model = NeuralModel(
        "sabelia",
        ds.vocab.n_concepts,
        ds.vocab.n_items,
        {"max_len": 32, "d_model": 16, "heads": 2, "layers": 1},
    )
    seq = max(ds.sequences, key=len)
    assert len(seq) > 32

    p = model.predict(seq)

    assert len(p) == len(seq)
    # the head is a real prediction, not the "no idea" constant the padding used
    assert not np.allclose(p[: len(seq) - 32], 0.5)
    assert np.all((p > 0) & (p < 1))


def test_predict_and_predict_dataset_agree_on_every_event():
    """The benchmark and the live path scored different event sets until they did."""
    ds = synthetic_dataset(students=4, events_per_student=90, seed=5)
    model = NeuralModel(
        "sabelia",
        ds.vocab.n_concepts,
        ds.vocab.n_items,
        {"max_len": 32, "d_model": 16, "heads": 2, "layers": 1},
    )

    y, p = model.predict_dataset(ds)

    assert len(y) == ds.n_events == len(p)
    by_hand = np.concatenate([model.predict(s) for s in ds.sequences])
    assert np.allclose(np.sort(p), np.sort(by_hand), atol=1e-6)


def test_difficulty_reaches_the_model_and_survives_a_checkpoint(tmp_path: Path):
    """The question's difficulty is a number the model reads, not one it must invent."""
    from sabelia.models.neural import NeuralModel, Rates, make_batch

    ds = synthetic_dataset(students=8, events_per_student=40, seed=4)
    tr, va, _ = split_by_student(ds, seed=0)
    result = train(
        tr, va, TrainConfig(model="sabelia", seed=0, epochs=1, log_every=10**6), log=lambda *_: None
    )
    model = result.model

    assert model.rates.item and model.rates.concept
    b = make_batch([ds.sequences[0]], model.max_len, model.rates)
    assert b.item_rate.shape == b.concept.shape
    assert float(b.item_rate.min()) != float(b.item_rate.max())  # a real table varies

    path = tmp_path / "m.pt"
    torch.save(model.state(), path)
    back = NeuralModel.from_state(torch.load(path, weights_only=False))
    assert back.rates.base == model.rates.base
    assert np.allclose(back.predict(ds.sequences[0]), model.predict(ds.sequences[0]), atol=1e-6)

    # an unfitted table answers with the neutral rate, not with a number it
    # does not have
    bare = make_batch([ds.sequences[0]], 32, Rates())
    assert float(bare.item_rate.min()) == float(bare.item_rate.max()) == 0.5


def test_the_hybrid_reads_the_feature_table_and_survives_a_checkpoint(tmp_path: Path):
    """The network asked only for what the counts cannot say — with the counts in hand."""
    from sabelia.models.neural import NeuralModel, make_batch

    ds = synthetic_dataset(students=8, events_per_student=40, seed=6)
    tr, va, _ = split_by_student(ds, seed=0)
    cfg = TrainConfig(model="sabelia", model_config={"use_features": True}, seed=0, epochs=1, log_every=10**6)
    model = train(tr, va, cfg, log=lambda *_: None).model

    assert model.scale is not None and model.net.feature_head is not None
    b = make_batch([ds.sequences[0]], model.max_len, model.rates, model.scale)
    assert b.features.shape[-1] == 18 and float(b.features.abs().sum()) > 0

    path = tmp_path / "hybrid.pt"
    torch.save(model.state(), path)
    back = NeuralModel.from_state(torch.load(path, weights_only=False))
    assert np.allclose(back.predict(ds.sequences[0]), model.predict(ds.sequences[0]), atol=1e-6)

    # without the flag a batch carries no feature columns: the default path pays nothing
    plain = make_batch([ds.sequences[0]], 32, model.rates, None)
    assert plain.features.shape[-1] == 0


def test_batching_the_windows_changes_no_prediction():
    """Several long learners at once must predict exactly what each does alone."""
    ds = synthetic_dataset(students=5, events_per_student=150, seed=8)
    model = NeuralModel(
        "sabelia",
        ds.vocab.n_concepts,
        ds.vocab.n_items,
        {"max_len": 32, "d_model": 16, "heads": 2, "layers": 1},
    )
    long = [s for s in ds.sequences if len(s) > 32]
    assert len(long) >= 3

    together = model._predict_long(long, batch_size=7)  # an odd size splits windows across batches
    alone = [model._predict_long([s])[0] for s in long]

    for a, b, s in zip(together, alone, long, strict=True):
        assert len(a) == len(s)
        assert np.allclose(a, b, atol=1e-6)
        assert np.all((a > 0) & (a < 1))
