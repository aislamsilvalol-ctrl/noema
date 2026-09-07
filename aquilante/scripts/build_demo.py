"""Build the Aquilante demo page: a knowledge map and a lab view from real pipeline output.

    .venv/bin/python scripts/build_demo.py --runs benchmarks/runs-3seeds --out examples/demo/index.html

Everything on the page is computed by the library on this machine when the
script runs: a learner is simulated, the recency heuristic (the fallback
model) estimates mastery, the half-life model estimates recall, the policy
recommends an action with its reason codes, and the benchmark table is read
from ``runs.jsonl``. No numbers are typed in. Pure HTML + inline SVG, no
JavaScript dependencies, so it renders anywhere and diffs in git.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import statistics
import time
from pathlib import Path

from aquilante.data.adapters import synthetic_dataset
from aquilante.features.sequences import split_by_student
from aquilante.inference.learner import Learner
from aquilante.memory.forgetting import HalfLifeModel
from aquilante.simulation.simulator import SimulatorConfig, prerequisite_edges, simulate

CREAM = "#faf7f1"
INK = "#1c1917"
INK_SOFT = "#6b6259"
LINE = "#e6dfd3"
ORANGE = "#b5450c"
GREEN = "#2f6b3a"
RED = "#a3372f"


def esc(s: object) -> str:
    return html.escape(str(s))


# ── the learner ──────────────────────────────────────────────────────────


def build_learner(seed: int = 11):
    cfg = SimulatorConfig(students=1, subjects=2, concepts_per_subject=6, events_per_student=90, seed=seed)
    events = list(simulate(cfg))
    # fit the forgetting model on a population from the same generator, not on this learner
    train, _, _ = split_by_student(synthetic_dataset(students=150, events_per_student=80, seed=seed + 1), seed=0)
    forgetting = HalfLifeModel().fit(train)
    prereq: dict[str, list[str]] = {}
    for a, b in prerequisite_edges(cfg):
        prereq.setdefault(b, []).append(a)
    learner = Learner(events[0].student_id, forgetting=forgetting, prerequisites=prereq)
    learner.observe_many(events)
    now = events[-1].timestamp + 3 * 86400  # three days after the last practice
    return learner, prereq, now, events


def knowledge_map_svg(state, prereq: dict[str, list[str]]) -> str:
    concepts = sorted(state.concepts.values(), key=lambda c: c.concept_id)
    subjects = sorted({c.concept_id.split(":")[0] for c in concepts})
    W, H = 760, 120 + 130 * len(subjects)
    pos: dict[str, tuple[float, float]] = {}
    for row, subj in enumerate(subjects):
        row_concepts = [c for c in concepts if c.concept_id.startswith(subj + ":")]
        for i, c in enumerate(row_concepts):
            x = 80 + i * (W - 160) / max(1, len(row_concepts) - 1)
            y = 90 + row * 130
            pos[c.concept_id] = (x, y)
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="knowledge map" font-family="ui-sans-serif, system-ui" font-size="11">']
    for b, pre in prereq.items():
        for a in pre:
            if a in pos and b in pos:
                (x1, y1), (x2, y2) = pos[a], pos[b]
                parts.append(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" stroke="{LINE}" stroke-width="2"/>')
    for c in concepts:
        x, y = pos[c.concept_id]
        r = 14 + 14 * c.mastery
        if c.attempts == 0:
            fill, label = "#ffffff", "unknown"
        elif c.mastery >= 0.8 and c.recall >= 0.75:
            fill, label = GREEN, "mastered"
        elif c.recall < 0.75 and c.mastery >= 0.45:
            fill, label = ORANGE, "review due"
        elif c.confidence < 0.35:
            fill, label = "#c9a227", "uncertain"
        else:
            fill, label = "#7a8fa6", "learning"
        ring = max(1.5, 6 * (1 - c.confidence))
        parts.append(
            f'<g><circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.1f}" fill="{fill}" fill-opacity="0.85" stroke="{INK}" stroke-opacity="0.35" stroke-width="{ring:.1f}" stroke-dasharray="{"3 3" if c.confidence < 0.35 else "none"}"/>'
            f'<title>{esc(c.concept_id)} · {label}\nmastery {c.mastery:.2f} · confidence {c.confidence:.2f} · recall {c.recall:.2f}\n{c.attempts} attempts, {c.correct} correct · last practised {c.days_since:.1f} d ago</title>'
            f'<text x="{x:.0f}" y="{y + r + 14:.0f}" text-anchor="middle" fill="{INK_SOFT}">{esc(c.concept_id.split(":")[1])}</text></g>'
        )
    parts.append("</svg>")
    legend = (
        f'<p class="legend"><span style="background:{GREEN}"></span>mastered <span style="background:{ORANGE}"></span>review due '
        f'<span style="background:#7a8fa6"></span>learning <span style="background:#c9a227"></span>uncertain <span style="background:#fff;border:1px solid {LINE}"></span>unknown '
        f'· radius = mastery · ring thickness = uncertainty (dashed when confidence &lt; 0.35) · lines = prerequisites</p>'
    )
    return "".join(parts) + legend


def recall_curve_svg(learner, concept_id: str, now: float) -> str:
    W, H = 420, 160
    days = list(range(0, 61, 2))
    ps = [learner.predict_recall(concept_id, days_ahead=d, now=now) for d in days]
    pts = " ".join(f"{40 + d / 60 * (W - 60):.1f},{H - 30 - p * (H - 60):.1f}" for d, p in zip(days, ps, strict=True))
    due = next((d for d, p in zip(days, ps, strict=True) if p < 0.75), None)
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="recall curve" font-family="ui-sans-serif, system-ui" font-size="11">']
    parts.append(f'<line x1="40" y1="{H - 30}" x2="{W - 20}" y2="{H - 30}" stroke="{LINE}"/><line x1="40" y1="30" x2="40" y2="{H - 30}" stroke="{LINE}"/>')
    y75 = H - 30 - 0.75 * (H - 60)
    parts.append(f'<line x1="40" y1="{y75:.1f}" x2="{W - 20}" y2="{y75:.1f}" stroke="{ORANGE}" stroke-dasharray="4 4"/><text x="{W - 22}" y="{y75 - 4:.1f}" text-anchor="end" fill="{ORANGE}">review threshold 0.75</text>')
    parts.append(f'<polyline points="{pts}" fill="none" stroke="{INK}" stroke-width="2"/>')
    if due is not None:
        x = 40 + due / 60 * (W - 60)
        parts.append(f'<line x1="{x:.1f}" y1="30" x2="{x:.1f}" y2="{H - 30}" stroke="{ORANGE}"/><text x="{x + 4:.1f}" y="42" fill="{ORANGE}">review in ~{due} d</text>')
    for d in (0, 30, 60):
        parts.append(f'<text x="{40 + d / 60 * (W - 60):.1f}" y="{H - 14}" text-anchor="middle" fill="{INK_SOFT}">{d} d</text>')
    parts.append(f'<text x="8" y="34" fill="{INK_SOFT}">1.0</text><text x="8" y="{H - 30}" fill="{INK_SOFT}">0.0</text></svg>')
    return "".join(parts)


def reliability_svg(bins: list[dict]) -> str:
    W, H = 260, 260
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="reliability diagram" font-family="ui-sans-serif, system-ui" font-size="11">']
    parts.append(f'<line x1="40" y1="{H - 30}" x2="{W - 20}" y2="30" stroke="{LINE}" stroke-dasharray="4 4"/>')
    parts.append(f'<line x1="40" y1="{H - 30}" x2="{W - 20}" y2="{H - 30}" stroke="{LINE}"/><line x1="40" y1="30" x2="40" y2="{H - 30}" stroke="{LINE}"/>')
    pts = []
    for b in bins:
        if b["count"] and not math.isnan(b["mean_predicted"]):
            x = 40 + b["mean_predicted"] * (W - 60)
            y = H - 30 - b["observed"] * (H - 60)
            pts.append((x, y, b["count"]))
    for x, y, n in pts:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{3 + math.log10(max(n, 1)) * 2:.1f}" fill="{ORANGE}" fill-opacity="0.8"><title>predicted {((x - 40) / (W - 60)):.2f} · observed {((H - 30 - y) / (H - 60)):.2f} · n={n}</title></circle>')
    parts.append(f'<text x="{W / 2:.0f}" y="{H - 8}" text-anchor="middle" fill="{INK_SOFT}">mean predicted probability</text>')
    parts.append(f'<text x="12" y="{H / 2:.0f}" fill="{INK_SOFT}" transform="rotate(-90 12 {H / 2:.0f})" text-anchor="middle">observed frequency</text></svg>')
    return "".join(parts)


# ── the lab: what the runs recorded ──────────────────────────────────────


def load_runs(root: Path) -> list[dict]:
    p = root / "runs.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def benchmark_table(runs: list[dict]) -> str:
    by_model: dict[str, list[dict]] = {}
    for r in runs:
        by_model.setdefault(r["model"], []).append(r)
    rows = []
    for name, rs in by_model.items():
        aucs = [r["metrics"]["auc"] for r in rs]
        lls = [r["metrics"]["log_loss"] for r in rs]
        eces = [r["metrics"]["ece"] for r in rs]
        rows.append((name, len(rs), statistics.fmean(aucs), statistics.stdev(aucs) if len(aucs) > 1 else None, statistics.fmean(lls), statistics.fmean(eces), rs[0]["metrics"].get("parameters")))
    rows.sort(key=lambda r: -r[2])
    out = ['<table><thead><tr><th>model</th><th>seeds</th><th>AUC</th><th>log loss</th><th>ECE</th><th>parameters</th></tr></thead><tbody>']
    for name, n, auc, sd, ll, ece, params in rows:
        auc_s = f"{auc:.3f} ± {sd:.3f}" if sd is not None else f"{auc:.3f}"
        out.append(f"<tr><td>{esc(name)}</td><td>{n}</td><td>{auc_s}</td><td>{ll:.3f}</td><td>{ece:.3f}</td><td>{esc(params) if params else '—'}</td></tr>")
    out.append("</tbody></table>")
    return "".join(out)


def run_meta(runs: list[dict]) -> str:
    if not runs:
        return "<p>No runs recorded.</p>"
    r = runs[-1]
    env = r.get("environment", {})
    return (
        f"<dl><dt>dataset</dt><dd>{esc(r['dataset'])} · {esc(r['dataset_kind'])} · {esc(r['dataset_version'])}</dd>"
        f"<dt>hardware</dt><dd>{esc(env.get('platform'))} · torch {esc(env.get('torch'))} · {esc(env.get('device'))}</dd>"
        f"<dt>git</dt><dd>{esc((r.get('git') or '')[:12])}</dd>"
        f"<dt>runs</dt><dd>{len(runs)}</dd></dl>"
    )


# ── the page ─────────────────────────────────────────────────────────────

CSS = f"""
:root {{ color-scheme: light; }}
body {{ margin: 0; background: {CREAM}; color: {INK}; font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, sans-serif; }}
main {{ max-width: 980px; margin: 0 auto; padding: 48px 24px 96px; }}
h1 {{ font: 500 40px/1.05 Georgia, 'Iowan Old Style', serif; letter-spacing: -0.02em; margin: 0 0 8px; }}
h1 span {{ color: {ORANGE}; }}
h2 {{ font: 500 24px/1.2 Georgia, serif; margin: 56px 0 8px; }}
p.lead {{ color: {INK_SOFT}; max-width: 62ch; margin: 0 0 24px; }}
.rule {{ border-top: 1px solid {LINE}; margin: 40px 0; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 32px; }}
@media (max-width: 720px) {{ .grid {{ grid-template-columns: 1fr; }} }}
table {{ border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }}
th, td {{ text-align: left; padding: 8px 10px; border-top: 1px solid {LINE}; }}
th {{ font-weight: 500; color: {INK_SOFT}; font-size: 12px; text-transform: none; }}
dl {{ display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; }}
dt {{ color: {INK_SOFT}; }}
code {{ font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }}
.legend span {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin: 0 4px 0 8px; vertical-align: middle; }}
.legend {{ color: {INK_SOFT}; font-size: 12px; }}
.reason {{ display: inline-block; border: 1px solid {LINE}; border-radius: 6px; padding: 1px 8px; margin: 2px 4px 2px 0; font: 12px ui-monospace, Menlo, monospace; }}
.honest {{ border-left: 3px solid {ORANGE}; padding: 4px 16px; color: {INK_SOFT}; }}
small {{ color: {INK_SOFT}; }}
"""


def build(runs_dir: Path, out: Path) -> None:
    learner, prereq, now, events = build_learner()
    state = learner.state(now=now)
    rec = learner.recommend(now=now)
    concepts = sorted(state.concepts.values(), key=lambda c: c.concept_id)
    weakest = min((c for c in concepts if c.attempts), key=lambda c: c.recall, default=None)
    runs = load_runs(runs_dir)

    # calibration of the fallback model on the simulated population
    from aquilante.evaluation.metrics import reliability_table
    from aquilante.models.baselines import MasteryHeuristic

    train, _, test = split_by_student(synthetic_dataset(students=200, events_per_student=80, seed=5), seed=0)
    heur = MasteryHeuristic().fit(train)
    y, p = heur.predict_dataset(test)
    bins = reliability_table(y, p)

    rows = "".join(
        f"<tr><td>{esc(c.concept_id)}</td><td>{c.mastery:.2f}</td><td>{c.confidence:.2f}</td><td>{c.recall:.2f}</td><td>{c.attempts}</td><td>{c.correct}</td><td>{'' if c.days_since is None else f'{c.days_since:.1f} d'}</td></tr>"
        for c in concepts
    )
    reasons = "".join(f'<span class="reason">{esc(r)}</span>' for r in rec.reasons)
    alternatives = ", ".join(f"{a} {c or ''} ({s:.2f})" for a, c, s in rec.alternatives) or "—"

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aquilante — demo</title><style>{CSS}</style></head><body><main>
<h1>Aquilante <span>demo</span></h1>
<p class="lead">A learner's state, the action the policy recommends and why, and the benchmark as recorded. Every number on this page was computed by the library when the page was built ({time.strftime('%Y-%m-%d %H:%M')}); nothing is typed in.</p>
<p class="honest">The learner is <strong>simulated</strong> and the mastery estimates come from the fallback model (the recency heuristic), because on the synthetic benchmark the neural candidate has not beaten it. The recall curve is the half-life model fitted on a simulated population. This page shows the system working, not the model being right about people.</p>

<h2>Knowledge map</h2>
<p class="lead">{esc(state.student_id)} · {state.events} events · state as of three days after the last practice · model: <code>{esc(state.model)}</code></p>
{knowledge_map_svg(state, prereq)}

<div class="grid">
<div><h2>Next action</h2>
<p><strong>{esc(rec.action.value)}</strong> {esc(rec.concept_id or '')} <small>score {rec.score:.2f} · suggested difficulty {rec.suggested_difficulty}</small></p>
<p>{reasons}</p>
<p><small>alternatives: {esc(alternatives)}</small></p>
</div>
<div><h2>Recall of the weakest concept</h2>
<p class="lead">{esc(weakest.concept_id) if weakest else ''} · half-life {f'{weakest.half_life_days:.1f} d' if weakest and weakest.half_life_days else '—'}</p>
{recall_curve_svg(learner, weakest.concept_id, now) if weakest else ''}
</div>
</div>

<h2>State, per concept</h2>
<table><thead><tr><th>concept</th><th>mastery</th><th>confidence</th><th>recall</th><th>attempts</th><th>correct</th><th>last practised</th></tr></thead><tbody>{rows}</tbody></table>

<div class="rule"></div>
<h2>Lab</h2>
{run_meta(runs)}
<div class="grid">
<div><h2 style="margin-top:24px">Benchmark</h2>{benchmark_table(runs)}<p><small>Split by learner; metrics on held-out learners; mean ± sample sd over seeds.</small></p></div>
<div><h2 style="margin-top:24px">Calibration of the fallback model</h2>{reliability_svg(bins)}<p><small>Reliability diagram of the recency heuristic on a simulated test population; the dashed diagonal is perfect calibration; dot size grows with the bin's count.</small></p></div>
</div>
<p><small>Built by <code>scripts/build_demo.py</code> from <code>{esc(runs_dir)}</code>. Aquilante — Adaptive Neural Learner Modeling Engine, Apache-2.0.</small></p>
</main></body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    print(f"wrote {out} ({len(page) // 1024} KB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="benchmarks/runs-3seeds")
    ap.add_argument("--out", default="examples/demo/index.html")
    a = ap.parse_args()
    build(Path(a.runs), Path(a.out))
