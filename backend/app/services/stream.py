import random
import threading
import time
from typing import List, Optional

from massive import WebSocketClient
from massive.websocket.models import Feed, Market

from backend.app.core.config import settings
from backend.app.rules.engine import RuleEngine
from backend.app.rules.events import MarketEvent


_FEED_MAP = {
    "realtime": Feed.RealTime,
    "delayed": Feed.Delayed,
}


class DashboardStreamer:
    """Owns the Massive WebSocket connection in a background daemon thread.

    Each incoming TRF (dark-pool) trade is converted to a MarketEvent and fed
    into RuleEngine.process(), which updates TickerState and evaluates rules.
    The engine's SSE fan-out notifies dashboard subscribers automatically.
    Non-TRF trades (exchange != DASHBOARD_TRF_EXCHANGE_ID) are dropped.
    """

    def __init__(
        self,
        api_key: str,
        universe: List[str],
        engine: RuleEngine,
        alert_callback=None,
    ):
        self.api_key = api_key
        self.universe = universe
        self.engine = engine
        # Optional callback for Phase 3: alert_callback(List[Signal]) -> None
        self.alert_callback = alert_callback
        self._client: Optional[WebSocketClient] = None
        self._thread: Optional[threading.Thread] = None
        self._stopped = threading.Event()
        self._got_first = False

    def start(self) -> None:
        if self._thread is not None:
            return
        subscriptions = [f"T.{t}" for t in self.universe]
        feed = _FEED_MAP.get(settings.DASHBOARD_WS_FEED.lower(), Feed.Delayed)
        self._client = WebSocketClient(
            api_key=self.api_key,
            market=Market.Stocks,
            feed=feed,
            subscriptions=subscriptions,
        )
        self._thread = threading.Thread(target=self._run, name="dashboard-ws", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        print(f"[DashboardStreamer] connecting WS for {len(self.universe)} tickers", flush=True)
        try:
            self._client.run(self._handle_messages)
        except Exception as e:
            print(f"[DashboardStreamer] WS terminated: {e}", flush=True)

    def _handle_messages(self, messages) -> None:
        if not self._got_first:
            self._got_first = True
            print(f"[DashboardStreamer] first WS batch received ({len(messages)} msgs)", flush=True)
        for m in messages:
            if getattr(m, "event_type", None) != "T":
                continue
            symbol = getattr(m, "symbol", None)
            price = getattr(m, "price", None)
            size = getattr(m, "size", None)
            exchange = getattr(m, "exchange", None)
            if symbol is None or price is None or size is None or exchange is None:
                continue
            # Only process dark-pool (TRF) trades
            if int(exchange) != settings.DASHBOARD_TRF_EXCHANGE_ID:
                continue

            # Convert WS timestamp to epoch seconds
            ts_raw = getattr(m, "sip_timestamp", None) or getattr(m, "timestamp", None)
            if ts_raw is None:
                ts = time.time()
            elif ts_raw > 1_000_000_000_000:  # nanoseconds
                ts = ts_raw / 1_000_000_000.0
            else:  # milliseconds
                ts = ts_raw / 1_000.0

            event = MarketEvent(
                symbol=symbol,
                ts=ts,
                price=float(price),
                size=int(size),
                exchange=int(exchange),
            )
            signals = self.engine.process(event)
            if signals and self.alert_callback is not None:
                self.alert_callback(signals)

    def stop(self) -> None:
        # WebSocketClient.close() is an async coroutine that needs the WS internal loop,
        # so we cannot safely await it from here. The thread is daemon=True; it will be
        # torn down with the process. Setting the flag is enough for any cooperative checks.
        self._stopped.set()


class MockStreamer:
    """Synthetic-tape driver for off-hours testing — drop-in for DashboardStreamer.

    Generates a random-walk price series per ticker plus occasional block trades,
    wraps each tick in a MarketEvent on the TRF exchange, and feeds it through
    RuleEngine.process() exactly like the live streamer. Useful when the market is
    closed (or no API key is configured) so the full ingestion → condition-matching
    → alert pipeline can be exercised end-to-end.

    Seeded with a fixed RNG so behavior is reproducible in tests. The background
    thread is optional: call step() directly to advance one trade deterministically.
    """

    # Sensible default if the caller passes an empty universe.
    DEFAULT_UNIVERSE = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN", "META", "GOOGL", "AMD", "NFLX", "SPY"]

    def __init__(
        self,
        universe: List[str],
        engine: RuleEngine,
        alert_callback=None,
        rate_per_sec: float = 20.0,
        block_prob: float = 0.10,
        seed: Optional[int] = None,
    ):
        self.universe = list(universe) if universe else list(self.DEFAULT_UNIVERSE)
        self.engine = engine
        self.alert_callback = alert_callback
        self.rate_per_sec = max(0.1, rate_per_sec)
        self.block_prob = block_prob
        self._rng = random.Random(seed)
        self._prices = {sym: self._rng.uniform(50.0, 350.0) for sym in self.universe}
        self._thread: Optional[threading.Thread] = None
        self._stopped = threading.Event()

    def _next_event(self) -> MarketEvent:
        """Build one synthetic TRF trade, advancing that ticker's random walk."""
        symbol = self._rng.choice(self.universe)
        drift = self._rng.uniform(-0.0015, 0.0015)
        self._prices[symbol] = max(1.0, self._prices[symbol] * (1.0 + drift))
        if self._rng.random() < self.block_prob:
            size = self._rng.randint(10_000, 35_000)   # block-sized
        else:
            size = self._rng.randint(10, 5_000)
        return MarketEvent(
            symbol=symbol,
            ts=time.time(),
            price=round(self._prices[symbol], 2),
            size=size,
            exchange=settings.DASHBOARD_TRF_EXCHANGE_ID,
        )

    def step(self):
        """Generate and process exactly one synthetic trade; return fired signals.

        Exposed so tests (and CI) can drive the engine deterministically without
        the background thread or any sleep.
        """
        event = self._next_event()
        signals = self.engine.process(event)
        if signals and self.alert_callback is not None:
            self.alert_callback(signals)
        return signals

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="mock-streamer", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        print(
            f"[MockStreamer] SIMULATING ~{self.rate_per_sec:.0f} trades/sec across "
            f"{len(self.universe)} tickers — THIS IS NOT LIVE DATA",
            flush=True,
        )
        mean_delay = 1.0 / self.rate_per_sec
        while not self._stopped.is_set():
            self.step()
            # Jitter ±50% around the mean delay so the rate varies naturally.
            time.sleep(self._rng.uniform(mean_delay * 0.5, mean_delay * 1.5))

    def stop(self) -> None:
        self._stopped.set()
