# NOEMA — FSRS Integration

NOEMA schedules cards with **FSRS** (Free Spaced Repetition Scheduler), the DSR
model — Difficulty, Stability, Retrievability — that replaced SM-2 as the state of the art
in open spaced-repetition tooling.

## 1. Why FSRS and not SM-2

SM-2 tracks one "ease factor" and multiplies intervals by it. It has no notion of memory
stability, cannot model how difficulty and retention interact, and its parameters cannot be
fit to a user. FSRS separates the three quantities that actually matter and its weights are
*optimisable from a user's own review log* — which fits NOEMA's core premise exactly. We do
not invent a scheduler. We implement FSRS faithfully and put our originality in the layers
above it.

## 2. The model

Each card carries state $(S, D)$ — stability in days, difficulty in $[1,10]$ — plus its due
date and counters.

**Forgetting curve** (FSRS-4.5/5 power form, better-fitting than pure exponential):

$$R(t, S) = \left(1 + F\cdot\frac{t}{S}\right)^{C}, \qquad F = \frac{19}{81},\; C = -0.5$$

**Interval for a target retention** $R^\*$ (default 0.90, user-configurable 0.80–0.97):

$$I(S) = \frac{S}{F}\left((R^\*)^{1/C} - 1\right)$$

**Initial state** after the first review with grade $G \in \{1..4\}$
(Again, Hard, Good, Easy):

$$S_0(G) = w_{G-1}, \qquad D_0(G) = w_4 - e^{\,w_5 (G-1)} + 1 \;\text{clamped to}\; [1,10]$$

**Difficulty update** (with mean reversion toward the easy anchor, which stops difficulty
from ratcheting upward forever):

$$D' = w_7\,D_0(4) + (1-w_7)\bigl(D - w_6\,(G-3)\bigr)$$

**Stability after a successful review** ($G > 1$):

$$S' = S\Bigl(1 + e^{w_8}\,(11-D)\,S^{-w_9}\,\bigl(e^{w_{10}(1-R)}-1\bigr)\,\theta_G\Bigr)$$

where $\theta_G$ applies the hard penalty $w_{15}$ ($G=2$) and easy bonus $w_{16}$ ($G=4$).

**Stability after a lapse** ($G = 1$):

$$S' = \min\Bigl(w_{11}\,D^{-w_{12}}\bigl((S+1)^{w_{13}}-1\bigr)e^{w_{14}(1-R)},\; S\Bigr)$$

The 17–21 weights $w$ ship with the published defaults.

## 3. Integration in NOEMA

### Placement

`noema/engines/fsrs.py` — **pure functions over frozen dataclasses**. No database, no
clock. `now` is an argument. This is what makes it testable against the reference
implementation's fixtures and what lets the optimiser replay history offline.

```python
@dataclass(frozen=True, slots=True)
class MemoryState:
    stability: float
    difficulty: float

def next_state(state: MemoryState | None, rating: Rating,
               elapsed_days: float, w: Weights) -> MemoryState: ...

def retrievability(state: MemoryState, elapsed_days: float) -> float: ...

def interval(state: MemoryState, target_retention: float) -> float: ...
```

### Review flow

1. Client posts `{card_id, rating, elapsed_ms, confidence?}`.
2. API loads `card_states`, computes `elapsed_days` from `last_review_at`.
3. `next_state` produces $(S', D')$; `interval` produces `due_at` with fuzz (±5%, so cards
   introduced together do not stay clumped forever).
4. Write the new `card_states` row **and** an append-only `reviews` row containing
   `state_before` and `state_after`. The projection is disposable; the log is not.
5. Emit a `ReviewRecorded` event → Mastery Engine recomputes the linked concepts.

### Rating semantics in the UI

Four buttons, labelled by outcome rather than by feeling, each showing its resulting
interval:

| | meaning | shown |
|---|---|---|
| Again | could not recall | `<10m` |
| Hard | recalled with effort | `2d` |
| Good | recalled | `6d` |
| Easy | instant | `14d` |

### Confidence is not a rating

The confidence prompt (§ Confidence System) is asked *after* the rating and does not feed
FSRS. FSRS weights are fit against a grade signal; injecting a second uncalibrated signal
would break that fit. Confidence flows only into mastery and misconception detection.

### Parameter optimisation

Once a user has ≥ 400 reviews, a weekly worker job fits their personal weights by maximising
log-likelihood of observed outcomes under the model (the standard FSRS optimiser
formulation), and stores them per user. Below that threshold everyone uses the defaults;
fitting 19 parameters on 40 reviews produces confident nonsense.

Optimisation is opt-in, reversible (weights are versioned), and reports the log-loss before
and after so the user can see whether it actually helped.

### Load balancing

The scheduler may shift a card's due date within $\pm 5\%$ of its interval to smooth daily
workload. Larger shifts are refused — protecting the user's retention target matters more
than a flat calendar.

## 4. What we deliberately do not do

- No "leech" auto-suspension. A card you keep failing is a signal for the Prerequisite
  Engine, not garbage to be hidden.
- No modification of the FSRS formulas. Ideas about better scheduling belong in the
  Learning Engine's selection layer, where they can be evaluated independently.
- No burying/sibling logic in v1.

## 5. Testing

- Parity fixtures against the reference implementation: same input sequence, same $(S, D)$
  to 1e-6.
- Property tests: $S$ strictly increases on `Good`; $R$ is monotonically decreasing in $t$;
  $R(0) = 1$; difficulty stays in $[1, 10]$ under any rating sequence.
- Replay test: 10k synthetic reviews, assert realised retention lands within 3 points of the
  configured target.
