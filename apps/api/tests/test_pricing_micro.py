"""Integer micro-cents, without a database.

The rate arithmetic used to live only inside ``PricingService.cost_cents``.
The integer form is the one new rows store; the float is derived from it.
"""

from __future__ import annotations

from noema.services.pricing import cents_from_micro_cents, micro_cents_for_tokens


def test_micro_cents_match_the_list_price_example() -> None:
    # 800k fresh * $2.00 + 200k cached * $0.50 + 500k out * $8.00 = $5.70.
    micro = micro_cents_for_tokens(
        fresh_tokens=800_000,
        cached_tokens=200_000,
        completion_tokens=500_000,
        input_usd_per_million=2.0,
        cached_usd_per_million=0.5,
        output_usd_per_million=8.0,
    )

    assert isinstance(micro, int)
    assert micro == 570_000_000
    assert cents_from_micro_cents(micro) == 570.0


def test_a_fractional_cent_stays_an_integer() -> None:
    # One token at $0.40 / million tokens is 40 micro-cents, not a float of cents.
    micro = micro_cents_for_tokens(
        fresh_tokens=1,
        cached_tokens=0,
        completion_tokens=0,
        input_usd_per_million=0.40,
        cached_usd_per_million=0.0,
        output_usd_per_million=0.0,
    )

    assert micro == 40
    assert cents_from_micro_cents(micro) == 4e-5
