#!/usr/bin/env python3
"""Run the Professor eval live and write the report.

Every scenario in `evals/professor_scenarios.json` is played through the real
`ProfessorEngine`, in-process, as a fresh learner on the database in
`DATABASE_URL` — use a throwaway one: this writes users, journeys and turns
and commits them. The provider chain is built the way `deps._gateway` builds
it for a request (`NOEMA_DEFAULT_PROVIDER` first, every other provider with a
key as fallback, usage written to `ai_usage`), and the tiers come from the
migration-seeded `model_tier_configs`, so a run with production's variables
routes like production.

Writes `docs/evals/professor-<date>.json` and `.md`. Stops starting new
scenarios once `--budget-usd` is spent (counted from `ai_usage`).

Usage:
    python scripts/eval_professor.py                      # everything
    python scripts/eval_professor.py --only confused tired
    python scripts/eval_professor.py --no-judge
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import uuid
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from noema.api.v1.deps import _fallback_chain, build_provider
from noema.core.config import Settings, get_settings
from noema.db.models import ModelTier, User
from noema.evals import professor as evals
from noema.professor.context import MOVE_PROMPT_VERSIONS
from noema.professor.curriculum import CURRICULUM_PROMPT_VERSION
from noema.professor.engine import ProfessorEngine
from noema.professor.moves import ROUTE_PROMPT_VERSION
from noema.providers.gateway import AIGateway
from noema.services.auth import AuthService
from noema.services.professor import tiered_gateway
from noema.services.usage import UsageWriter

ROOT = Path(__file__).resolve().parents[3]


async def gateway_for(
    db: AsyncSession, user: User, settings: Settings, meter: evals.Meter
) -> AIGateway:
    """`deps._gateway` without the request: same primary, same fallbacks."""
    primary = await build_provider(settings.noema_default_provider, settings, None)
    fallbacks = await _fallback_chain(settings.noema_default_provider, settings, None)
    return AIGateway(
        meter.instrument(primary),
        [meter.instrument(p) for p in fallbacks],
        record_usage=UsageWriter(db, user.id),
    )


async def new_user(db: AsyncSession, settings: Settings, label: str) -> User:
    user = await AuthService(db, settings).register(
        f"eval-{label}-{uuid.uuid4().hex[:6]}@example.com",
        "correct-horse-battery-staple",
        f"Eval {label}",
    )
    await db.commit()
    return user


async def play(
    maker: async_sessionmaker[AsyncSession],
    settings: Settings,
    scenario: dict[str, Any],
    defaults: dict[str, Any],
    *,
    with_judge: bool,
) -> evals.ScenarioResult:
    meter = evals.Meter()
    metered_build = meter.wrap(build_provider)
    async with maker() as db:
        user = await new_user(db, settings, scenario["id"].replace("_", "-"))
        gateway = await gateway_for(db, user, settings, meter)

        def engine_for(session: AsyncSession, learner: User) -> ProfessorEngine:
            return ProfessorEngine(
                session,
                user=learner,
                settings=settings,
                gateway=gateway,
                credentials=None,
                build_provider=metered_build,
            )

        result = await evals.run_scenario(
            db,
            user=user,
            scenario=scenario,
            engine_for=engine_for,
            meter=meter,
            defaults=defaults,
        )
        print(
            f"  {scenario['id']}: "
            + " ".join(f"{t.signal}->{t.move}" for t in result.turns)
            + f"  ${result.cost_usd:.4f}",
            flush=True,
        )
        if with_judge:
            judge_meter = evals.Meter()
            judge_gateway = await gateway_for(db, user, settings, judge_meter)
            economy = await tiered_gateway(
                ModelTier.ECONOMY,
                db=db,
                default_gateway=judge_gateway,
                build_provider=judge_meter.wrap(build_provider),
                settings=settings,
                credentials=None,
            )
            await evals.judge(economy.gateway, scenario, result, model=economy.model)
            await db.commit()
            result.judge_cost_usd = sum(c.cost_usd for c in judge_meter.take())
        return result


async def main(args: argparse.Namespace) -> int:
    settings = get_settings()
    chain = await _fallback_chain(settings.noema_default_provider, settings, None)
    args.fallbacks = ", ".join(p.name for p in chain)
    engine = create_async_engine(settings.database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    corpus = evals.load_scenarios()
    defaults = corpus.get("defaults", {})
    scenarios = [
        s for s in corpus["scenarios"] if not args.only or s["id"] in set(args.only)
    ]

    results: list[evals.ScenarioResult] = []
    spent = 0.0
    gate = asyncio.Semaphore(args.concurrency)

    async def guarded(scenario: dict[str, Any]) -> evals.ScenarioResult | None:
        nonlocal spent
        async with gate:
            if spent >= args.budget_usd:
                print(f"  {scenario['id']}: skipped, budget spent", flush=True)
                return None
            result = await play(
                maker, settings, scenario, defaults, with_judge=not args.no_judge
            )
            spent += result.cost_usd
            return result

    try:
        played = await asyncio.gather(*(guarded(s) for s in scenarios))
        results = [r for r in played if r is not None]
    finally:
        await engine.dispose()

    models = Counter(
        f"{u['provider']}/{u['model']}" for r in results for t in r.turns for u in t.usage
    )
    turns = [t for r in results for t in r.turns]
    recorded_tokens = sum(t.recorded.get("tokens", 0) for t in turns)
    metered_tokens = sum(t.tokens for t in turns)
    meta = {
        "date": args.date,
        "revision": args.revision,
        "routing": f"primary {settings.noema_default_provider}, fallbacks "
        f"{args.fallbacks or 'none'}",
        "ai_usage": f"ai_usage recorded {recorded_tokens} tokens and "
        f"${sum(t.recorded.get('cost_usd', 0.0) for t in turns):.4f} for the tutor "
        f"turns; the provider responses metered {metered_tokens} tokens",
        "judge": "economy tier, prompt eval.judge_professor "
        f"v{evals.JUDGE_PROMPT_VERSION}",
        "prompts": f"moves {MOVE_PROMPT_VERSIONS} (others v1), route "
        f"v{ROUTE_PROMPT_VERSION}, curriculum v{CURRICULUM_PROMPT_VERSION}",
        "models": ", ".join(f"{m} x{n}" for m, n in models.most_common()),
    }
    write(results, meta, args.date)
    return 0


def write(results: list[evals.ScenarioResult], meta: dict[str, Any], day: str) -> None:
    out_dir = ROOT / "docs" / "evals"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / f"professor-{day}"
    stem.with_suffix(".json").write_text(
        json.dumps(evals.as_json(results, meta), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    stem.with_suffix(".md").write_text(
        evals.render_report(results, meta), encoding="utf-8"
    )

    checks = [c for r in results for c in r.checks]
    total = sum(r.cost_usd for r in results)
    print(
        f"checks {sum(c.passed for c in checks)}/{len(checks)}; cost ${total:.4f}; "
        f"wrote {stem.with_suffix('.md').relative_to(ROOT)}"
    )


def rescore(path: Path) -> int:
    """Checks again on a stored run's replies; no database, no model."""
    data = json.loads(path.read_text(encoding="utf-8"))
    results = evals.from_json(data)
    evals.rescore(results)
    meta = dict(data["meta"])
    meta["rescored"] = "deterministic checks re-run on the stored replies"
    write(results, meta, meta["date"])
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", default=[], help="scenario ids to run")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--budget-usd", type=float, default=3.0)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument(
        "--rescore", type=Path, help="re-run the checks on a stored run's JSON"
    )
    if "--rescore" in sys.argv:
        sys.exit(rescore(parser.parse_args().rescore))
    if "DATABASE_URL" not in os.environ:
        sys.exit("eval: set DATABASE_URL to a throwaway database")
    arguments = parser.parse_args()
    arguments.revision = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    ).stdout.strip()
    sys.exit(asyncio.run(main(arguments)))
