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
