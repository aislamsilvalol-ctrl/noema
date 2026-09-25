"""The level curve, stages, and the day and week a learner lives in."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from itertools import pairwise

from noema.services.progression import (
    ProgressionEngine,
    level_for,
    stage_for,
    xp_for_level,
    zone,
)


def test_the_curve_climbs_and_slows() -> None:
    gaps = [xp_for_level(n + 1) - xp_for_level(n) for n in range(1, 40)]
    assert xp_for_level(1) == 0
    assert all(later >= earlier for earlier, later in pairwise(gaps))


def test_a_level_is_exactly_where_its_floor_is() -> None:
    for level in (1, 2, 7, 23):
        assert level_for(xp_for_level(level)) == level
        assert level_for(xp_for_level(level + 1) - 1) == level


def test_stages_are_places_not_ranks() -> None:
    assert [stage_for(n) for n in (1, 5, 10, 20, 35, 80)] == [
        "first_steps",
        "trail",
        "crossing",
        "altitude",
        "horizon",
        "horizon",
    ]


def test_an_unknown_time_zone_falls_back_to_utc() -> None:
    assert str(zone("Not/AZone")) == "UTC"
    assert str(zone(None)) == "UTC"


def test_the_day_and_week_follow_the_learners_clock() -> None:
    engine = ProgressionEngine(None, uuid.uuid4(), "America/Sao_Paulo")  # type: ignore[arg-type]
    # 01:30 UTC on a Monday is still Sunday evening in São Paulo.
    now = datetime(2026, 9, 28, 1, 30, tzinfo=UTC)

    start, end = engine._day_window(now)
    assert start == datetime(2026, 9, 27, 3, 0, tzinfo=UTC)
    assert end == datetime(2026, 9, 28, 3, 0, tzinfo=UTC)
    assert engine._period_key("daily", now) == "2026-09-27"
    week_start, _ = engine._week_window(now)
    assert week_start == datetime(2026, 9, 21, 3, 0, tzinfo=UTC)  # Monday, local
