# Sabelia — Research notes

What the field knows about modelling a learner from interaction data, what
it does not, and what that implies for Sabelia's first version. Written
before the architecture was fixed; the choices at the end are the ones the
code implements. Claims carry a source. Citations were checked against the papers and
dataset pages on 2026-09-07; the few that were not are marked
**[unverified]** and must be verified before being quoted anywhere else.

The question the system must answer:

> What does this learner know now, what are they starting to forget, and
> what should happen next?

Three sub-problems, with different literatures: **knowledge tracing**
(estimating a latent knowledge state from a sequence of graded events),
**memory / forgetting** (how the probability of recall decays with time),
and **pedagogical policy** (choosing the next action). A fourth,
**uncertainty**, cuts across all three.

## 1. Knowledge tracing

| Family | Representative work | Idea | Strengths | Limitations | Data needed | Cost | Interpretable |
|---|---|---|---|---|---|---|---|
| Bayesian Knowledge Tracing | Corbett & Anderson, *Knowledge tracing: modeling the acquisition of procedural knowledge*, UMUAI 1995. https://doi.org/10.1007/BF01099821 | One two-state HMM per skill: unknown → known with P(learn); observations through guess/slip | Tiny, interpretable, works with hundreds of learners; the mastery number *is* the belief | One skill per item; no forgetting in the base model; identifiability problems (guess/slip can trade off with the prior); ignores time and item difficulty | Small | Trivial | Yes |
| Item Response Theory / Rasch | Rasch 1960; for KT use, see the PFA paper below | P(correct) = σ(ability − difficulty); static ability | The standard for item calibration and adaptive testing; well understood | Static: no learning within the sequence | Small–medium | Trivial | Yes |
| Performance Factors Analysis | Pavlik, Cen & Koedinger, *Performance Factors Analysis — a new alternative to knowledge tracing*, AIED 2009. https://doi.org/10.3233/978-1-60750-028-5-531 | Logistic regression on skill difficulty, prior successes and prior failures | Handles multi-skill items; competitive with BKT; interpretable coefficients | Counts, not sequence; no forgetting unless features are added | Small | Trivial | Yes |
| Deep Knowledge Tracing | Piech et al., *Deep Knowledge Tracing*, NeurIPS 2015. https://arxiv.org/abs/1506.05908 | An LSTM/GRU over one-hot (skill, correct) interactions predicts the next answer on every skill | Learns inter-skill structure; the paper reports AUC 0.86 on ASSISTments 2009 (later found inflated by dataset duplicates, see Xiong et al.) | Predictions are not a stable "mastery" (they wave, and can drop after a correct answer — Yeung & Yeung 2018 add regularisers); no time; needs thousands of learners to beat logistic baselines | Medium–large | Small model, cheap | Weak |
| DKVMN | Zhang et al., *Dynamic Key-Value Memory Networks for Knowledge Tracing*, WWW 2017. https://arxiv.org/abs/1611.08108 | External memory with one slot per latent concept | A per-concept state you can read out | More moving parts for similar AUC | Medium | Cheap | Some |
| SAKT | Pandey & Karypis, *A Self-Attentive model for Knowledge Tracing*, EDM 2019. https://arxiv.org/abs/1907.06837 | Causal self-attention: the query is the next exercise, keys/values are past interactions | Handles long sequences, sparse data better than RNNs in their experiments | No time gaps in the base model; attention weights are only loosely interpretable | Medium | Cheap | Some |
| AKT | Ghosh, Heffernan & Lan, *Context-Aware Attentive Knowledge Tracing*, KDD 2020. https://arxiv.org/abs/2007.12324 | Monotonic attention with a learned exponential decay over *position* distance, plus Rasch-style item embeddings | Explicit forgetting-like decay; item difficulty inside the model; strong reported results | Decay over index distance, not wall-clock time | Medium | Cheap | Some |
| SAINT / SAINT+ | Choi et al., *Towards an Appropriate Query, Key, and Value Computation for Knowledge Tracing*, L@S 2020, https://arxiv.org/abs/2002.07033; Shin et al., *SAINT+: Integrating Temporal Features for EdNet Correctness Prediction*, LAK 2021, https://arxiv.org/abs/2010.12042 | Encoder–decoder transformer; SAINT+ adds elapsed time and lag time as inputs | The temporal features gave a measurable gain on EdNet | Needs EdNet-scale data (hundreds of thousands of learners) | Large | Moderate | Weak |
| DAS3H | Choffin, Popineau, Bourda & Vie, *DAS3H: Modeling Student Learning and Forgetting for Optimally Scheduling Distributed Practice of Skills*, EDM 2019. https://arxiv.org/abs/1905.06873 | Logistic model with time-window counts of past attempts and successes per skill (windows: 1 h, 1 d, 7 d, 30 d, ∞) | Forgetting through time windows, in a model that is still a logistic regression; strong on datasets with real timestamps | Windows are fixed; per-learner decay is not learned | Small–medium | Trivial | Yes |
| DKT-Forget | Nagatani et al., *Augmenting Knowledge Tracing by Considering Forgetting Behavior*, WWW 2019. https://doi.org/10.1145/3308558.3313565 | DKT plus repeated-time-gap, sequence-time-gap and past-trial-count features | Shows that adding gap features to DKT helps on datasets with timestamps | Same DKT weaknesses | Medium | Cheap | Weak |
| "Is deep KT better?" | Gervet, Koedinger, Schneider & Mitchell, *When is Deep Learning the Best Approach to Knowledge Tracing?*, JEDM 2020. https://jedm.educationaldatamining.org/index.php/JEDM/article/view/451 | Systematic comparison of logistic (IRT, PFA, DAS3H) and deep (DKT, SAKT) models on nine datasets | **Key finding**: logistic models with the right features match or beat deep models on small and medium datasets; deep models win on large ones with many items and long sequences; time-window features matter when timestamps exist | — | — | — | — |
| simpleKT | Liu et al., *simpleKT: A Simple But Tough-to-Beat Baseline for Knowledge Tracing*, ICLR 2023. https://arxiv.org/abs/2302.06881 | A Rasch-style embedding plus one attention block | Matches far more complex models across the pyKT benchmark | — | Medium | Cheap | Some |
| Benchmarking rigour | Liu et al., *pyKT: A Python Library to Benchmark Deep Learning based Knowledge Tracing Models*, NeurIPS 2022 datasets track. https://arxiv.org/abs/2206.11460 | Standardised preprocessing and evaluation for KT | Documents how much reported gains came from inconsistent evaluation (e.g. predicting one question from an expanded multi-skill row) | — | — | — | — |
| Data hygiene | Xiong, Zhao, Van Inwegen & Beck, *Going Deeper with Deep Knowledge Tracing*, EDM 2016. https://eric.ed.gov/?id=ED592679 | Shows ASSISTments 2009 duplicates and scaffolding rows inflated DKT's original AUC; after cleaning, DKT and PFA are close | — | — | — | — |

**AUC ranges to sanity-check results** (verified against the papers'
tables). On ASSISTments 2009 under pyKT's question-level evaluation
(pyKT, Table 2), models span roughly 0.70–0.79 AUC: SAINT 0.696 and SAKT
0.725 at the low end, DKT 0.754 in the middle, AKT 0.785 at the top;
simpleKT reports 0.774 ± 0.002 against AKT 0.785 ± 0.002 and DKT 0.754 ±
0.001 (simpleKT, Table 2). Anything far above 0.85 on this dataset is a
leakage red flag.

**What this implies.** Sabelia V0 must ship logistic baselines with
temporal features (PFA, and a DAS3H-style time-window variant is the natural
next addition) and must beat them on held-out learners before any neural
claim is made. The neural candidate should be small, attention-based, and
carry wall-clock time and an explicit forgetting term — the two things the
literature shows matter and that most public implementations leave out.

## 2. Memory and forgetting

| Work | Idea | Use here |
|---|---|---|
| Ebbinghaus (1885), *Über das Gedächtnis*; replication: Murre & Dros, PLOS ONE 2015. https://doi.org/10.1371/journal.pone.0120644 | Retention falls steeply then slowly; a power or exponential-in-log-time curve | Shape of the decay; the simulator uses log-time decay |
| Anderson & Schooler, *Reflections of the environment in memory*, Psychological Science 1991 (ACT-R base-level activation) | Activation = log of the sum of practice recencies to a power; recall is a logistic function of activation | Motivates counting *when* practices happened, not only how many |
| Settles & Meeder, *A Trainable Spaced Repetition Model for Language Learning*, ACL 2016. https://aclanthology.org/P16-1174/ | Half-life regression: p = 2^(−Δt/h), h = 2^(θ·x), θ learned from recall logs | **Adopted**: `sabelia.memory.HalfLifeModel` is this model with per-concept counts and difficulty as features |
| FSRS (open-source scheduler, Jarrett Ye et al.), https://github.com/open-spaced-repetition/fsrs4anki | Difficulty–Stability–Retrievability state with a power forgetting curve and parameters fitted per user | Noema already runs FSRS-4.5 for flashcards; Sabelia's recall estimate must agree with it in spirit (same state, same curve) and can consume its reviews as events |
| DAS3H (above) | Time-window counts in a logistic model | Baseline to add; cheap and strong where timestamps exist |

**Distinction kept in the code.** *Mastery* (would they answer correctly
if asked now, given everything) and *recall* (how much of a once-known
concept survives a gap) are different numbers. The learner state carries
both; the policy uses recall for review decisions and mastery for
what-to-learn decisions.

## 3. Cognitive diagnosis and graphs

- DINA and the Q-matrix tradition (de la Torre, *DINA model and parameter estimation*, J. Educ. Behav. Stat. 2009. https://doi.org/10.3102/1076998607309474) model each item as requiring a set of attributes. Useful where an expert Q-matrix exists; Noema's concepts come from an LLM-planned curriculum, so the matrix is soft. Not adopted in V0.
- NeuralCD (Wang et al., *Neural Cognitive Diagnosis for Intelligent Education Systems*, AAAI 2020. https://arxiv.org/abs/1908.08066) learns a monotone diagnosis from a Q-matrix. Same dependency.
- GKT (Nakagawa, Iwasawa & Matsuo, *Graph-based Knowledge Tracing: Modeling Student Proficiency Using Graph Neural Network*, WI 2019. https://doi.org/10.1145/3350546.3352513) propagates the update of one concept to its neighbours. The paper reports at best a 6.25 % relative AUC improvement over DKT/DKVMN on ASSISTments and KDD Cup; pyKT's re-evaluation places GKT below DKT on ASSISTments 2009 (0.742 vs 0.754). Modest, and dependent on graph quality.

**Decision.** The prerequisite graph enters Sabelia V0 in two places
that need no GNN: the simulator (transfer and penalty along prerequisite
edges, so the pipeline is tested on graph-shaped data) and the policy
(LEARN only when prerequisites are ready; EXPLAIN cites a weak prerequisite).
A GNN is a V2 experiment with a clear falsification criterion: it must beat
Sabelia-with-prerequisite-features on held-out learners.

## 4. Uncertainty and calibration

- MC dropout: Gal & Ghahramani, *Dropout as a Bayesian Approximation*, ICML 2016. https://arxiv.org/abs/1506.02142 — dropout at inference, variance across samples. Cheap; adopted for the confidence estimate.
- Deep ensembles: Lakshminarayanan, Pritzel & Blundell, NeurIPS 2017. https://arxiv.org/abs/1612.01474 — better than MC dropout in most comparisons, at N× the cost. The benchmark can train several seeds; serving them is a deployment choice.
- Temperature scaling: Guo, Pleiss, Sun & Weinberger, *On Calibration of Modern Neural Networks*, ICML 2017. https://arxiv.org/abs/1706.04599 — one scalar fitted on validation fixes most miscalibration. Adopted; applied after early stopping.
- ECE: Naeini, Cooper & Hauskrecht, *Obtaining Well Calibrated Probabilities Using Bayesian Binning*, AAAI 2015 — the binned calibration error reported in every benchmark row.

Why it matters here: the policy compares a predicted recall to a
threshold. A model that is 10 points miscalibrated moves every review by
days. Calibration is a first-class metric, not a footnote.

## 5. Adaptive diagnosis (cold start)

Computerised adaptive testing selects the item that maximises Fisher
information at the current ability estimate (van der Linden & Glas, eds.,
*Elements of Adaptive Testing*, Springer 2010). With a Rasch model the
information is p(1−p): ask items the learner has ~50 % chance on. For a
prerequisite chain, a wrong answer moves the probe to the prerequisite;
a right one moves it up. V2.5 in the roadmap; the policy already emits
`DIAGNOSTIC` when confidence is low, which is the hook.

## 6. Policy

- Rule/score policies remain the reference in tutoring systems; they are
  what a learned policy must beat on learning gain, not on clicks.
- Clement, Roy, Oudeyer & Lopes, *Multi-Armed Bandits for Intelligent Tutoring Systems*, JEDM 7(2):20–48, 2015. https://jedm.educationaldatamining.org/index.php/JEDM/article/view/JEDM111 (arXiv https://arxiv.org/abs/1310.3174) — bandits over activities with *learning progress* as the reward. The right reward for Sabelia.
- Reinforcement learning for tutoring has a long record of simulator-only wins that did not transfer (a review: Doroudi, Aleven & Brunskill, *Where's the Reward? A Review of Reinforcement Learning for Instructional Sequencing*, IJAIED 2019. https://doi.org/10.1007/s40593-019-00187-x). Adopt bandits only with real outcome data; RL not before that.

## 7. Datasets

| Dataset | Size | Fields | Licence / access | Caveats |
|---|---|---|---|---|
| ASSISTments 2009–2010 skill builder | ~4 k students, ~330 k rows (≈280 k after cleaning) **[counts unverified]** | user, problem, skill, correct, attempt count, hint count, first-response ms, order | Free download from the ASSISTments data page after accepting their terms; research use | Duplicate rows and scaffolding (Xiong et al. 2016); **no timestamps**, only an order |
| ASSISTments 2012–2013, 2017 | larger; 2017 has timestamps | similar plus time | Same page; the 2017 set has richer affect labels | Multi-skill tagging differs by year |
| EdNet (Riiid) | KT1: 784,309 students, 95.3 M interactions (131.4 M across KT1–KT4) | per-user CSV: timestamp (ms), solving_id, question_id, user_answer, elapsed_time; correctness from `questions.csv` | CC BY-NC 4.0, "for research purposes" — https://github.com/riiid/ednet (paper https://arxiv.org/abs/1912.03072) | Non-commercial: fine for research and benchmarks, not for a commercial model without agreement. Adapter: `ednet-kt1`. |
| Riiid AIEd Challenge 2020 (Kaggle) | EdNet-derived, ~100 M rows | as above plus lecture events | Kaggle competition terms | Same restriction; competition rules limit reuse |
| Junyi Academy | 247,606 students, ~25.9 M interactions, 722 exercises, 41 KCs (log to Jan 2015) | problem logs with skills and time | PSLC DataShop dataset 1198, DataShop terms of use (login required): https://pslcdatashop.web.cmu.edu/DatasetInfo?datasetId=1198; a newer 2018–19 release (~72 k students, 16 M attempts) by request to Junyi | Chinese-language skill names |
| Duolingo HLR data | 13 M learning traces (user × lexeme × session) | p_recall, timestamp, delta since last practice, user, languages, lexeme, history and session counts | CC BY-NC 4.0 — Harvard Dataverse doi:10.7910/DVN/N8XJME, file `settles.acl16.learning_traces.13m.csv.gz` (379 MB); code https://github.com/duolingo/halflife-regression (MIT) | Recall, not KT: the dataset for the forgetting model. Adapter: `duolingo-hlr`. |
| Statics 2011 / Algebra 2005 (KDD Cup) | tens of thousands of students | DataShop format with timestamps | PSLC DataShop terms of use | Older, ITS-specific |

**Choice for V0.** The synthetic generator for pipeline correctness, and
adapters for ASSISTments 2009 (the field's common reference, with its
caveats, written to the standard cleaning rules), EdNet-KT1 and the
Duolingo recall traces — the last two because they carry real time, which
is what the forgetting model and the time features need. No dataset is
fetched by the code; the user downloads under the dataset's licence, and
both EdNet and Duolingo are non-commercial licences.

## 8. What Sabelia V0 does, given the above

1. **Learner state = three numbers per concept** — mastery (sequence
   model), confidence (MC-dropout spread × evidence), recall (half-life
   model) — derived from events on every call, never stored as truth.
2. **Baselines first**: global mean, concept mean, the recency-weighted
   heuristic the product uses today, PFA, BKT (EM), half-life regression.
3. **Neural candidate**: a small causal-attention model with wall-clock
   gaps, response time, hints, item embeddings and a per-concept forgetting
   gate on the attended memory, each switchable for ablation; DKT as the
   deep reference.
4. **Evaluation**: split by learner; AUC, log loss, Brier, ECE, accuracy;
   one table; every run recorded with dataset version, seed, config, git
   commit and hardware.
5. **Policy**: rules with scores and reason codes; bandits later, with
   learning progress as the reward.
6. **Not adopted in V0, with the falsification test that would admit
   them**: GNNs (must beat prerequisite features), RL (must beat the
   rule policy on measured learning gain on real learners), cognitive
   diagnosis models (need a Q-matrix Noema does not have).

The word "state-of-the-art" does not appear in this repository's claims
and will not until a reproducible benchmark on a public dataset earns it.
