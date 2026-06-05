"""US equities trading calendar helpers.

Used to (1) reject backtest requests over all-non-trading date ranges, (2) warn
users in the Stock Explorer when they pick a weekend/holiday, and (3) prevent
the forward-return stamper from writing stale closes for horizons that land
outside regular trading hours.

A small hardcoded holiday list (covering 2024–2027, the dates currently
reachable through the UI's date pickers) keeps this dependency-free. When
adding a new year, extend `US_MARKET_HOLIDAYS`. The list intentionally omits
half-days — they're rare and the stamper still produces useful prices.
"""

from datetime import date, datetime, time, timedelta
from typing import Iterable, Union
from zoneinfo import ZoneInfo


_NYC = ZoneInfo("America/New_York")
_RTH_OPEN = time(9, 30)    # 9:30 AM ET
_RTH_CLOSE = time(16, 0)   # 4:00 PM ET

# NYSE/Nasdaq full-day holidays. Source: official exchange calendars.
US_MARKET_HOLIDAYS: frozenset[date] = frozenset(
    date.fromisoformat(s) for s in (
        # 2024
        "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
        "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
        # 2025
        "2025-01-01", "2025-01-09",  # Carter mourning day
        "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26",
        "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
        # 2026
        "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
        "2026-06-19", "2026-07-03",  # July 4 falls on Saturday → observed Friday
        "2026-09-07", "2026-11-26", "2026-12-25",
        # 2027
        "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
        "2027-06-18",  # June 19 falls on Saturday → observed Friday
        "2027-07-05",  # July 4 falls on Sunday → observed Monday
        "2027-09-06", "2027-11-25", "2027-12-24",  # Dec 25 falls on Saturday → observed Friday
    )
)


def _coerce_date(d: Union[str, date, datetime]) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return date.fromisoformat(d)


def is_trading_day(d: Union[str, date, datetime]) -> bool:
    """True iff the given date is a weekday and not a recognized US market holiday."""
    day = _coerce_date(d)
    if day.weekday() >= 5:    # Sat=5, Sun=6
        return False
    return day not in US_MARKET_HOLIDAYS


def next_trading_day(d: Union[str, date, datetime]) -> date:
    """Smallest trading day strictly after `d`."""
    day = _coerce_date(d) + timedelta(days=1)
    while not is_trading_day(day):
        day += timedelta(days=1)
    return day


def trading_days_between(start: Union[str, date, datetime], end: Union[str, date, datetime]) -> Iterable[date]:
    """Yield every trading day in [start, end] inclusive (chronological order)."""
    s = _coerce_date(start)
    e = _coerce_date(end)
    cur = s
    while cur <= e:
        if is_trading_day(cur):
            yield cur
        cur += timedelta(days=1)


def has_trading_day_between(start: Union[str, date, datetime], end: Union[str, date, datetime]) -> bool:
    """True iff at least one trading day falls in [start, end]. Used for backtest validation."""
    return any(True for _ in trading_days_between(start, end))


def is_rth(ts: float) -> bool:
    """True iff the given epoch-seconds timestamp falls inside regular US trading hours.

    "RTH" here means 9:30 ET ≤ t < 16:00 ET on a trading day. Used by the
    forward-return stamper to skip horizons whose target moment lies outside
    RTH (otherwise `get_last_price()` would return a stale close).
    """
    dt = datetime.fromtimestamp(ts, tz=_NYC)
    if not is_trading_day(dt.date()):
        return False
    t = dt.time()
    return _RTH_OPEN <= t < _RTH_CLOSE
