"""Korean equity market calendar and session contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class SessionWindow:
    """Named market session window in Korean local time."""

    name: str
    start: time
    end: time

    def contains(self, value: time) -> bool:
        """Return whether *value* is inside the session."""
        return self.start <= value < self.end


KRX_EQUITY_SESSIONS: tuple[SessionWindow, ...] = (
    SessionWindow("pre_hours", time(8, 0), time(9, 0)),
    SessionWindow("regular", time(9, 0), time(15, 30)),
    SessionWindow("post_hours", time(15, 40), time(18, 0)),
)

NXT_EQUITY_SESSIONS: tuple[SessionWindow, ...] = (
    SessionWindow("pre_market", time(8, 0), time(8, 50)),
    SessionWindow("after_market", time(15, 30), time(20, 0)),
)


class KoreanTradingCalendar:
    """KRX/NXT trading-day calendar backed by user-supplied holiday dates.

    The built-in rules model the stable official closure categories: weekends,
    Labor Day, government/extra holidays supplied by the caller, and the KRX
    year-end closure on Dec. 31 or the nearest previous business day.
    """

    def __init__(
        self,
        *,
        holidays: Iterable[date | str | pd.Timestamp] = (),
        extra_closed_days: Iterable[date | str | pd.Timestamp] = (),
    ) -> None:
        self.holidays = {_to_date(value) for value in holidays}
        self.extra_closed_days = {_to_date(value) for value in extra_closed_days}

    def is_trading_day(self, value: date | str | pd.Timestamp) -> bool:
        """Return whether *value* is an open Korean equity trading day."""
        day = _to_date(value)
        if day.weekday() >= 5:
            return False
        if day in self.holidays or day in self.extra_closed_days:
            return False
        if day.month == 5 and day.day == 1:
            return False
        if day == self.year_end_closure(day.year):
            return False
        return True

    def add_trading_days(self, value: date | str | pd.Timestamp, days: int) -> pd.Timestamp:
        """Return the date reached after *days* open trading days."""
        if days <= 0:
            return pd.Timestamp(_to_date(value))

        current = _to_date(value)
        remaining = days
        while remaining > 0:
            current += timedelta(days=1)
            if self.is_trading_day(current):
                remaining -= 1
        return pd.Timestamp(current)

    def session_for(self, value: str | pd.Timestamp | datetime, *, venue: str = "krx") -> str | None:
        """Return the Korean equity session name for *value*, or None if closed."""
        ts = pd.Timestamp(value)
        if not self.is_trading_day(ts):
            return None

        windows = KRX_EQUITY_SESSIONS if venue.lower() == "krx" else NXT_EQUITY_SESSIONS
        local_time = ts.time()
        for window in windows:
            if window.contains(local_time):
                return window.name
        return None

    def year_end_closure(self, year: int) -> date:
        """Return the KRX year-end closure day for *year*."""
        current = date(year, 12, 31)
        while current.weekday() >= 5 or current in self.holidays or current in self.extra_closed_days:
            current -= timedelta(days=1)
        return current


def _to_date(value: date | str | pd.Timestamp) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()
