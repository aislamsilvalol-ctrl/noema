# noema-api

The NOEMA backend: FastAPI service, learning engines and the AI provider layer.

Project documentation lives at the repository root — start with
[`docs/architecture.md`](../../docs/architecture.md).

```bash
uv sync --all-extras --dev
uv run alembic upgrade head
uv run uvicorn noema.main:app --reload
uv run pytest
```

The engines in `noema/engines/` are pure functions over frozen dataclasses: no database, no
network, no ambient clock. Keep them that way — it is what makes the learning model testable
and lets a user's whole review history be replayed offline when the model changes.
