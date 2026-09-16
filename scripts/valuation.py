#!/usr/bin/env python
"""What NOEMA is worth today — and what would actually change that.

    python3 scripts/valuation.py             print the range
    python3 scripts/valuation.py --record    print it and append it to history

Reads `docs/valuation.yaml` (the facts), checks what the repository can check
on its own, and prints a range. `--record` appends the result to
`docs/valuation-history.jsonl`, so the number can be watched moving instead of
argued about — and so a month from now it is possible to see what moved it.

It refuses to print a single number. A single number for a company with no
customers is a sentence dressed as a measurement. It prints three, and they
mean different things:

  what could change hands today   the cost of rebuilding it, and nothing else
  what the bet is worth           a probability times an outcome — unsellable
  what revenue would make it      zero, until someone pays

The uncomfortable part is deliberate. Finishing a feature moves the first
number by the cost of the week it took, and moves the second not at all. The
only thing that moves this page is evidence that a stranger pays and returns.
That is not a flaw in the model; it is the finding.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "docs" / "valuation.yaml"
HISTORY = ROOT / "docs" / "valuation-history.jsonl"
SNAPSHOT = ROOT / "apps" / "web" / "src" / "data" / "sabelia-benchmarks.json"

# The gates, in the order evidence actually arrives. Named once so the report
# and the ladder cannot drift apart.
GATE_MEANS = {
    "idea": "code exists",
    "launched": "strangers can reach it",
    "first_paying": "someone paid, once",
    "hundred_retained": "a hundred pay and come back",
}


def brl(value: float, cents: bool = False) -> str:
    if cents:
        return "R$ " + f"{value:,.2f}".replace(",", "|").replace(".", ",").replace("|", ".")
    return "R$ " + f"{round(value):,}".replace(",", ".")


def git(*args: str) -> str:
    done = subprocess.run(("git", "-C", str(ROOT), *args), capture_output=True, text=True)
    return done.stdout.strip()


def ml_standing() -> list[tuple[str, int | None, int, str]]:
    """Where the engine places among the baselines, per public dataset.

    Variants of the candidate are not competitors, so they are dropped: the
    question is whether the thing we ship beats something a competent person
    could write in an afternoon.
    """
    if not SNAPSHOT.exists():
        return []
    standing = []
    for dataset in json.loads(SNAPSHOT.read_text())["datasets"]:
        if dataset["kind"] != "public":
            continue
        rows = sorted(
            (m for m in dataset["models"] if not m["model"].startswith("sabelia-")),
            key=lambda m: -m["auc"],
        )
        names = [m["model"] for m in rows]
        rank = names.index("sabelia") + 1 if "sabelia" in names else None
        standing.append((dataset["dataset"], rank, len(names), names[0]))
    return standing


def audit(facts: dict[str, Any]) -> list[str]:
    """Where the facts file and the repository disagree.

    A valuation whose inputs nobody re-checks becomes a story within a month.
    """
    warnings = []
    standing = ml_standing()
    beats = bool(standing) and all(rank == 1 for _, rank, _, _ in standing)
    if beats != facts["assets"]["ml_beats_every_baseline"]:
        warnings.append(
            f"assets.ml_beats_every_baseline says "
            f"{facts['assets']['ml_beats_every_baseline']}, the benchmarks say {beats}"
        )
    if facts["traction"]["paying_customers"] > 0 and facts["traction"]["mrr"] == 0:
        warnings.append("paying customers but no MRR — one of the two is wrong")
    if facts["traction"]["mrr"] > 0 and not facts["assets"]["billing_configured"]:
        warnings.append("MRR without billing configured — where is the money arriving?")
    if facts["traction"]["signups"] > 0 and not facts["traction"]["launched"]:
        warnings.append("signups without a launch — say launched: true or explain them")
    return warnings


def gate(traction: dict[str, Any]) -> str:
    retention = traction.get("retention_week4") or 0
    if traction["paying_customers"] >= 100 and retention >= 0.40:
        return "hundred_retained"
    if traction["paying_customers"] >= 1:
        return "first_paying"
    if traction["launched"]:
        return "launched"
    return "idea"


def present_value(option: dict[str, Any]) -> float:
    """What R$ 1M of annual revenue, three years out, is worth today."""
    future = option["target_arr"] * option["exit_multiple"]
    return future / (1 + option["discount_rate"]) ** option["years_to_target"]


def revenue_multiple(facts: dict[str, Any]) -> tuple[float, float]:
    """Early-stage consumer subscription, small and unproven: 1,5–4× ARR.

    The top of that band belongs to a business whose gross margin is known. A
    tutoring product pays for inference per active learner; until that cost is
    measured the margin is a guess, and the band collapses to its floor.
    """
    low, high = 1.5, 4.0
    if facts["burn"]["ai_cost_per_active_month"] is None:
        high = low
    return low, high


def movement(now: dict[str, Any]) -> list[str]:
    """What changed since the last recorded valuation."""
    if not HISTORY.exists():
        return []
    lines = [l for l in HISTORY.read_text().splitlines() if l.strip()]
    if not lines:
        return []
    before = json.loads(lines[-1])
    out = [f"    since {before['as_of']}:"]
    if before["gate"] != now["gate"]:
        out.append(f"      stage  {before['gate']} → {now['gate']}")
    for key, label in (("floor_high", "cost to duplicate"), ("bet", "expected value of the bet")):
        delta = now[key] - before[key]
        if abs(delta) >= 1:
            out.append(f"      {label:24} {'+' if delta > 0 else '−'}{brl(abs(delta))}")
    return out if len(out) > 1 else [f"    nothing has moved since {before['as_of']}."]


def main() -> int:
    facts = yaml.safe_load(FACTS.read_text())
    build, traction, option = facts["build"], facts["traction"], facts["option"]

    # 1. The floor: what someone would spend to have what you have.
    months, rate = build["founder_months"], build["market_rate_month"]
    floor_low = months * rate * build["rebuild_low"] + build["infra_spent"]
    floor_high = months * rate * build["rebuild_high"] + build["infra_spent"]

    # 2. The bet, priced as a bet.
    here = gate(traction)
    pv = present_value(option)
    bet = option[f"p_{here}"] * pv

    # 3. Revenue. There is none, and the arithmetic should say so out loud.
    arr = traction["mrr"] * 12
    mult_low, mult_high = revenue_multiple(facts)

    print(f"\nNOEMA — valuation, {facts['as_of']}")
    print("A range with its reasons. Most of the reasons are zeros.\n")

    print("  WHAT COULD CHANGE HANDS TODAY")
    print(
        f"    cost to duplicate       {brl(floor_low)} – {brl(floor_high)}"
        f"   ({months} months × {brl(rate)}, {git('rev-list', '--count', 'HEAD')} commits)"
    )
    entity = facts["company"]["entity"]
    print(
        f"    transferable now        {brl(0)}"
        f"   {'no entity, no contracts, no customers' if entity == 'none' else 'entity exists'}"
    )
    print("    a buyer of code without customers is hiring you, and would say so.\n")

    print("  WHAT THE BET IS WORTH")
    print(f"    expected value          {brl(bet)}   {option[f'p_{here}']:.0%} × {brl(pv)}")
    print(f"    stage                   {here} — {GATE_MEANS[here]}")
    print("    you cannot sell this number. It prices the ticket, not the prize.\n")

    print("  WHAT REVENUE WOULD MAKE IT")
    if arr == 0:
        print(f"    mrr {brl(0)} → arr {brl(0)} → {brl(0)}. Nothing is a multiple of nothing.")
    else:
        print(
            f"    arr {brl(arr)} × {mult_low}–{mult_high}   "
            f"{brl(arr * mult_low)} – {brl(arr * mult_high)}"
        )
        if facts["burn"]["ai_cost_per_active_month"] is None:
            print("    upper band withheld: inference cost per learner never measured.")
    print()

    print("  WHERE VALUE ACTUALLY COMES FROM")
    price = facts["pricing"]["price_month"]
    print(f"    finish the whole roadmap                  +{brl(0)}   nobody pays for features")
    for n in (1, 10, 100, 1000, 2800):
        n_arr = n * price * 12
        low, high = n_arr * mult_low, n_arr * mult_high
        band = brl(low) if low == high else f"{brl(low)} – {brl(high)}"
        mark = "   ← worth more than the entire build" if low > floor_high else ""
        print(f"    {n:>5} paying at {brl(price, cents=True)}/month        {band}{mark}")
    print(
        f"    and the evidence is worth more than the revenue: moving from\n"
        f"    '{here}' to 'first_paying' adds {brl(option['p_first_paying'] * pv - bet)} "
        f"of expected value, on {brl(price * 12, cents=True)} of actual money.\n"
    )

    print("  DEDUCTIONS A BUYER WOULD MAKE")
    reasons = {
        "training_data_non_commercial": "datasets are CC BY-NC: the ML story cannot ship commercially as it stands",
        "single_founder_key_person": "one person; the asset walks out at the end of the day",
        "no_legal_entity": "nothing exists to acquire but the code and you",
        "no_registered_trademark": "the name is not defended",
    }
    for key, why in reasons.items():
        if facts["risks"].get(key):
            print(f"    · {why}")
    for dataset, rank, total, best in ml_standing():
        if rank != 1:
            print(f"    · on {dataset} the engine places {rank}/{total}, behind {best}")
    burn = facts["burn"]["infra_month"] + facts["burn"]["ai_month"]
    print(f"    · {brl(burn)}/month of burn against {brl(traction['mrr'])} of revenue\n")

    warnings = audit(facts)
    if warnings:
        print("  THE FACTS FILE DISAGREES WITH THE REPOSITORY")
        for warning in warnings:
            print(f"    ! {warning}")
        print()

    record = {
        "as_of": str(facts["as_of"]),
        "recorded_at": round(time.time()),
        "git": git("rev-parse", "--short", "HEAD"),
        "gate": here,
        "floor_low": round(floor_low),
        "floor_high": round(floor_high),
        "bet": round(bet),
        "arr": round(arr),
        "paying": traction["paying_customers"],
    }
    moved = movement(record)
    if moved:
        print("  MOVEMENT")
        print("\n".join(moved) + "\n")

    print(f"  HONEST RANGE TODAY      {brl(floor_low)} – {brl(floor_high + bet)}")
    print("  and the top of that range is a bet you cannot cash.\n")

    if "--record" in sys.argv:
        with HISTORY.open("a") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        print(f"  recorded → {HISTORY.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
