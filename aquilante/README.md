# Aquilante

**Adaptive Neural Learner Modeling Engine.** An adaptive system for
modeling knowledge, retention and learning progression from learning
events, and for choosing the next learning action from what it estimates.

Aquilante answers one question, continuously, per learner:

> What does this learner know now, what are they starting to forget, and
> what should happen next?

It is not a chatbot, not a wrapper around a language model, and not a
vector database. It is a small machine-learning system with a dataset
schema, a feature pipeline, baselines, two neural sequence models, a
training loop, an evaluation with calibration, a registry, an online
learner state with uncertainty, a rule-based pedagogical policy with reason
codes, and an inference service. Language models sit *outside* it: a
product such as [NOEMA](https://github.com/aislamsilvalol-ctrl/noema) asks Aquilante what a learner needs
and asks a language model to say it well.

Status: **alpha, research-oriented**. Numbers in this README come from the
synthetic simulator and prove that the pipeline works, not that the model
works on people. See [Results](#results) and [Limitations](#limitations).

```
events ─► features ─► models ─► training ─► evaluation ─► registry
                                                 │
                        Learner.observe ─► state ─► policy ─► next action
```

## Quickstart

```bash
cd aquilante
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[torch,dev]"
.venv/bin/pytest                                   # 30 tests, ~2 min on a laptop CPU
.venv/bin/aquilante describe  --dataset configs/datasets/synthetic-small.yaml
.venv/bin/aquilante benchmark --dataset configs/datasets/synthetic-small.yaml --quick --out runs
.venv/bin/aquilante train     --dataset configs/datasets/synthetic-small.yaml --config configs/train/aquilante.yaml --out runs
.venv/bin/aquilante compare   --runs runs
.venv/bin/aquilante serve     --model runs/models/aquilante/<version>
```

As a library:

```python
from aquilante import Learner, LearningEvent

learner = Learner("student-7f3a")            # a pseudonymous id; identity stays outside
learner.observe(LearningEvent(event_id="e1", student_id="student-7f3a",
                              concept_id="calculus:chain-rule", timestamp=1_700_000_000,
                              correct=False, difficulty=0.6, response_ms=14_200))
state = learner.state()                       # mastery · confidence · recall, per concept
learner.predict_recall("calculus:chain-rule", days_ahead=7)
learner.recommend()                           # Action + reason codes, e.g. REVIEW because recall_predicted:0.61<0.75
```

Without a trained neural model the `Learner` answers with the recency
heuristic and says so in `state.model`; with one (a registered directory
from `aquilante train`) it answers with the model and MC-dropout uncertainty.

## What is in the box

| Layer | Module | What it does |
|---|---|---|
| Events | `aquilante.data.schema` | `LearningEvent` v1: pseudonymous student, concept, item, time, type, correctness, difficulty, latency, hints, attempt, stated confidence, session. Versioned; `upgrade()` for older versions. |
| Adapters | `aquilante.data.adapters` | Synthetic simulator, JSONL (a product's own export), ASSISTments 2009 skill builder with the standard cleaning (drop scaffolding, dedupe multi-skill rows). Every dataset carries a content-hash version and a `kind`: `synthetic`, `public`, `real`. |
| Features | `aquilante.features.sequences` | Per-learner sequences with log time gaps (overall and per concept), prior exposures and successes, response time, hints, difficulty. Splits by learner with a seeded hash. |
| Simulator | `aquilante.simulation` | Learners with individual learning and forgetting rates on a prerequisite chain; Rasch-like outcomes; response times and hints correlated with uncertainty. Known parameters, so the pipeline can be checked. |
| Baselines | `aquilante.models.baselines` | Global mean, concept mean, recency-weighted mastery heuristic (what products ship), PFA, BKT by EM (optional forgetting). NumPy only. |
| Forgetting | `aquilante.memory.forgetting` | Half-life regression: P(recall) = 2^(−Δt/h), h learned from counts and difficulty. |
| Neural | `aquilante.models.neural` | DKT (GRU) and **Aquilante**: causal attention over interaction embeddings with time gaps, response time, hints, items, and a per-concept forgetting gate; ablation switches; MC dropout; temperature scaling. |
| Training | `aquilante.training` | YAML config, seed, length-bucketed batches, AdamW, gradient clipping, early stopping on validation log loss, best checkpoint, optional AMP on CUDA. |
| Evaluation | `aquilante.evaluation` | AUC, log loss, Brier, ECE with a reliability table, accuracy, base rate. Own implementations, no optional dependency. |
| Registry | `aquilante.experiments` | `runs.jsonl` (model, dataset + version, seed, config, metrics, time, hardware, git commit) and a model registry with `experimental → staging → production → deprecated`; one production version per model; rollback is a status change. |
| Policy | `aquilante.policy` | DIAGNOSTIC · REVIEW · LEARN · EXPLAIN · PRACTICE · CHALLENGE from the state, with scores, alternatives and reason codes such as `recall_predicted:0.61<0.75`, `wrong_streak:2`, `prerequisite_weak:algebra`. |
| Inference | `aquilante.inference` | `Learner` (observe · state · predict_recall · recommend) and a FastAPI service (`/events`, `/learner/{id}/state`, `/recall`, `/recommend`, `/health`) that never fails over to nothing: the heuristic serves when the model cannot. |
| Benchmark | `aquilante.benchmarks` | Same split, same metrics, one table, every run recorded. |

## Results

The current table, with its provenance and the command that reproduces
it, is [`benchmarks/README.md`](benchmarks/README.md). On the synthetic
benchmark set (400 learners, seed 0, one seed per model, 12 epochs for the
neural models on a laptop CPU) the ranking by AUC is:

| model | AUC | log loss | ECE |
|---|---|---|---|
| mastery heuristic (recency rule) | 0.678 | 0.643 | 0.042 |
| PFA | 0.673 | 0.641 | 0.021 |
| DKT | 0.670 | 0.645 | 0.024 |
| BKT | 0.669 | 0.644 | 0.022 |
| Aquilante (full) | 0.656 | 0.652 | 0.035 |
| concept mean | 0.596 | 0.680 | 0.013 |
| global mean | 0.500 | 0.694 | 0.016 |

**The simple models win on this data.** That is the expected result on a
simulator whose generating process is close to a logistic model with
counts, and it is exactly the kind of result the benchmark exists to
surface: the neural candidate has not earned a place yet. The ablation
rows (time, forgetting gate, response time, item embeddings) differ by
less than the seed-to-seed noise one should expect from a single run;
they will be re-run with three seeds on a public dataset with real
timestamps (ROADMAP V1) before any of them is called an ingredient.

## Design decisions, briefly

- **Split by learner.** A model that has seen a learner's early events and
  is tested on their later ones is solving an easier problem than the one
  the product faces.
- **State is derived, not stored.** The learner state is recomputed from
  events; a better model re-reads the same events.
- **Three numbers, not one.** Mastery (would they get it right now),
  confidence (how much to trust that), recall (how much survives a gap).
  The policy uses recall for reviews and mastery for what to learn.
- **Uncertainty is cheap and present.** MC dropout for the spread,
  temperature scaling for the mean. Ensembles are a training-time option.
- **No engagement reward.** The policy scores actions by predicted
  learning need; nothing in it rewards time in app or streaks.
- **No language model.** Aquilante does not read or write text.
- **Complexity earns its place in the ablation table.** Each ingredient of
  the neural model can be switched off; the benchmark runs the variants.

The literature behind these choices, with sources and what could not be
verified, is in [`RESEARCH.md`](RESEARCH.md).

## Limitations

- Results so far are on **synthetic** data. They validate the pipeline,
  the causality of predictions, the calibration path and the fallbacks.
  They say nothing about real learners.
- The ASSISTments 2009 adapter exists; the dataset must be downloaded by
  you under its terms, and it has no timestamps, so time features are
  flat on it.
- The forgetting model is a recall model over counts and gaps; it does
  not yet learn per-learner rates.
- The policy is rules. A contextual bandit with learning progress as
  reward is on the roadmap, after there is outcome data to learn from.
- Cold-start diagnosis is a policy action, not yet an adaptive item
  selector.
- No graph neural network. The prerequisite graph enters the simulator
  and the policy; a GNN is an experiment with a falsification test, not a
  default.

## Ethics and privacy

Aquilante consumes pseudonymous identifiers only and stores no free text.
It estimates *educational* quantities — mastery, recall, confidence — and
must not be used to infer or label anything else about a person. Deletion
is deletion of a learner's events; the state is derived, so nothing else
holds it. Open-source code is not open data: no learner data ships with
this repository and none should be added to it. See
[`MODEL_CARD.md`](MODEL_CARD.md).

## Roadmap

[`ROADMAP.md`](ROADMAP.md). Short form: V0 data + baselines (this),
V1 temporal knowledge tracing on a public dataset with real time, V1.5
per-learner forgetting + calibrated uncertainty, V2 prerequisite graph in
the model, V2.5 adaptive diagnostic, V3 policy learning from outcomes.

## Where it lives

The canonical repository is
<https://github.com/aislamsilvalol-ctrl/aquilante>. A copy is carried
inside the NOEMA monorepo under `aquilante/` for the integration work and
is synchronised from there with `git subtree push --prefix=aquilante`.

## Licence

Apache-2.0. See [`LICENSE`](LICENSE).
