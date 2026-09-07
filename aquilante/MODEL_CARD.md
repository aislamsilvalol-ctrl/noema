# Model card — Aquilante (sequence models for learner modeling)

Following Mitchell et al., *Model Cards for Model Reporting* (FAT* 2019).

## Model details

- **Models**: `dkt` (GRU over concept×outcome interactions; Piech et al. 2015)
  and `aquilante` (causal self-attention over interaction embeddings with
  time gaps, response time, hints, item embeddings and a per-concept
  forgetting gate). Both output P(correct at t | events before t).
- **Auxiliary models**: half-life regression for recall; BKT, PFA and
  count heuristics as baselines.
- **Version**: 0.1.0. Registered versions carry their own `model.json` with
  config, dataset version, metrics, git commit and hardware.
- **Licence**: Apache-2.0. **Contact**: the NOEMA repository.

## Intended use

Estimating, per learner and per concept, the probability of answering
correctly now, the probability of recall after a gap, and the confidence
of those estimates; and ranking pedagogical actions (diagnose, review,
learn, explain, practise, challenge) with reason codes. The consumer is a
tutoring product that turns the recommendation into an experience.

**Out of scope**: grading people; ranking or admitting learners; inferring
ability as a trait; any inference about attributes unrelated to the
concepts being learned; any use where the reason codes are hidden from the
learner.

## Training data

- V0 is trained and evaluated on **synthetic** data from
  `aquilante.simulation` (documented generating process, seeded) and can be
  trained on ASSISTments 2009 through its adapter. No real learner data is
  included in the repository.
- Events carry pseudonymous learner ids and no text. Products are
  responsible for pseudonymisation before export.

## Evaluation

Split by learner (seeded hash). Metrics: AUC, log loss, Brier, ECE
(10 bins), accuracy, base rate; reliability tables per registered model.
Current numbers and their provenance: `benchmarks/README.md`.

## Known limitations

- Synthetic results transfer nothing to real learners; they establish that
  the pipeline is correct and the models learn *something*.
- Public datasets without timestamps (ASSISTments 2009) flatten the time
  features; results there should be compared with the literature's cleaned
  numbers (RESEARCH.md §1), not with the synthetic table.
- Uncertainty from MC dropout is a spread, not a posterior; it is useful
  as a relative signal (ask before trusting) and is reported as such.
- The models see concept ids from the product; if the product's concept
  identities are unstable across sessions, the sequences fragment and the
  estimates degrade (see `docs/NOEMA_INTEGRATION.md` for the fix on the
  product side).

## Ethical considerations

- The system optimises predicted learning need, never engagement.
- Estimates are shown with confidence and with reason codes; a low
  confidence must lead to a question, not to a decision.
- A learner's state is derived from their events; deleting the events
  deletes the state.
- Fairness across learner populations has **not** been evaluated; it must
  be before any real deployment (per-group calibration is the first
  check).
