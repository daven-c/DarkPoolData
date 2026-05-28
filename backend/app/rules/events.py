"""Core data carriers for the rule engine.

A `MarketEvent` is a single normalized (dark-pool) trade. `TickerState` holds the
rolling per-symbol state the engine mutates on every event and that metrics read.

This module is intentionally pure (no FastAPI / config imports) so it can be unit
tested and reused by both the live path and the backtest replay.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple

# A recent-trade tuple: (ts, price, size, notional, side)
RecentTrade = Tuple[float, float, int, float, str]


@dataclass
class MarketEvent:
    """One normalized trade. `side` is filled in by `TickerState.update` (tick test)."""

    symbol: str
    ts: float  # epoch seconds
    price: float
    size: int
    exchange: int
    conditions: List[int] = field(default_factory=list)
    is_dark_pool: bool = True
    side: Optional[str] = None  # "ask" | "bid", assigned during state update

    @property
    def notional(self) -> float:
        return self.price * self.size


@dataclass
class TickerState:
    """Rolling per-symbol aggregates + a bounded recent-trades window.

    Cumulative dollar totals are session-to-date. `recent` is pruned to
    `window_max_s` so windowed metrics (sweeps, short-horizon price moves) stay cheap.
    """

    symbol: str
    block_threshold: int = 10_000
    window_max_s: float = 300.0

    total_amount: float = 0.0
    at_ask: float = 0.0
    at_bid: float = 0.0
    dp_trades: int = 0
    block_trades: int = 0

    last_price: Optional[float] = None
    last_side: str = "ask"
    session_open: Optional[float] = None
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    prior_day_total: float = 0.0

    recent: Deque[RecentTrade] = field(default_factory=deque)

    def update(self, event: MarketEvent) -> None:
        """Classify side (Lee-Ready tick test), update totals, append to window."""
        lp = self.last_price
        if lp is None or event.price > lp:
            side = "ask"
        elif event.price < lp:
            side = "bid"
        else:
            side = self.last_side
        event.side = side

        notional = event.notional
        self.total_amount += notional
        self.dp_trades += 1
        if event.size >= self.block_threshold:
            self.block_trades += 1
        if side == "ask":
            self.at_ask += notional
        else:
            self.at_bid += notional

        if self.session_open is None:
            self.session_open = event.price
            self.session_high = event.price
            self.session_low = event.price
        else:
            if event.price > (self.session_high or event.price):
                self.session_high = event.price
            if event.price < (self.session_low or event.price):
                self.session_low = event.price

        self.recent.append((event.ts, event.price, event.size, notional, side))
        cutoff = event.ts - self.window_max_s
        while self.recent and self.recent[0][0] < cutoff:
            self.recent.popleft()

        self.last_price = event.price
        self.last_side = side

    @property
    def net_flow(self) -> float:
        return self.at_ask - self.at_bid

    @property
    def daily_change_pct(self) -> Optional[float]:
        if self.prior_day_total > 0:
            return (self.total_amount - self.prior_day_total) / self.prior_day_total * 100.0
        return None

    def dashboard_row(self) -> dict:
        """Snapshot shape consumed by the dashboard API."""
        return {
            "symbol": self.symbol,
            "total_amount": self.total_amount,
            "daily_change_pct": self.daily_change_pct,
            "at_ask": self.at_ask,
            "at_bid": self.at_bid,
            "net_value": self.net_flow,
            "dp_trades": self.dp_trades,
            "block_trades": self.block_trades,
        }
