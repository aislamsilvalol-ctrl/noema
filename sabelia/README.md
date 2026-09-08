# Sabelia

**Adaptive Neural Learner Modeling Engine.** An adaptive system for
modeling knowledge, retention and learning progression from learning
events, and for choosing the next learning action from what it estimates.

Sabelia answers one question, continuously, per learner:

> What does this learner know now, what are they starting to forget, and
> what should happen next?

It is not a chatbot, not a wrapper around a language model, and not a
vector database. It is a small machine-learning system with a dataset
schema, a feature pipeline, baselines, two neural sequence models, a
training loop, an evaluation with calibration, a registry, an online
learner state with uncertainty, a rule-based pedagogical policy with reason
codes, and an inference service. Language models sit *outside* it: a
product such as [NOEMA](https://github.com/aislamsilvalol-ctrl/noema) asks Sabelia what a learner needs
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
cd sabelia
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[torch,dev]"
# torch < 2.3 (the last release for x86 macOS) needs numpy 1.x: uv pip install --python .venv/bin/python "numpy<2"
.venv/bin/pytest                                   # 30 tests, ~2 min on a laptop CPU
.venv/bin/sabelia describe  --dataset configs/datasets/synthetic-small.yaml
.venv/bin/sabelia benchmark --dataset configs/datasets/synthetic-small.yaml --quick --out runs
.venv/bin/sabelia train     --dataset configs/datasets/synthetic-small.yaml --config configs/train/sabelia.yaml --out runs
.venv/bin/sabelia compare   --runs runs
.venv/bin/sabelia serve     --model runs/models/sabelia/<version>
```

As a library:

```python
from sabelia import Learner, LearningEvent

learner = Learner("student-7f3a")  # a pseudonymous id; identity stays outside
learner.observe(
    LearningEvent(
        event_id="e1",
        student_id="student-7f3a",
        concept_id="calculus:chain-rule",
        timestamp=1_700_000_000,
        correct=False,
        difficulty=0.6,
        response_ms=14_200,
    )
)
state = learner.state()  # mastery · confidence · recall, per concept
learner.predict_recall("calculus:chain-rule", days_ahead=7)
learner.recommend()  # Action + reason codes, e.g. REVIEW because recall_predicted:0.61<0.75
```

Without a trained neural model the `Learner` answers with the recency
heuristic and says so in `state.model`; with one (a registered directory
from `sabelia train`) it answers with the model and MC-dropout uncertainty.

## What is in the box

| Layer | Module | What it does |
|---|---|---|
| Events | `sabelia.data.schema` | `LearningEvent` v1: pseudonymous student, concept, item, time, type, correctness, difficulty, latency, hints, attempt, stated confidence, session. Versioned; `upgrade()` for older versions. |
| Adapters | `sabelia.data.adapters` | Synthetic simulator, JSONL (a product's own export), ASSISTments 2009 skill builder with the standard cleaning (drop scaffolding, dedupe multi-skill rows). Every dataset carries a content-hash version and a `kind`: `synthetic`, `public`, `real`. |
| Features | `sabelia.features.sequences` | Per-learner sequences with log time gaps (overall and per concept), prior exposures and successes, response time, hints, difficulty. Splits by learner with a seeded hash. |
| Simulator | `sabelia.simulation` | Learners with individual learning and forgetting rates on a prerequisite chain; Rasch-like outcomes; response times and hints correlated with uncertainty. Known parameters, so the pipeline can be checked. |
| Baselines | `sabelia.models.baselines` | Global mean, concept mean, recency-weighted mastery heuristic (what products ship), PFA, DAS3H-style time-window logistic model, BKT by EM (optional forgetting). NumPy only. |
| Forgetting | `sabelia.memory.forgetting` | Half-life regression: P(recall) = 2^(−Δt/h), h learned from counts and difficulty. |
| Neural | `sabelia.models.neural` | DKT (GRU) and **Sabelia**: causal attention over interaction embeddings with time gaps, response time, hints, items, and a per-concept forgetting gate; ablation switches; MC dropout; temperature scaling. |
| Training | `sabelia.training` | YAML config, seed, length-bucketed batches, AdamW, gradient clipping, early stopping on validation log loss, best checkpoint, optional AMP on CUDA. |
| Evaluation | `sabelia.evaluation` | AUC, log loss, Brier, ECE with a reliability table, accuracy, base rate. Own implementations, no optional dependency. |
| Registry | `sabelia.experiments` | `runs.jsonl` (model, dataset + version, seed, config, metrics, time, hardware, git commit) and a model registry with `experimental → staging → production → deprecated`; one production version per model; rollback is a status change. |
| Policy | `sabelia.policy` | DIAGNOSTIC · REVIEW · LEARN · EXPLAIN · PRACTICE · CHALLENGE from the state, with scores, alternatives and reason codes such as `recall_predicted:0.61<0.75`, `wrong_streak:2`, `prerequisite_weak:algebra`. |
| Inference | `sabelia.inference` | `Learner` (observe · state · predict_recall · recommend) and a FastAPI service (`/events`, `/learner/{id}/state`, `/recall`, `/recommend`, `/health`) that never fails over to nothing: the heuristic serves when the model cannot. |
| Benchmark | `sabelia.benchmarks` | Same split, same metrics, one table, every run recorded. |

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
| Sabelia (full) | 0.656 | 0.652 | 0.035 |
| concept mean | 0.596 | 0.680 | 0.013 |
| global mean | 0.500 | 0.694 | 0.016 |

**The simple models win on this data.** That is the expected result on a
simulator whose generating process is close to a logistic model with
counts, and it is exactly the kind of result the benchmark exists to
surface: the neural candidate has not earned a place yet.

With three seeds (same set, `benchmarks/runs-3seeds`), the ranking holds
and the spread says how much to trust it:

| model | AUC (mean ± sd, 3 seeds) |
|---|---|
| mastery heuristic | 0.686 ± 0.024 |
| PFA | 0.681 ± 0.025 |
| BKT | 0.678 ± 0.025 |
| DKT | 0.674 ± 0.020 |
| Sabelia without the forgetting gate | 0.668 ± 0.026 |
| Sabelia without time | 0.666 ± 0.030 |
| Sabelia (full) | 0.663 ± 0.032 |

The seed-to-seed spread is larger than every gap between models, so
**no ablation conclusion can be drawn from the synthetic data**.

On real data the picture changes. On the first 300k rows of the Duolingo
learning traces (6,869 learners, real timestamps, three seeds, split by
learner; `benchmarks/runs-duolingo`):

| model | AUC (mean ± sd, 3 seeds) | log loss | ECE |
|---|---|---|---|
| Sabelia (full) | 0.662 ± 0.004 | 0.413 | 0.013 |
| Sabelia without time / forgetting / response / item | 0.661–0.664 | 0.412–0.414 | 0.009–0.011 |
| DKT | 0.635 ± 0.002 | 0.436 | 0.048 |
| mastery heuristic | 0.604 ± 0.002 | 0.434 | 0.031 |
| DAS3H | 0.603 ± 0.003 | 0.430 | 0.010 |
| BKT | 0.600 ± 0.003 | 0.457 | 0.038 |
| PFA | 0.596 ± 0.005 | 0.433 | 0.018 |

**Sabelia wins on this dataset**, in AUC and in log loss, by a margin far
outside the seed spread. **Its ablations do not**: the five variants are
indistinguishable, so on this slice the time features and the forgetting gate
add nothing measurable.

**On EdNet-KT1 it wins the ranking and loses the calibration.** 6,000 learners
sampled by hash from EdNet's 784,309, three seeds:

| model | AUC | log loss | ECE |
|---|---|---|---|
| Sabelia (full) | 0.6600 ± 0.0023 | 0.6321 | 0.0115 |
| DKT | 0.6548 ± 0.0041 | 0.6344 | 0.0169 |
| BKT | 0.6354 ± 0.0079 | **0.6225** | **0.0071** |
| DAS3H | 0.6301 ± 0.0051 | 0.6261 | 0.0098 |
| mastery heuristic | 0.6150 ± 0.0075 | 0.6418 | 0.0555 |

ROADMAP V1's exit condition is AUC **and** log loss against the best logistic
baseline. Sabelia clears the first by 0.025 and fails the second by 0.010, so
**V1 is not met**. One dataset where it wins both is not the bar, and the bar
was written before the numbers were in.

A second Duolingo run answers the "short windows" caveat: keeping every row of
a 4% sample of learners (median sequence 36 rather than 25) raises every
model *except* Sabelia — the heuristic to 0.621, DAS3H to 0.626, DKT to 0.644,
Sabelia 0.661 — so the lead narrows from 0.058 to 0.037 over the best logistic
baseline. There, and only there, removing the time features costs something
(0.657). One seed; the ordering inside the Sabelia block is undetermined.

## Demo

`examples/demo/index.html` is a static page built by
`scripts/build_demo.py` from the library itself: a simulated learner's
knowledge map (mastery as radius, uncertainty as ring, prerequisites as
lines), the recommended action with its reason codes, the recall curve of
the weakest concept with the review threshold, the per-concept state, and
the lab view — the recorded benchmark and the reliability diagram of the
fallback model. Rebuild it after a benchmark:

```bash
.venv/bin/python scripts/build_demo.py --runs benchmarks/runs-3seeds --out examples/demo/index.html
```

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
- **No language model.** Sabelia does not read or write text.
- **Complexity earns its place in the ablation table.** Each ingredient of
  the neural model can be switched off; the benchmark runs the variants.

The literature behind these choices, with sources and what could not be
verified, is in [`RESEARCH.md`](RESEARCH.md).

## Limitations

- Real-data evidence is two public datasets in two domains: vocabulary recall
  (Duolingo) and problem solving (EdNet). It wins the ranking on both and the
  calibration on only one. It says nothing about NOEMA's own learners; the
  synthetic results validate the pipeline only.
- **None of the four designed-in mechanisms — time, forgetting, response time,
  item identity — can be shown to contribute on any dataset run so far.** The
  attention over the concept sequence is what carries the result.
- Removing the item embedding cuts the model from 862k parameters to 90k with
  no loss of AUC on EdNet. That is the next thing to test properly, and it
  points at a smaller model rather than a bigger one.
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

Sabelia consumes pseudonymous identifiers only and stores no free text.
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
<https://github.com/aislamsilvalol-ctrl/sabelia>. A copy is carried
inside the NOEMA monorepo under `sabelia/` for the integration work and
is synchronised from there with `git subtree push --prefix=sabelia`.

## Licence

Apache-2.0. See [`LICENSE`](LICENSE).
