# NOEMA — Adaptive Learning Engine

The user opens NOEMA with 30 minutes. The engine decides what those 30 minutes contain.
This is the feature the whole product exists to deliver.

## 1. Framing

It is a **constrained selection problem**: choose a set of study items maximising expected
learning gain, subject to a time budget and pedagogical constraints.

Not a recommender system in the ML sense — there is no collaborative signal, and there
should not be. Everything is derived from one learner's own state, which is both a privacy
property and a correctness property.

## 2. Candidate items

| kind | source | cost estimate |
|---|---|---|
| `card_review` | FSRS-due cards | rolling median of the user's per-card time, default 8s |
| `card_learn` | new cards on active concepts | 15s |
| `question` | generated for weak concepts | 45s (open answers 120s) |
| `misconception_drill` | targeted questions from the Mistake Bank | 90s |
| `read` | note/section for an unlearned concept | tokens / 200 wpm |
| `feynman` | explain-back on a high-mastery-claim concept | 180s |
| `prereq_repair` | a prerequisite blocking progress | inherits its own kind |

Costs are **measured, not assumed** — the engine keeps a per-user running median and the
plan gets more accurate the more it is used.

## 3. Utility

For candidate $x$ touching concept $c$:

$$U(x) = \underbrace{\Delta R(x)}_{\text{memory gained}} \cdot \underbrace{I(c)}_{\text{importance}} \cdot \underbrace{\pi(x)}_{\text{pedagogical multiplier}} \Big/ \underbrace{\mathrm{cost}(x)}_{\text{seconds}}$$

**Memory gain $\Delta R$.** For a card, the expected long-run retention gained by reviewing
it now, which is largest when retrievability sits near the target — reviewing something at
$R = 0.99$ wastes time, at $R = 0.3$ you have already forgotten it and it costs a relearn:

$$\Delta R(x) = R(t)\bigl(1 - R(t)\bigr)\cdot\frac{S'-S}{S'}$$

This peaks around $R = 0.5$ but is tempered by the stability ratio, which favours reviews
that actually move the needle. For questions and reading, $\Delta R$ is approximated from
the expected mastery delta under the Mastery Engine's Beta update.

**Importance $I(c)$** is the graph-weighted impact from
[`mastery-engine.md`](./mastery-engine.md) §7, boosted for concepts on an active
`StudyGoal`'s learning path and by goal deadline proximity:

$$I'(c) = I(c)\cdot\bigl(1 + 1.5 \cdot \mathbb{1}[c \in \text{goal}]\bigr)\cdot\bigl(1 + \text{urgency}\bigr)$$

**Pedagogical multiplier $\pi$** encodes what we believe about learning, in one auditable
place:

| condition | $\pi$ |
|---|---|
| overdue card ($t > 1.5\,I$) | 1.4 |
| unresolved misconception | 2.0 |
| prerequisite of something the user is currently failing | 1.8 |
| concept studied within the last 4 hours | 0.4 (spacing, not cramming) |
| interleaving bonus — different concept from the previous item | 1.15 |
| new material while > 40 reviews are already overdue | 0.3 |

That last row is the rule that keeps NOEMA honest: it will not let someone start a shiny new
subject while their existing knowledge rots.

## 4. Selection

Greedy by $U$ under the time budget, then repaired by constraints. Greedy is within a
constant factor of optimal for this knapsack shape and runs in milliseconds — a proper
solver is not worth the dependency.

Constraints applied after greedy fill:

1. **Warm-up.** First 15% of the session is due reviews, never new material.
2. **Prerequisite ordering.** If both $p$ and $c$ are selected and $p \to c$ is a
   prerequisite edge, $p$ comes first.
3. **Interleaving.** No more than 3 consecutive items from the same concept.
4. **Cognitive load.** At most one `feynman` or long-open item per 25 minutes.
5. **Cool-down.** Final 10% is high-$R$ cards — end on success. This is a motivation
   decision, made explicitly rather than smuggled in as gamification.

## 5. Prerequisite Engine

Triggered when a concept accumulates 3 failures within 14 days, or mastery drops while
review volume is normal.

1. Walk `prerequisite_of` edges backwards from $c$, up to depth 3.
2. Score each ancestor $p$ by $\bigl(1 - M_p/100\bigr)\cdot \omega_{p\to c}$.
3. If the best ancestor scores above 0.45, the engine **reroutes**: it inserts $p$'s repair
   items ahead of $c$ and tells the user why, in plain language — *"Backpropagation keeps
   slipping. Your chain rule mastery is 38%. Let's fix that first."*
4. If no weak ancestor is found, the problem is local: generate varied-format questions on
   $c$ itself rather than repeating the same card.

Blocked concepts render as `locked` on the learning path until their prerequisites clear 65.

## 6. Misconception Engine

**Detection.** An answer with $s < 0.5$ and $\kappa \ge 4$ writes a `mistakes` row with
`is_misconception = true`. Two independent confident errors on the same concept escalate it
to a first-class object with a generated summary of *what the user appears to believe*,
extracted from their actual wrong answers — not a generic "you got this wrong".

**Correction.** Targeted items are generated with a specific brief: contrast the belief with
the correct model, prefer discriminating cases where the wrong model gives a different
answer than the right one. A misconception is only marked resolved after **two spaced
correct answers with confidence ≥ 4** — one lucky correction proves nothing.

**Why this matters.** Confident errors are the failures normal spaced repetition never
catches, because the learner never flags them for review. This is the difference between
NOEMA and a flashcard app.

## 7. Session shape

```
GET /api/v1/learning-session/plan?minutes=30

{
  "estimated_minutes": 29,
  "rationale": "Backpropagation is your weakest concept blocking 4 others.",
  "blocks": [
    {"kind": "warmup",  "minutes": 5,  "items": [...12 due cards]},
    {"kind": "repair",  "minutes": 10, "concept": "Chain Rule",
     "why": "prerequisite of Backpropagation (mastery 38%)"},
    {"kind": "practice","minutes": 9,  "items": [...6 questions]},
    {"kind": "cooldown","minutes": 5,  "items": [...8 high-retrievability cards]}
  ]
}
```

`rationale` and per-block `why` are required fields, not decoration. If the engine cannot
explain a choice in one sentence, that is a bug in the engine.

## 8. Evaluation

Plans are stored (`study_sessions.plan`) alongside outcomes, which gives us:

- **Calibration**: predicted vs. actual session duration.
- **Retention**: realised recall vs. the FSRS target.
- **Counterfactual replay**: re-run a new engine version against historical evidence logs
  and compare predicted retention. Cheap, offline, and the only defensible way to say a
  change to the scheduler is an improvement.

Every heuristic constant in §3 is a tunable in one settings object, and every one of them is
a hypothesis until replay says otherwise.
