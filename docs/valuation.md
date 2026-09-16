# What NOEMA is worth

`python3 scripts/valuation.py --record`

A tracker that recomputes the number as the work advances, and an honest
account of why the number moves so little when the work advances.

## What this is, and what it is not

A valuation is not a measurement. For a company with customers it is a
negotiated price anchored on cash flows; for a company without them it is an
opinion about the future with a currency symbol in front of it. The press
reports post-money valuations as if they were appraisals — they are the
arithmetic of a round someone agreed to, and if no one agrees to a round, the
number does not exist.

So this file does not print one number. It prints three, and keeps them apart
because they answer different questions:

| | question it answers | today |
|---|---|---|
| **Cost to duplicate** | what would someone spend to have this? | R$ 29.400 – 47.400 |
| **Expected value of the bet** | what is the lottery ticket worth? | R$ 21.866 |
| **Revenue multiple** | what do the cash flows support? | R$ 0 |

Only the first is defensible today. The second cannot be sold — it is a
probability times an outcome, and probabilities do not clear at a bank. The
third is the only one that ever becomes a real price, and it is zero until
someone pays.

**Honest range on 2026-09-16: R$ 29.400 – R$ 69.266**, and the top of that
range is a bet, not an asset.

## Why finishing features barely moves it

The cost-to-duplicate number is the month of work, priced at what it would
cost to hire the month of work: 1,2 calendar months at R$ 30.000 of loaded
senior salary, plus infrastructure. Another week of building adds another week
of salary — around R$ 7.000 — and nothing else. That is the entire mechanical
effect of shipping.

It is tempting to believe that 313 commits and ~110.000 lines are worth more
than their cost. They are not, for a specific reason: **the same tools that
let one person build this in a month let the next person rebuild it in a
month.** Scarcity is what carries a premium, and speed that everyone has is
not scarcity. Lines of code are a cost, recorded in the ledger as a cost.

What does carry a premium is the thing nobody can copy from the repository:
a group of people who use the product and pay for it. That is why the ladder
in the script exists — to keep the comparison in view.

    finish the whole roadmap             +R$ 0
    100 paying at R$ 29,90/month         R$ 53.820  ← more than the entire build

A hundred subscribers are worth more than every line written so far. This is
not a rhetorical device; it is the arithmetic, and it is the single most
useful fact on this page.

## What actually moves it: the four gates

The script tracks stages, not features, because evidence is what changes a
probability:

| gate | what it proves | probability of reaching R$ 1M/year |
|---|---|---|
| `idea` | code exists | 2% |
| `launched` | strangers can reach it | 5% |
| `first_paying` | someone paid, once | 12% |
| `hundred_retained` | a hundred pay and come back | 35% |

Those percentages are priors, not measurements — they live in
`docs/valuation.yaml` precisely so they can be argued with rather than
assumed. They follow the ordinary base rates: most products never launch, most
launched products never take a second payment, and most that do never reach
R$ 1M of annual revenue.

The consequence is the sharpest number here. **Moving from `idea` to
`first_paying` adds about R$ 109.000 of expected value on R$ 358,80 of actual
money.** The first subscription is worth roughly three times the whole
codebase, and almost none of that is the revenue — it is the information that
a stranger will pay, which is the one fact this project has never had.

Target: R$ 1.000.000 of annual revenue, about 2.800 subscribers. Not an exit,
not a unicorn — a company that pays two salaries. Discounted three years at
40%, which is what capital costs at this stage when it is honest about risk.

## What a buyer would deduct

These are not footnotes. Each one lowers the number, and three of them are
fixable this month:

- **The training data is CC BY-NC.** EdNet, the Duolingo traces and MIT OCW
  are all licensed for non-commercial use. Benchmarks and research are fine —
  that is what the licence is for. Shipping a model trained on them inside a
  paid product, or serving material derived from them, is not. As it stands,
  the ML work is a research asset and not a commercial one, and a buyer's
  lawyer finds this in an afternoon.
- **No legal entity.** There is no CNPJ, so there is nothing to buy except the
  code and the person. An acquirer in this position is hiring you and would
  price it that way.
- **One founder.** The asset walks out at the end of the day.
- **The engine is second, not first.** On EdNet it places 2 of 13 behind
  gradient boosting; on Duolingo it places 1 of 13, by 0,0006 AUC — three
  seeds out of three, and still inside the noise. It now beats the feature
  logistic on every seed of both datasets, which was not true a week ago. It
  is a good research result and not yet a moat; nobody has ever paid for an
  AUC.
- **R$ 150/month of burn against R$ 0 of revenue.** Small, but the direction
  matters: every month without evidence spends money and produces no new
  reason for the number to rise.

## What this deliberately does not do

- No comparable-company multiples. "Duolingo trades at N× revenue" says
  nothing about a product with no revenue.
- No TAM slice. "The Brazilian education market is R$ X billion and we take
  1%" is not a forecast, it is a wish with a multiplication sign.
- No DCF on projected subscribers. Discounting invented cash flows produces a
  precise number from nothing, which is worse than an honest range.
- No premium for the AI. It is currently a liability on the licence side and a
  second-place finish on the benchmark side.

## Using it

Facts live in `docs/valuation.yaml`, arithmetic in `scripts/valuation.py`, so
that changing what you believe requires editing a line that says what you
believe. The script re-checks what the repository can prove — commit count,
where the engine places against its baselines — and prints a warning when the
facts file and the repository disagree.

Run it when something real changes — a launch, a first customer, a measured
retention number — and record it:

    python3 scripts/valuation.py --record

Each record appends to `docs/valuation-history.jsonl`, and the next run prints
what moved since the last one. Recording a run after every feature will
produce a flat line for months. That flat line is the most honest chart in
this repository, and it turns upward on the day somebody pays.
