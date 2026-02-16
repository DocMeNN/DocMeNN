# accounting/services/period_lock.py

"""
======================================================
PATH: accounting/services/period_lock.py
======================================================
PERIOD LOCK GUARD

Purpose:
- Enforce accounting period locks globally.
- Prevent posting ANY journal entry whose posted_at date
  falls within a closed period for the chart being posted to.

Design:
- Thin, reusable guard
- Called by journal_entry_service (engine choke-point)
- Accepts chart explicitly (never guesses chart incorrectly)
"""

from __future__ import annotations

from datetime import datetime, date

from django.utils import timezone

from accounting.models.period_close import PeriodClose


class PeriodLockedError(ValueError):
    """Raised when attempting to post into a closed accounting period."""


def _to_date(dt: datetime | date | None) -> date | None:
    if dt is None:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt
    if isinstance(dt, datetime):
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt.date()
    return None


def assert_period_open(*, chart, posted_at: datetime | date | None) -> None:
    """
    Assert that posted_at does NOT fall inside a closed period for the given chart.

    Usage:
        assert_period_open(chart=chart, posted_at=posted_at)

    Raises:
        PeriodLockedError if the date is locked.
    """
    post_date = _to_date(posted_at)
    if post_date is None:
        return

    locked = PeriodClose.objects.filter(
        chart=chart,
        start_date__lte=post_date,
        end_date__gte=post_date,
    ).exists()

    if locked:
        raise PeriodLockedError(
            f"Posting blocked: {post_date} falls inside a closed period for this chart."
        )
