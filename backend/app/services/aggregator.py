import asyncio
import threading
from typing import AsyncIterator, Dict, List, Optional, Tuple

from backend.app.core.config import settings


class DashboardAggregator:
    """In-memory running totals for the dashboard universe.

    Trade-condition bid/ask heuristic uses the Lee-Ready tick test:
    uptick -> at_ask, downtick -> at_bid, equal -> retain prior side.

    Thread-safe for the WS callback thread; subscriber fan-out is bound
    to the asyncio loop that called `subscribe()`.
    """

    def __init__(self, universe: List[str]):
        self._universe = set(universe)
        self._stats: Dict[str, Dict[str, float]] = {
            t: {
                "total_amount": 0.0,
                "at_ask": 0.0,
                "at_bid": 0.0,
                "dp_trades": 0,
                "block_trades": 0,
            }
            for t in universe
        }
        self._last_price: Dict[str, float] = {}
        self._last_side: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._subscribers: List[Tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []

    @property
    def universe(self) -> List[str]:
        return sorted(self._universe)

    def reset(self) -> None:
        """Zero out all running totals. Call at session rollover."""
        with self._lock:
            for stats in self._stats.values():
                stats["total_amount"] = 0.0
                stats["at_ask"] = 0.0
                stats["at_bid"] = 0.0
                stats["dp_trades"] = 0
                stats["block_trades"] = 0
            self._last_price.clear()
            self._last_side.clear()

    def apply_trade(self, symbol: str, price: float, size: int, exchange: int) -> None:
        if symbol not in self._stats:
            return
        if exchange != settings.DASHBOARD_TRF_EXCHANGE_ID:
            return
        value = price * size
        with self._lock:
            stats = self._stats[symbol]
            stats["total_amount"] += value
            stats["dp_trades"] += 1
            if size >= settings.DASHBOARD_BLOCK_SIZE_THRESHOLD:
                stats["block_trades"] += 1

            last = self._last_price.get(symbol)
            if last is None or price > last:
                side = "ask"
            elif price < last:
                side = "bid"
            else:
                side = self._last_side.get(symbol, "ask")

            if side == "ask":
                stats["at_ask"] += value
            else:
                stats["at_bid"] += value

            self._last_price[symbol] = price
            self._last_side[symbol] = side
            snapshot_row = {"symbol": symbol, **stats}

        self._notify(snapshot_row)

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        with self._lock:
            return {sym: dict(stats) for sym, stats in self._stats.items()}

    def row(self, symbol: str) -> Optional[Dict[str, float]]:
        with self._lock:
            stats = self._stats.get(symbol)
            return dict(stats) if stats is not None else None

    def _notify(self, row: Dict[str, float]) -> None:
        for loop, q in list(self._subscribers):
            loop.call_soon_threadsafe(self._safe_put, q, row)

    @staticmethod
    def _safe_put(q: asyncio.Queue, item: Dict[str, float]) -> None:
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            pass

    async def subscribe(self) -> AsyncIterator[Dict[str, float]]:
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=settings.DASHBOARD_SSE_QUEUE_MAX)
        entry = (loop, q)
        self._subscribers.append(entry)
        try:
            while True:
                yield await q.get()
        finally:
            self._subscribers.remove(entry)
