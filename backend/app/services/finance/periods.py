"""Period primitives.

The engine is monthly by default. A :class:`MonthlyPeriod` represents a
half-open interval ``[start, end_exclusive)`` where ``end_exclusive`` is
the first day of the next month. Cash flows on ``end_exclusive`` belong to
the next period; on any day before, they belong to this period.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class MonthlyPeriod:
    start: date
    end_exclusive: date

    @classmethod
    def from_year_month(cls, year: int, month: int) -> "MonthlyPeriod":
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1)
        else:
            end = date(year, month + 1, 1)
        return cls(start=start, end_exclusive=end)

    @classmethod
    def containing(cls, when: date) -> "MonthlyPeriod":
        return cls.from_year_month(when.year, when.month)

    def contains(self, when: date) -> bool:
        return self.start <= when < self.end_exclusive

    def previous(self) -> "MonthlyPeriod":
        if self.start.month == 1:
            return MonthlyPeriod.from_year_month(self.start.year - 1, 12)
        return MonthlyPeriod.from_year_month(self.start.year, self.start.month - 1)

    def next(self) -> "MonthlyPeriod":
        return MonthlyPeriod(start=self.end_exclusive, end_exclusive=_add_month(self.end_exclusive))

    def label(self) -> str:
        return f"{self.start.year}-{self.start.month:02d}"


def _add_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def shift_months(start: date, months: int) -> date:
    """Add ``months`` (may be negative) to a date, clamping the day to the month's length."""
    total = start.year * 12 + (start.month - 1) + months
    new_year, new_month0 = divmod(total, 12)
    new_month = new_month0 + 1
    # Clamp day to last valid day of new month.
    if new_month == 12:
        next_month = date(new_year + 1, 1, 1)
    else:
        next_month = date(new_year, new_month + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return date(new_year, new_month, min(start.day, last_day))


def months_between(a: date, b: date) -> int:
    """Whole months from ``a`` to ``b`` (positive when ``b`` is later)."""
    if b < a:
        return -months_between(b, a)
    months = (b.year - a.year) * 12 + (b.month - a.month)
    if b.day < a.day:
        months -= 1
    return months


__all__ = ["MonthlyPeriod", "shift_months", "months_between"]