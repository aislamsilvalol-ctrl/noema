# NOEMA — Mastery Engine

The Mastery Engine answers: **how well does this user know this concept, right now?**

It is separate from FSRS on purpose. FSRS models memory of a *card*. Mastery models
understanding of a *concept*, which may be backed by many cards, many questions, an open
answer graded by AI, or nothing at all.

## 1. Design constraints

1. **Explainable.** The UI shows a number between 0 and 100. Every number must decompose
   into terms a user can read. We store the decomposition (`concept_mastery.components`).
2. **Recomputable.** Mastery is a pure function of the append-only evidence log plus the
   graph. Never incrementally mutated in place beyond caching.
3. **Honest about ignorance.** A concept with two data points must not display 100.
4. **Time-aware.** Knowing something in March is not knowing it in August.

## 2. Notation

For user *u* and concept *c*, evidence is a set of graded events:

$$e_i = (s_i,\; d_i,\; \kappa_i,\; t_i,\; \sigma_i)$$

| symbol | meaning | range |
|---|---|---|
| $s_i$ | correctness score (partial credit allowed) | $[0,1]$ |
| $d_i$ | item difficulty | $[0,1]$ |
| $\kappa_i$ | declared confidence (nullable) | $\{1..5\}$ |
| $t_i$ | timestamp | |
| $\sigma_i$ | grader kind | `deterministic \| ai \| self` |
| $\Delta_i$ | age in days, $= (t_{now} - t_i)/86400$ | |

## 3. Competence — $C \in [0,1]$

A weighted Beta posterior mean. Evidence is weighted; the prior comes from prerequisites.

$$w_i = w^{rec}_i \cdot w^{dif}_i \cdot w^{src}_i \cdot w^{conf}_i$$

**Recency.** Old evidence is weaker evidence *about current competence* (a separate concern
from memory decay, handled in §4):

$$w^{rec}_i = \exp(-\Delta_i / \tau), \qquad \tau = 60 \text{ days}$$

**Difficulty.** Getting an expert item right is more informative than an easy one:

$$w^{dif}_i = 0.5 + d_i \quad \in [0.5, 1.5]$$

**Grader trust.** AI grading of open answers is useful but not ground truth:

$$w^{src}_i = \begin{cases} 1.0 & \text{deterministic} \\ 0.7 & \text{ai} \\ 0.4 & \text{self-reported} \end{cases}$$

**Confidence.** A correct guess is weak positive evidence; a confident error is strong
negative evidence:

$$w^{conf}_i = \begin{cases}
0.5 + 0.125\,(\kappa_i - 1) & s_i \ge 0.5 \quad \text{(0.5 at a guess → 1.0 when sure)}\\
1.0 + 0.125\,(\kappa_i - 1) & s_i < 0.5 \quad \text{(1.0 → 1.5 for confident errors)}\\
1.0 & \kappa_i \text{ missing}
\end{cases}$$

**Prior from prerequisites.** With pseudo-count $k_0 = 4$ and

$$\mu_0 = \begin{cases}
\dfrac{\sum_{p \in \mathrm{prereq}(c)} \omega_p \cdot M_p/100}{\sum_p \omega_p} & \text{if prerequisites exist}\\[2ex]
0.35 & \text{otherwise}
\end{cases}$$

where $\omega_p$ is the prerequisite edge weight. So a concept whose prerequisites are solid
starts optimistic, and one built on shaky ground starts pessimistic — which is exactly the
belief a tutor would hold.

$$\alpha_0 = k_0\mu_0,\qquad \beta_0 = k_0(1-\mu_0)$$

$$\boxed{\;C = \frac{\alpha_0 + \sum_i w_i s_i}{\alpha_0 + \beta_0 + \sum_i w_i}\;}$$

The posterior variance $\mathrm{Var} = \frac{\alpha\beta}{(\alpha+\beta)^2(\alpha+\beta+1)}$
is kept as the engine's own uncertainty and drives the UI: below $k_0 + 3$ effective
observations we render mastery as a range, not a point.

## 4. Retrievability — $R \in [0,1]$

Probability the user could recall the concept *right now*.

If the concept has cards, aggregate FSRS retrievability (see [`fsrs.md`](./fsrs.md)):

$$R = \frac{\sum_{j \in \mathrm{cards}(c)} v_j \, R_j(t)}{\sum_j v_j}, \qquad
R_j(t) = \left(1 + \frac{19}{81}\cdot\frac{t_j}{S_j}\right)^{-0.5}$$

with $v_j$ the card's coverage weight (how much of the concept that card tests; default 1).

If the concept has no cards, fall back to an exponential decay whose half-life grows with
the amount of successful evidence:

$$R = \exp\!\left(-\frac{\Delta_{last}}{S_{est}}\right), \qquad
S_{est} = S_0 \,(1 + n_{success})^{0.6}, \quad S_0 = 3 \text{ days}$$

## 5. Mastery

$$\boxed{\;M = 100 \cdot C \cdot \bigl(\lambda + (1-\lambda) R\bigr), \qquad \lambda = 0.5\;}$$

Read it plainly: **half of mastery is competence you have demonstrated, half is whether you
can retrieve it today.** A concept you once knew perfectly and have not touched in a year
floors at 50, not 0 — you have not lost the understanding, you have lost the access. That
matches how relearning actually behaves, and it keeps the number from being demoralising
noise.

Multiplying rather than averaging is deliberate: $C = 0$ must produce $M = 0$ regardless of
how recently you saw the material.

## 6. Calibration

Tracked separately, never folded into $M$:

$$\mathrm{cal} = \frac{1}{n}\sum_i \left(\frac{\kappa_i - 1}{4} - s_i\right) \in [-1, 1]$$

Positive means overconfident, negative means underconfident. Overconfidence is the signal
the Misconception Engine consumes; underconfidence changes the tutor's behaviour (it should
stop over-explaining to someone who already knows the material).

## 7. Weak concepts

A concept is weak when any of:

- $M < 60$ with at least $k_0$ effective observations;
- $\mathrm{cal} > 0.3$ (believes they know it, doesn't);
- an unresolved misconception is attached;
- $R < 0.6$ while $C > 0.8$ — known but fading, the cheapest possible intervention.

Weak concepts are ranked by **impact**, not by how low the score is:

$$I(c) = (1 - M_c/100) \cdot \Bigl(1 + \sum_{k \ge 1} \gamma^k \,|\mathrm{descendants}_k(c)|\Bigr), \quad \gamma = 0.5$$

A shaky prerequisite with eight things stacked on it outranks an isolated concept at the
same score. This is the single most useful thing the graph buys us.

## 8. Recomputation

- **Incremental**, on each new evidence event: recompute the touched concept and propagate
  to direct dependents (their prior moved). Depth-limited to 2 hops.
- **Nightly**, per active user: full recompute so time decay is reflected without traffic.
- **Backfill**, on formula change: a versioned `mastery_model_version` on the projection;
  a migration rebuilds from the evidence log and old rows are kept for one release so the
  change can be evaluated rather than assumed.

## 9. Constants

Every constant above (`τ, k_0, λ, γ, S_0`, weights) lives in one typed settings object with
these values as defaults. They are guesses informed by the literature, not tuned facts, and
they are the first thing to calibrate once there is real review history to fit against.
