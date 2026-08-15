"""Rules about migrations that a from-scratch upgrade cannot check.

CI applies every migration to an empty database in one process. A real
deployment does not: it arrives already at some revision and applies only what
is new, in a fresh process. The two differ in a way that has bitten this project
once already, so the difference is written down here as tests rather than left to
be rediscovered.

The specific trap: SQLAlchemy remembers, on the object driving the DDL, which
enum types it has created during *this* run, and skips creating them again. From
scratch, migration 0004 creates ``grader`` and migration 0007 quietly reuses that
memo. Upgrading 0006 → 0007 on its own starts with an empty memo, issues
``CREATE TYPE grader`` for real, and dies. Nothing about the migration looks
wrong; it simply passed for a reason that does not hold in production.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def migrations() -> list[Path]:
    found = sorted(VERSIONS.glob("[0-9]*.py"))
    assert found, "no migrations found — this test would pass vacuously"
    return found


@pytest.mark.parametrize("path", migrations(), ids=lambda p: p.stem)
def test_create_type_is_not_passed_to_sa_enum(path: Path) -> None:
    """``sa.Enum`` accepts ``create_type`` and throws it away.

    Only ``postgresql.ENUM`` honours it. Passing it to ``sa.Enum`` reads as "do
    not create this type" and means the opposite, with no error to say so — the
    worst kind of wrong, because the code documents an intention it does not
    have.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not any(kw.arg == "create_type" for kw in node.keywords):
            continue

        called = ast.unparse(node.func)
        assert not called.endswith("sa.Enum"), (
            f"{path.name}:{node.lineno} passes create_type to {called}, which "
            "discards it. Use postgresql.ENUM(..., create_type=False) to "
            "reference a type an earlier migration already created."
        )
