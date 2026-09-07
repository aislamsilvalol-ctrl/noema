# Roadmap

Each version has an exit criterion. A version that does not meet it does
not get its number.

## V0 — data and baselines (this repository, 2026-09)

- Learning event schema v1, adapters (synthetic, JSONL, ASSISTments 2009).
- Features, learner split, metrics with calibration, registry.
- Baselines: global/concept mean, recency heuristic, PFA, BKT.
- Half-life forgetting model.
- DKT and the Aquilante candidate with ablation switches; training loop.
- Learner state (mastery, confidence, recall), rule policy with reasons,
  service with fallback. Tests.
- **Exit**: the benchmark runs end to end on synthetic data with every model
  in one table; predictions are causal; the service survives a missing model.
  *Met.*

## V1 — temporal knowledge tracing on real time

- EdNet (KT1) and Duolingo HLR adapters; a DAS3H-style time-window
  logistic baseline.
- Benchmark on at least one public dataset with timestamps, three seeds,
  with the literature's cleaned numbers beside the table.
- **Exit**: Aquilante ≥ the best logistic baseline in AUC *and* log loss on
  held-out learners of a public dataset, or the README says it is not.

## V1.5 — forgetting and uncertainty

- Per-learner forgetting rate (a learned scalar per learner, regularised).
- Deep ensembles as a serving option; calibration per concept group.
- **Exit**: ECE ≤ 0.03 on the public test set; recall predictions checked
  against observed gaps.

## V2 — the prerequisite graph in the model

- Prerequisite-aware features (state of prerequisites at query time) in
  both the logistic baseline and Aquilante; a GNN variant.
- **Exit**: the GNN variant beats the feature variant on held-out learners,
  or it is dropped and the report says why.

## V2.5 — adaptive diagnostic

- Item selection by expected information under the current state, moving
  down the prerequisite chain on failure.
- **Exit**: a simulated cold-start learner is placed within the simulator's
  known mastery in fewer questions than a fixed diagnostic.

## V3 — policy learning

- Contextual bandit over actions with *learning progress* as reward,
  trained offline from logged outcomes; the rule policy stays as the
  control arm.
- **Exit**: measured learning gain on real learners, with the rule policy
  as baseline; no engagement metric in the objective.

## Integration with NOEMA (tracked in `docs/NOEMA_INTEGRATION.md`)

- Stable concept ids and latency/difficulty/confidence on the product's
  mastery events; a pseudonymous export; the Professor Engine consuming
  `state` and `recommend`, with the rule policy as fallback.
