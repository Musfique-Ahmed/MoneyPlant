"""Period primitives and month arithmetic."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.finance.periods import (
    MonthlyPeriod,
    months_between,
    shift_months,
)


def test_from_year_month_first_of_month_to_first_of_next() -> None:
    p = MonthlyPeriod.from_year_month(2026, 1)
    assert p.start == date(2026, 1, 1)
    assert p.end_exclusive == date(2026, 2, 1)
    assert p.label() == "2026-01"


def test_from_year_month_december_rolls_to_next_year() -> None:
    p = MonthlyPeriod.from_year_month(2026, 12)
    assert p.start == date(2026, 12, 1)
    assert p.end_exclusive == date(2027, 1, 1)


def test_contains_is_half_open() -> None:
    p = MonthlyPeriod.from_year_month(2026, 3)
    assert p.contains(date(2026, 3, 1))   # first day is in period
    assert p.contains(date(2026, 3, 31))  # last day is in period
    assert not p.contains(date(2026, 4, 1))  # end_exclusive is the next period's
    assert not p.contains(date(2026, 2, 28))


def test_previous_next_isomorphism() -> None:
    p = MonthlyPeriod.from_year_month(2026, 6)
    assert p.next().start == date(2026, 7, 1)
    assert p.next().end_exclusive == date(2026, 8, 1)
    assert p.next().previous() == p


def test_previous_rolls_back_year() -> None:
    p = MonthlyPeriod.from_year_month(2026, 1)
    assert p.previous().start == date(2025, 12, 1)


def test_containing_finds_month_for_an_arbirary_date() -> None:
    p = MonthlyPeriod.containing(date(2026, 7, 15))
    assert p.start == date(2026, 7, 1)
    assert p.end_exclusive == date(2026, 8, 1)


def test_shift_months_within_year() -> None:
    assert shift_months(date(2026, 3, 15), 2) == date(2026, 5, 15)
    assert shift_months(date(2026, 3, 15), -1) == date(2026, 2, 15)


def test_shift_months_year_boundary() -> None:
    assert shift_months(date(2026, 11, 10), 3) == date(2027, 2, 10)
    assert shift_months(date(2026, 1, 31), -1) == date(2025, 12, 31)


def test_shift_months_clamps_day_to_month_end() -> None:
    # Jan 31 + 1 month → Feb has no 31, clamp to Feb 28.
    assert shift_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    # Leap-year rule: 2024 has Feb 29.
    assert shift_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_months_between_counts_full_months() -> None:
    assert months_between(date(2026, 1, 1), date(2026, 4, 1)) == 3
    assert months_between(date(2026, 1, 15), date(2026, 4, 14)) == 2  # not yet 3 full months
    assert months_between(date(2026, 4, 1), date(2026, 1, 1)) == -3
