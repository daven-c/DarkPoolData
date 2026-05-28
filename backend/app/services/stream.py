import threading
from typing import List, Optional

from massive import WebSocketClient
from massive.websocket.models import Feed, Market

from backend.app.core.config import settings
from backend.app.services.aggregator import DashboardAggregator


_FEED_MAP = {
    "realtime": Feed.RealTime,
    "delayed": Feed.Delayed,
}


class DashboardStreamer:
    """Owns the Massive WebSocket connection in a background daemon thread
    and routes incoming TRF trades into the aggregator.
    """

    def __init__(self, api_key: str, universe: List[str], aggregator: DashboardAggregator):
        self.api_key = api_key
        self.universe = universe
        self.aggregator = aggregator
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
            self.aggregator.apply_trade(symbol, float(price), int(size), int(exchange))

    def stop(self) -> None:
        # WebSocketClient.close() is an async coroutine that needs the WS internal loop,
        # so we cannot safely await it from here. The thread is daemon=True; it will be
        # torn down with the process. Setting the flag is enough for any cooperative checks.
        self._stopped.set()
