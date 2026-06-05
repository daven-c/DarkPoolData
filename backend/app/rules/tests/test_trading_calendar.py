"""Tests for the US trading-calendar helpers.

Run: pytest backend/app/rules/tests/test_trading_calendar.py
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from backend.app.services.trading_calendar import (
    US_MARKET_HOLIDAYS,
    has_trading_day_between,
    is_rth,
    is_trading_day,
    next_trading_day,
    trading_days_between,
)


_NYC = ZoneInfo("America/New_York")


def _et(year, month, day, hour, minute=0) -> float:
    """Build an epoch-seconds timestamp at a specific ET wall clock."""
    return datetime(year, month, day, hour, minute, tzinfo=_NYC).timestamp()


def test_weekday_is_trading_day():
    assert is_trading_day("2026-06-03") is True  # Wednesday
    assert is_trading_day(date(2026, 6, 3)) is True


def test_weekend_is_not_trading_day():
    assert is_trading_day("2026-06-06") is False  # Saturday
    assert is_trading_day("2026-06-07") is False  # Sunday


def test_known_holidays_are_not_trading_days():
    # July 4, 2026 falls on a Saturday → market observes Friday July 3 closed.
    assert is_trading_day("2026-07-03") is False
    assert is_trading_day("2026-01-01") is False
    assert is_trading_day("2025-07-04") is False
    assert is_trading_day("2025-12-25") is False


def test_holiday_set_is_frozen():
    # Defensive: callers shouldn't accidentally mutate the shared frozenset.
    import pytest
    with pytest.raises(AttributeError):
        US_MARKET_HOLIDAYS.add(date(2030, 1, 1))  # type: ignore[attr-defined]


def test_next_trading_day_skips_weekend():
    # Friday → next is Monday.
    assert next_trading_day("2026-06-05") == date(2026, 6, 8)


def test_next_trading_day_skips_holiday():
    # July 3 2026 is the observed July 4 holiday (Sat). Next is Mon July 6.
    assert next_trading_day("2026-07-02") == date(2026, 7, 6)


def test_has_trading_day_between_true_for_normal_range():
    assert has_trading_day_between("2026-06-01", "2026-06-05") is True


def test_has_trading_day_between_false_for_pure_weekend():
    assert has_trading_day_between("2026-06-06", "2026-06-07") is False


def test_trading_days_between_excludes_weekends_and_holidays():
    days = list(trading_days_between("2026-07-02", "2026-07-08"))
    # Thu Jul 2, Mon Jul 6, Tue Jul 7, Wed Jul 8. (Jul 3 = observed holiday, Jul 4-5 = weekend.)
    assert days == [date(2026, 7, 2), date(2026, 7, 6), date(2026, 7, 7), date(2026, 7, 8)]


def test_is_rth_within_session():
    assert is_rth(_et(2026, 6, 3, 10, 0)) is True
    assert is_rth(_et(2026, 6, 3, 9, 30)) is True   # opening bell included
    assert is_rth(_et(2026, 6, 3, 15, 59)) is True


def test_is_rth_excludes_close_bell_moment():
    # 4:00:00 PM ET is the closing bell — we treat it as not-RTH so +5m stamping
    # at 3:55 (which would target 4:00) is allowed; +5m at 3:56 targets 4:01 (not RTH).
    assert is_rth(_et(2026, 6, 3, 16, 0)) is False


def test_is_rth_excludes_pre_and_post_market():
    assert is_rth(_et(2026, 6, 3, 8, 0)) is False
    assert is_rth(_et(2026, 6, 3, 17, 0)) is False


def test_is_rth_excludes_weekends_and_holidays():
    assert is_rth(_et(2026, 6, 6, 12, 0)) is False   # Saturday noon
    assert is_rth(_et(2026, 7, 3, 12, 0)) is False   # observed July 4 holiday


def test_string_date_acceptance():
    # All helpers should accept ISO strings interchangeably with date objects.
    assert is_trading_day("2026-06-03") == is_trading_day(date(2026, 6, 3))
    assert next_trading_day("2026-06-05") == next_trading_day(date(2026, 6, 5))


def test_rth_time_constants_match_nyse():
    # Sanity check on the module-level constants.
    from backend.app.services.trading_calendar import _RTH_CLOSE, _RTH_OPEN
    assert _RTH_OPEN == time(9, 30)
    assert _RTH_CLOSE == time(16, 0)
