"""Unit and pipeline tests that need only NumPy."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from aquilante.data.adapters import jsonl_dataset, synthetic_dataset, write_jsonl
from aquilante.data.schema import SCHEMA_VERSION, EventType, LearningEvent, upgrade
from aquilante.evaluation.metrics import auc, expected_calibration_error, log_loss, summarize
from aquilante.experiments.registry import ExperimentRun, Registry
from aquilante.features.sequences import split_by_student
from aquilante.inference.learner import Learner
from aquilante.memory.forgetting import HalfLifeModel, recall_probability
from aquilante.models.baselines import BKT, PFA, ConceptMean, GlobalMean, MasteryHeuristic
from aquilante.policy.rules import Action, recommend
from aquilante.simulation.simulator import SimulatorConfig, simulate

# ── schema ────────────────────────────────────────────────────────────────


def test_graded_events_need_an_outcome():
    with pytest.raises(ValueError):
        LearningEvent(
            event_id="e", student_id="s", concept_id="c", timestamp=0.0, event_type=EventType.answer
        )
    e = LearningEvent(
        event_id="e", student_id="s", concept_id="c", timestamp=0.0, event_type=EventType.exposure
    )
    assert not e.is_graded


def test_upgrade_refuses_future_versions_and_stamps_current():
    e = upgrade({"event_id": "e", "student_id": "s", "concept_id": "c", "timestamp": 1.0, "correct": True})
    assert e.schema_version == SCHEMA_VERSION
    with pytest.raises(ValueError):
        upgrade(
            {
                "schema_version": SCHEMA_VERSION + 1,
                "event_id": "e",
                "student_id": "s",
                "concept_id": "c",
                "timestamp": 1.0,
                "correct": True,
            }
        )


# ── simulator and features ────────────────────────────────────────────────


def test_simulator_is_deterministic_and_time_ordered():
    a = list(simulate(SimulatorConfig(students=3, events_per_student=20, seed=1)))
    b = list(simulate(SimulatorConfig(students=3, events_per_student=20, seed=1)))
    assert [e.event_id for e in a] == [e.event_id for e in b]
    assert [e.correct for e in a] == [e.correct for e in b]
    for sid in {e.student_id for e in a}:
        ts = [e.timestamp for e in a if e.student_id == sid]
        assert ts == sorted(ts)


def test_sequence_features_only_look_backwards():
    ds = synthetic_dataset(students=2, events_per_student=30, seed=2)
    s = ds.sequences[0]
    for t in range(len(s)):
        c = s.concept[t]
        assert s.prior_seen[t] == int((s.concept[:t] == c).sum())
        assert s.prior_correct[t] == int(s.correct[:t][s.concept[:t] == c].sum())
    assert s.log_gap[0] == 0.0


def test_split_is_by_student_and_stable():
    ds = synthetic_dataset(students=100, events_per_student=10, seed=5)
    tr, va, te = split_by_student(ds, seed=0)
    ids = lambda d: {s.student_id for s in d.sequences}  # noqa: E731
    assert ids(tr).isdisjoint(ids(te)) and ids(tr).isdisjoint(ids(va))
    tr2, _, te2 = split_by_student(ds, seed=0)
    assert ids(tr) == ids(tr2) and ids(te) == ids(te2)
    assert 10 <= len(te.sequences) <= 30


def test_jsonl_round_trip(tmp_path: Path):
    events = list(simulate(SimulatorConfig(students=2, events_per_student=5, seed=1)))
    out = tmp_path / "e.jsonl"
    assert write_jsonl(events, out) == 10
    ds = jsonl_dataset(out, kind="synthetic")
    assert ds.n_events == 10 and ds.version.startswith("sha256:")


# ── metrics ───────────────────────────────────────────────────────────────


def test_metrics_against_known_values():
    y = [0, 0, 1, 1]
    p = [0.1, 0.4, 0.35, 0.8]
    assert abs(auc(y, p) - 0.75) < 1e-9
    assert abs(log_loss([1], [0.5]) - np.log(2)) < 1e-9
    assert expected_calibration_error([1, 1, 0, 0], [0.5, 0.5, 0.5, 0.5]) < 1e-9
    m = summarize(y, p)
    assert m.n == 4 and 0 <= m.ece <= 1


def test_auc_handles_ties_and_degenerate_labels():
    assert abs(auc([0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5]) - 0.5) < 1e-9
    assert np.isnan(auc([1, 1], [0.2, 0.9]))


# ── baselines ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def small_split():
    ds = synthetic_dataset(students=120, events_per_student=60, seed=11)
    return split_by_student(ds, seed=0)


def test_baselines_beat_the_base_rate(small_split):
    tr, _, te = small_split
    floor = summarize(*GlobalMean().fit(tr).predict_dataset(te))
    assert abs(floor.auc - 0.5) < 1e-9
    for model in (ConceptMean(), MasteryHeuristic(), PFA(epochs=10), BKT(em_iters=4)):
        m = summarize(*model.fit(tr).predict_dataset(te))
        assert m.auc > 0.55, model.name
        assert m.log_loss < floor.log_loss + 0.02, model.name


def test_predictions_are_causal(small_split):
    """Changing a later answer must not change an earlier prediction."""
    tr, _, te = small_split
    model = MasteryHeuristic().fit(tr)
    s = te.sequences[0]
    before = model.predict(s).copy()
    s2 = s.__class__(**{**s.__dict__, "correct": s.correct.copy()})
    s2.correct[-1] = 1 - s2.correct[-1]
    after = model.predict(s2)
    assert np.allclose(before[:-1], after[:-1])


def test_bkt_parameters_are_within_bounds(small_split):
    tr, _, _ = small_split
    m = BKT(em_iters=3).fit(tr)
    for L0, T, G, S, F in m.params_by_concept.values():
        assert 0 < L0 < 1 and 0 < T < 1 and G <= 0.5 and S <= 0.5 and F == 0.0


# ── forgetting ────────────────────────────────────────────────────────────


def test_recall_decays_with_time_and_grows_with_half_life():
    assert recall_probability(10, 0) == 1.0
    assert abs(recall_probability(10, 10) - 0.5) < 1e-9
    assert recall_probability(20, 10) > recall_probability(10, 10)


def test_half_life_model_fits_without_nan(small_split):
    tr, _, te = small_split
    m = HalfLifeModel(epochs=2).fit(tr)
    assert np.all(np.isfinite(m.theta))
    p = m.predict(te.sequences[0])
    assert np.all((p >= 0) & (p <= 1))


# ── learner and policy ────────────────────────────────────────────────────


def _event(i, concept, correct, t, student="s1"):
    return LearningEvent(
        event_id=f"e{i}",
        student_id=student,
        concept_id=concept,
        timestamp=t,
        correct=correct,
        difficulty=0.5,
    )


def test_learner_with_no_history_answers_and_recommends_learning():
    lr = Learner("new")
    st = lr.state(now=1000.0)
    assert st.concepts == {} and st.events == 0
    rec = lr.recommend(now=1000.0, in_scope=["a"])
    assert rec.action is Action.learn and rec.concept_id == "a"


def test_learner_state_is_derived_from_events_and_falls_back_to_heuristic():
    lr = Learner("s1")
    day = 86400.0
    for i, ok in enumerate([True, True, False, True]):
        lr.observe(_event(i, "a", ok, i * day))
    st = lr.state(now=4 * day)
    a = st.concepts["a"]
    assert a.attempts == 4 and a.correct == 3 and a.wrong_streak == 0
    assert 0 < a.mastery < 1 and 0 <= a.confidence <= 1 and 0 < a.recall <= 1
    assert st.model.startswith("mastery_heuristic")
    later = lr.predict_recall("a", days_ahead=30, now=4 * day)
    assert later < a.recall


def test_learner_rejects_other_students_events():
    lr = Learner("s1")
    with pytest.raises(ValueError):
        lr.observe(_event(1, "a", True, 0.0, student="s2"))


def test_policy_reasons_are_structured():
    states = {
        "algebra": {
            "mastery": 0.9,
            "confidence": 0.8,
            "recall": 0.4,
            "days_since": 12.0,
            "attempts": 6,
            "last_correct": True,
            "wrong_streak": 0,
        },
        "calculus": {
            "mastery": 0.0,
            "confidence": 0.0,
            "recall": 0.0,
            "days_since": None,
            "attempts": 0,
            "last_correct": None,
            "wrong_streak": 0,
        },
    }
    rec = recommend(states, prerequisites={"calculus": ["algebra"]})
    assert rec.action is Action.review and rec.concept_id == "algebra"
    assert any(r.startswith("recall_predicted:") for r in rec.reasons)
    assert any(r.startswith("days_since_practice:") for r in rec.reasons)
    low_conf = {
        "x": {
            "mastery": 0.8,
            "confidence": 0.1,
            "recall": 0.9,
            "days_since": 1.0,
            "attempts": 2,
            "last_correct": True,
            "wrong_streak": 0,
        }
    }
    assert recommend(low_conf).action is Action.diagnostic


def test_policy_explains_after_a_wrong_streak_and_learns_when_prerequisites_ready():
    states = {
        "a": {
            "mastery": 0.85,
            "confidence": 0.9,
            "recall": 0.95,
            "days_since": 0.5,
            "attempts": 8,
            "last_correct": True,
            "wrong_streak": 0,
        },
        "b": {
            "mastery": 0.5,
            "confidence": 0.6,
            "recall": 0.9,
            "days_since": 0.2,
            "attempts": 4,
            "last_correct": False,
            "wrong_streak": 2,
        },
    }
    rec = recommend(states, prerequisites={"b": ["a"], "c": ["a"]}, in_scope=["a", "b", "c"])
    assert rec.action is Action.explain and rec.concept_id == "b"
    assert ("LEARN", "c", pytest.approx(0.5, abs=1e-6)) in rec.alternatives or any(
        a[0] == "LEARN" for a in rec.alternatives
    )


# ── registry ──────────────────────────────────────────────────────────────


def test_registry_records_runs_and_promotes_one_production_version(tmp_path: Path):
    reg = Registry(tmp_path)
    reg.record(
        ExperimentRun(
            run_id="r1",
            model="pfa",
            dataset="synthetic",
            dataset_version="sim:1",
            dataset_kind="synthetic",
            seed=0,
            config={},
            metrics={"auc": 0.6},
            train_seconds=0.1,
        )
    )
    assert reg.runs()[0]["git"] is None or isinstance(reg.runs()[0]["git"], str)
    reg.register("aquilante", "v1", payload={}, metrics={"auc": 0.7}, status="staging")
    reg.register("aquilante", "v2", payload={}, metrics={"auc": 0.72})
    reg.set_status("aquilante", "v1", "production")
    reg.set_status("aquilante", "v2", "production")
    statuses = {m["version"]: m["status"] for m in reg.versions("aquilante")}
    assert statuses == {"v1": "deprecated", "v2": "production"}
    assert reg.production("aquilante").name == "v2"
    meta = json.loads((reg.production("aquilante") / "model.json").read_text())
    assert meta["metrics"]["auc"] == 0.72


# ── public dataset adapters, on tiny files in the same shape ───────────────


def test_ednet_kt1_adapter_reads_per_user_files(tmp_path: Path):
    from aquilante.data.adapters import ednet_kt1_dataset

    (tmp_path / "questions.csv").write_text(
        "question_id,bundle_id,explanation_id,correct_answer,part,tags,deployed_at\n"
        "q1,b1,e1,b,1,1;2,0\nq2,b1,e1,d,1,3,0\n"
    )
    kt1 = tmp_path / "KT1"
    kt1.mkdir()
    (kt1 / "u1.csv").write_text(
        "timestamp,solving_id,question_id,user_answer,elapsed_time\n"
        "1565332027449,1,q1,b,24000\n1565332057449,2,q2,a,19000\n1565400000000,3,q1,c,30000\n"
    )
    ds = ednet_kt1_dataset(kt1, tmp_path / "questions.csv")
    assert ds.n_students == 1 and ds.n_events == 3
    s = ds.sequences[0]
    assert s.correct.tolist() == [1, 0, 0]
    assert s.log_gap_concept[2] > 0  # real time, in days, between the two q1 answers


def test_duolingo_hlr_adapter_emits_recall_events(tmp_path: Path):
    from aquilante.data.adapters import duolingo_hlr_dataset

    (tmp_path / "hlr.csv").write_text(
        "p_recall,timestamp,delta,user_id,learning_language,ui_language,lexeme_id,lexeme_string,history_seen,history_correct,session_seen,session_correct\n"
        "1.0,1362076081,27649635,u:FO,de,en,lx1,lernen/lernen<vblex>,6,4,2,2\n"
        "0.5,1362176081,100000,u:FO,de,en,lx1,lernen/lernen<vblex>,8,6,2,1\n"
    )
    ds = duolingo_hlr_dataset(tmp_path / "hlr.csv")
    assert ds.n_events == 2
    assert ds.sequences[0].correct.tolist() == [1, 0]
