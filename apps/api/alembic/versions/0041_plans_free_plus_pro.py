"""Three plans, Free / Plus / Pro, metered in invisible credits of real cost.

Approved 2026-10-19 (`docs/pricing/PRICING_AUDIT.md`): Free, Plus R$34,90
(R$349/year) and Pro R$69,90 (R$699/year). Student and Max stay in the enum
(no account is on them; every account is on Free) but are no longer offered.

A learner never sees a credit. What they see is "aulas completas" and "modo
padrão". Inside, 1 credit = US$0.001 of AI cost as `ai_usage` records it
(`model_prices`), so a limit holds whatever the model mix or the price list
does:

- `full_credits`: the month's lessons on the full routing (Sonnet, Opus for
  a stuck learner). Past it, lessons continue in standard mode (the economy
  tier, Haiku 5.5) instead of stopping.
- `hard_credits`: the month's ceiling, standard mode included. Past it the
  tutor waits for next month (or an upgrade).
- `daily_turns`: messages to the tutor per rolling 24 hours.
- `weekly_lessons`: lessons started per rolling 7 days (Free only).
- `monthly_documents`, `max_journeys`: PDFs per month, trails at once.

Worst case per plan (every credit spent, FX R$5,65), against net revenue
after 6% tax, 2% refunds and gateway fees (`docs/pricing/noema-unit-economics.xlsx`):

  free   220 credits    = US$0.22  = R$1,24  (budget R$1,00, ceiling R$1,50)
  plus   3,600 credits  = US$3.60  = R$20,34 vs R$30,08 net -> 32% margin
  pro    10,500 credits = US$10.50 = R$59,33 vs R$60,64 net -> 2% margin

At expected use the margins are the audit's (61-82%). One Sonnet 5.5 lesson
of 10 exchanges is about 74 credits, so Plus' 3,000 full credits are about
40 full lessons and Pro's 9,500 about 125. The audit's fair-use ceiling of
2,000 exchanges a month did not hold a margin (2,000 x 0.74 cents = R$84 on
Plus); the credit ceiling replaces it.

Revision ID: 0041
Revises: 0040
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

# plan: monthly, annual, full, hard, daily, weekly, documents, journeys, sort, active
PLANS: dict[
    str, tuple[int, int | None, int, int, int, int | None, int, int | None, int, bool]
] = {
    "free": (0, None, 150, 220, 40, 3, 3, 1, 0, True),
    "plus": (3490, 34900, 3000, 3600, 150, None, 30, None, 1, True),
    "pro": (6990, 69900, 9500, 10500, 300, None, 100, None, 2, True),
}


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE plan ADD VALUE IF NOT EXISTS 'plus' AFTER 'free'")

    op.add_column(
        "plan_configs",
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column("plan_configs", sa.Column("annual_price_cents", sa.Integer()))
    for name in ("full_credits", "hard_credits"):
        op.add_column(
            "plan_configs",
            sa.Column(name, sa.Integer(), server_default="0", nullable=False),
        )
    for name in ("daily_turns", "weekly_lessons", "monthly_documents", "max_journeys"):
        op.add_column("plan_configs", sa.Column(name, sa.Integer()))
    op.add_column(
        "plan_configs",
        sa.Column("sort", sa.Integer(), server_default="0", nullable=False),
    )

    op.execute(
        "INSERT INTO plan_configs (plan, monthly_ai_units, monthly_price_cents) "
        "VALUES ('plus', 0, 3490) ON CONFLICT (plan) DO NOTHING"
    )
    for plan, row in PLANS.items():
        monthly, annual, full, hard, daily, weekly, documents, journeys, sort, active = (
            row
        )
        op.execute(
            sa.text(
                "UPDATE plan_configs SET monthly_price_cents = :monthly, "
                "annual_price_cents = :annual, full_credits = :full, "
                "hard_credits = :hard, monthly_ai_units = :hard, "
                "daily_turns = :daily, weekly_lessons = :weekly, "
                "monthly_documents = :documents, max_journeys = :journeys, "
                "sort = :sort, active = :active, updated_at = now() "
                "WHERE plan = CAST(:plan AS plan)"
            ).bindparams(
                monthly=monthly,
                annual=annual,
                full=full,
                hard=hard,
                daily=daily,
                weekly=weekly,
                documents=documents,
                journeys=journeys,
                sort=sort,
                active=active,
                plan=plan,
            )
        )
    # Student and Max: kept for any row that names them, offered to no one.
    # Metered like Plus and Max-as-Pro so an account moved there by hand
    # still has a working limit.
    op.execute(
        "UPDATE plan_configs SET active = false, sort = 9, full_credits = 3000, "
        "hard_credits = 3600, daily_turns = 150, monthly_documents = 30 "
        "WHERE plan = 'student'"
    )
    op.execute(
        "UPDATE plan_configs SET active = false, sort = 9, full_credits = 9500, "
        "hard_credits = 10500, daily_turns = 300, monthly_documents = 100 "
        "WHERE plan = 'max'"
    )


def downgrade() -> None:
    # Postgres cannot drop an enum value; 'plus' stays in the type. Accounts
    # on it go back to Free, and the old unit limits come back.
    op.execute("UPDATE users SET plan = 'free' WHERE plan = 'plus'")
    op.execute("DELETE FROM plan_configs WHERE plan = 'plus'")
    for plan, units, price in (
        ("free", 100, 0),
        ("student", 300, 2990),
        ("pro", 600, 5990),
        ("max", 1000, 9990),
    ):
        op.execute(
            sa.text(
                "UPDATE plan_configs SET monthly_ai_units = :units, "
                "monthly_price_cents = :price WHERE plan = CAST(:plan AS plan)"
            ).bindparams(units=units, price=price, plan=plan)
        )
    for name in (
        "sort",
        "max_journeys",
        "monthly_documents",
        "weekly_lessons",
        "daily_turns",
        "hard_credits",
        "full_credits",
        "annual_price_cents",
        "active",
    ):
        op.drop_column("plan_configs", name)
