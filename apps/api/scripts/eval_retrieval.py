#!/usr/bin/env python3
"""Run the retrieval eval against a real database and print what it scored.

`tests/test_db_evals.py` only ever tells you whether recall@k and the refusal
rate cleared their floor — a passing run prints nothing, by design, so an
unrelated change doesn't turn every CI log into a wall of eval output. That
also means nobody sees the actual numbers unless the floor breaks: no way to
watch a trend, or to tell "just barely above the floor" from "nowhere near it."
This is that second half — the report `noema.evals.run` already builds, printed
on purpose instead of only on failure.

Runs inside a transaction that is always rolled back, the same as the test
fixture's `db` — nothing this writes reaches the real database.

Usage:
    uv run python scripts/eval_retrieval.py
    uv run python scripts/eval_retrieval.py --provider ollama --model nomic-embed-text
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import os
import sys
import uuid

os.environ.setdefault("NOEMA_MASTER_KEY", base64.b64encode(b"0" * 32).decode())
os.environ.setdefault("NOEMA_SESSION_SECRET", base64.b64encode(b"1" * 32).decode())

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from noema.api.v1.deps import build_provider
from noema.core.config import get_settings
from noema.evals import run
from noema.providers.gateway import AIGateway
from noema.services.auth import AuthService


async def main(provider_name: str, model: str | None) -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        connection = await engine.connect()
    except Exception as exc:
        print(f"eval: database unreachable: {exc}", file=sys.stderr)
        await engine.dispose()
        return 2

    transaction = await connection.begin()
    session = AsyncSession(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        user = await AuthService(session, settings).register(
            f"eval-{uuid.uuid4().hex[:8]}@example.com", "correct-horse-battery", "Eval"
        )
        provider = await build_provider(provider_name, settings, credentials=None)
        gateway = AIGateway(provider)

        report = await run(
            session, owner_id=user.id, gateway=gateway, embedding_model=model
        )
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()

    print(f"provider:      {provider_name}{f' ({model})' if model else ''}")
    print(
        f"recall@k:      {report.recall_at_k:.0%} "
        f"({report.answerable} answerable queries)"
    )
    print(
        f"refusal rate:  {report.refusal_rate:.0%} "
        f"({report.unanswerable} unanswerable queries)"
    )
    if report.missed:
        print("missed (should have answered):")
        for query in report.missed:
            print(f"  - {query}")
    if report.false_answers:
        print("answered anyway (should have refused):")
        for query in report.false_answers:
            print(f"  - {query}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider", default="mock", help="embedding provider name (default: mock)"
    )
    parser.add_argument(
        "--model", default=None, help="embedding model, if the provider needs one"
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.provider, args.model)))
