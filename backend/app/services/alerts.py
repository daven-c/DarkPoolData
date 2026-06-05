"""AlertDispatcher — fans Signal objects to SSE, Discord, and SQLite.

Design
------
- `enqueue(signals)` is thread-safe: can be called from the WS daemon thread.
- A background asyncio `_drain` task processes the queue and hits each sink.
- SSE subscribers get every signal as JSON.
- Discord is best-effort (errors are silenced so the live path stays clean).
- SQLite rows are written synchronously via threading.Lock (tiny writes, fine).

Forward-return stamper
---------------------
`forward_return_stamper(store, massive, horizons_min)` is an async task started
from the lifespan. Every 60 s it queries for unstamped rows whose horizon has
elapsed and patches in the realised return. Intraday horizons use the current
last-trade price; the +1d horizon uses the daily close of the target date.
"""

import asyncio
import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, List, Optional, Tuple

from backend.app.core.config import settings
from backend.app.rules.rule import Signal
from backend.app.services.discord import DiscordNotifier
from backend.app.services.trading_calendar import is_rth

# ---------------------------------------------------------------------------
# SQLite schema
# ---------------------------------------------------------------------------
DB_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
)
DB_PATH = os.path.join(DB_DIR, "alerts.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id          TEXT PRIMARY KEY,
    rule_id     TEXT NOT NULL,
    rule_name   TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    ts          REAL NOT NULL,       -- epoch seconds (signal fired)
    side_label  TEXT,                -- 'bull' | 'bear' | NULL (neutral)
    kind        TEXT NOT NULL,
    price       REAL NOT NULL,
    message     TEXT NOT NULL,
    metadata    TEXT NOT NULL,       -- JSON blob
    forward_5m  REAL,               -- % return after 5 min  (NULL until stamped)
    forward_30m REAL,               -- % return after 30 min (NULL until stamped)
    forward_1d  REAL,               -- % return after 1 day  (NULL until stamped)
    stamped_at  REAL                -- epoch seconds when all horizons resolved
);
CREATE INDEX IF NOT EXISTS alerts_symbol ON alerts(symbol);
CREATE INDEX IF NOT EXISTS alerts_ts ON alerts(ts DESC);
CREATE INDEX IF NOT EXISTS alerts_rule ON alerts(rule_id);
"""


# ---------------------------------------------------------------------------
# AlertStore
# ---------------------------------------------------------------------------

class AlertStore:
    """Thin SQLite wrapper for alert persistence."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        os.makedirs(DB_DIR, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Drop the deprecated `severity` column from pre-existing DBs."""
        cols = {r[1] for r in conn.execute("PRAGMA table_info(alerts)").fetchall()}
        if "severity" in cols:
            conn.execute("ALTER TABLE alerts DROP COLUMN severity")

    @contextmanager
    def _connect(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def insert(self, signal: Signal) -> str:
        alert_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO alerts
                   (id, rule_id, rule_name, symbol, ts, side_label,
                    kind, price, message, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    alert_id,
                    signal.rule_id,
                    signal.rule_name,
                    signal.symbol,
                    signal.ts,
                    signal.side_label,
                    signal.kind,
                    signal.price,
                    signal.message,
                    json.dumps(signal.metadata),
                ),
            )
        return alert_id

    def get_recent(self, limit: int = 100) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM alerts ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_history(
        self,
        symbol: Optional[str] = None,
        rule_name: Optional[str] = None,
        limit: int = 500,
    ) -> List[dict]:
        clauses, params = [], []
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if rule_name:
            clauses.append("rule_name = ?")
            params.append(rule_name)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM alerts {where} ORDER BY ts DESC LIMIT ?", params
            ).fetchall()
        return [dict(r) for r in rows]

    # Earliest plausible signal timestamp: 2020-01-01 00:00:00 UTC.
    # Rows with ts below this are test/dev artefacts with bogus epoch values (e.g. ts=0).
    _MIN_VALID_TS: float = 1_577_836_800.0

    def get_unstamped(self, horizon_col: str, before_ts: float, limit: int = 200) -> List[dict]:
        """Rows whose horizon has elapsed but hasn't been stamped yet.

        Only returns rows with a plausible timestamp (>= 2020-01-01).  Rows
        with ts=0 or other dev/test artefacts are silently excluded so the
        stamper never requests data for 1970.
        """
        valid = {"forward_5m", "forward_30m", "forward_1d"}
        if horizon_col not in valid:
            raise ValueError(f"invalid horizon_col: {horizon_col}")
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT id, symbol, ts, price FROM alerts "
                f"WHERE {horizon_col} IS NULL AND ts >= ? AND ts <= ? LIMIT ?",
                (self._MIN_VALID_TS, before_ts, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def purge_invalid_timestamps(self) -> int:
        """Delete rows whose ts is before _MIN_VALID_TS (test/dev artefacts).
        Returns the number of rows deleted.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM alerts WHERE ts < ?", (self._MIN_VALID_TS,)
            )
        return cur.rowcount

    @staticmethod
    def _start_of_day_ts() -> float:
        """Epoch seconds for 00:00:00 UTC of the current day."""
        now = datetime.now(tz=timezone.utc)
        sod = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return sod.timestamp()

    def rule_stats(self, since_ts: Optional[float] = None) -> List[dict]:
        """Per-rule aggregate stats over the alerts table.

        One row per (rule_id, rule_name) seen in the table. For each rule:
        signal_count, signals_today, last_ts, and for each forward horizon
        column the number of stamped rows, hit-rate (% of positive returns)
        and average return.

        Only rows with a plausible timestamp (>= _MIN_VALID_TS) are counted so
        test/dev artefacts never skew the numbers. `since_ts` optionally
        narrows the window further (e.g. trailing 30 days).
        """
        sod = self._start_of_day_ts()
        clauses = ["ts >= ?"]
        params: list = [self._MIN_VALID_TS]
        if since_ts is not None:
            clauses.append("ts >= ?")
            params.append(since_ts)
        where = f"WHERE {' AND '.join(clauses)}"

        # signals_today uses a fixed bind param (start-of-day) before the WHERE params.
        sql = f"""
            SELECT
                rule_id,
                rule_name,
                COUNT(*)                                        AS signal_count,
                SUM(CASE WHEN ts >= ? THEN 1 ELSE 0 END)        AS signals_today,
                MAX(ts)                                         AS last_ts,

                COUNT(forward_5m)                               AS stamped_5m,
                SUM(CASE WHEN forward_5m > 0 THEN 1 ELSE 0 END) AS hits_5m,
                AVG(forward_5m)                                 AS avg_5m,

                COUNT(forward_30m)                              AS stamped_30m,
                SUM(CASE WHEN forward_30m > 0 THEN 1 ELSE 0 END) AS hits_30m,
                AVG(forward_30m)                                AS avg_30m,

                COUNT(forward_1d)                               AS stamped_1d,
                SUM(CASE WHEN forward_1d > 0 THEN 1 ELSE 0 END) AS hits_1d,
                AVG(forward_1d)                                 AS avg_1d
            FROM alerts
            {where}
            GROUP BY rule_id, rule_name
            ORDER BY signal_count DESC
        """
        with self._connect() as conn:
            rows = conn.execute(sql, (sod, *params)).fetchall()

        def _horizon(stamped, hits, avg) -> dict:
            stamped = stamped or 0
            return {
                "stamped": stamped,
                "hit_rate": (hits / stamped * 100.0) if stamped else None,
                "avg_return": avg,
            }

        out = []
        for r in rows:
            out.append(
                {
                    "rule_id": r["rule_id"],
                    "rule_name": r["rule_name"],
                    "signal_count": r["signal_count"] or 0,
                    "signals_today": r["signals_today"] or 0,
                    "last_ts": r["last_ts"],
                    "horizons": {
                        "5m": _horizon(r["stamped_5m"], r["hits_5m"], r["avg_5m"]),
                        "30m": _horizon(r["stamped_30m"], r["hits_30m"], r["avg_30m"]),
                        "1d": _horizon(r["stamped_1d"], r["hits_1d"], r["avg_1d"]),
                    },
                }
            )
        return out

    def health(self) -> dict:
        """Cheap aggregate counters for the engine-health strip."""
        sod = self._start_of_day_ts()
        with self._connect() as conn:
            row = conn.execute(
                """SELECT
                       COUNT(*)                                  AS total_signals,
                       SUM(CASE WHEN ts >= ? THEN 1 ELSE 0 END)  AS signals_today,
                       MAX(ts)                                   AS last_signal_ts
                   FROM alerts
                   WHERE ts >= ?""",
                (sod, self._MIN_VALID_TS),
            ).fetchone()
        return {
            "total_signals": row["total_signals"] or 0,
            "signals_today": row["signals_today"] or 0,
            "last_signal_ts": row["last_signal_ts"],
        }

    def stamp_horizon(self, alert_id: str, horizon_col: str, return_pct: float) -> None:
        valid = {"forward_5m", "forward_30m", "forward_1d"}
        if horizon_col not in valid:
            raise ValueError(f"invalid horizon_col: {horizon_col}")
        with self._connect() as conn:
            conn.execute(
                f"UPDATE alerts SET {horizon_col} = ? WHERE id = ?",
                (return_pct, alert_id),
            )
            # Mark stamped_at when all three horizons are resolved
            conn.execute(
                """UPDATE alerts SET stamped_at = ?
                   WHERE id = ? AND forward_5m IS NOT NULL
                     AND forward_30m IS NOT NULL AND forward_1d IS NOT NULL""",
                (time.time(), alert_id),
            )


# ---------------------------------------------------------------------------
# AlertDispatcher
# ---------------------------------------------------------------------------

class AlertDispatcher:
    """Fans Signal objects to SSE subscribers, Discord, and SQLite."""

    def __init__(
        self,
        store: AlertStore,
        discord: DiscordNotifier,
        sse_queue_max: int = 1_000,
        discord_enabled: bool = True,
    ):
        self._store = store
        self._discord = discord
        self._sse_queue_max = sse_queue_max
        self._discord_enabled = discord_enabled
        self._queue: Optional[asyncio.Queue] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._subscribers: List[Tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Create the internal queue and launch the drain task. Call from lifespan."""
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        asyncio.create_task(self._drain(), name="alert-drain")

    # ------------------------------------------------------------------
    # Thread-safe enqueue (called from WS daemon thread)
    # ------------------------------------------------------------------

    def enqueue(self, signals: List[Signal]) -> None:
        """Schedule signals for async processing from any thread."""
        if self._loop is None or self._queue is None:
            return
        for sig in signals:
            try:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, sig)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Async drain + sinks
    # ------------------------------------------------------------------

    async def _drain(self) -> None:
        while True:
            try:
                sig: Signal = await self._queue.get()
                await self._dispatch(sig)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[AlertDispatcher] drain error: {e}", flush=True)

    async def _dispatch(self, sig: Signal) -> None:
        # 1. SSE fan-out
        payload = sig.to_dict()
        payload_json = json.dumps(payload)
        for loop, q in list(self._subscribers):
            loop.call_soon_threadsafe(self._safe_put, q, payload_json)

        # 2. Discord (best-effort)
        if self._discord_enabled:
            try:
                await self._discord.send_alert(sig.message)
            except Exception:
                pass

        # 3. SQLite persistence
        try:
            self._store.insert(sig)
        except Exception as e:
            print(f"[AlertDispatcher] SQLite insert error: {e}", flush=True)

        print(
            f"[Signal] {sig.rule_name} | {sig.symbol} | {sig.side_label or 'neutral'} | {sig.message}",
            flush=True,
        )

    @staticmethod
    def _safe_put(q: asyncio.Queue, item: str) -> None:
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            pass

    # ------------------------------------------------------------------
    # SSE subscriber management
    # ------------------------------------------------------------------

    async def subscribe(self) -> AsyncIterator[str]:
        """Yields JSON-encoded Signal dicts as they fire. Used by /alerts/stream."""
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=self._sse_queue_max)
        entry = (loop, q)
        self._subscribers.append(entry)
        try:
            while True:
                yield await q.get()
        finally:
            if entry in self._subscribers:
                self._subscribers.remove(entry)


# ---------------------------------------------------------------------------
# Forward-return stamper (background async task)
# ---------------------------------------------------------------------------

async def forward_return_stamper(
    store: AlertStore,
    massive,   # MassiveService — avoid circular import by typing as Any
    horizons_min: Optional[List[int]] = None,
) -> None:
    """Background task. Every 60 s, checks for unstamped rows whose horizon has
    elapsed and patches in the realised forward return (%).

    For intraday horizons (≤390 min / 1 trading day) we use get_last_price.
    For the +1d horizon we use the daily close of the target date.
    """
    if horizons_min is None:
        horizons_min = settings.ALERTS_FORWARD_HORIZONS_MIN

    _HORIZON_COLS = {5: "forward_5m", 30: "forward_30m", 1440: "forward_1d"}

    while True:
        try:
            now = time.time()
            for h_min in horizons_min:
                col = _HORIZON_COLS.get(h_min)
                if col is None:
                    continue
                horizon_s = h_min * 60.0
                cutoff = now - horizon_s
                rows = store.get_unstamped(col, cutoff)
                for row in rows:
                    signal_price = row["price"]
                    if signal_price <= 0:
                        continue
                    symbol = row["symbol"]

                    # Intraday horizons: only stamp if the target moment lands
                    # inside regular trading hours. Otherwise get_last_price()
                    # returns a stale prior-session close and pollutes hit-rate
                    # stats. Row stays NULL so it can be retried/marked later.
                    if h_min != 1440 and not is_rth(row["ts"] + horizon_s):
                        continue

                    # Fetch forward price
                    if h_min == 1440:
                        # +1 trading day: use daily close
                        target_dt = datetime.fromtimestamp(row["ts"], tz=timezone.utc)
                        # Skip weekends to find next trading day
                        next_day = target_dt + timedelta(days=1)
                        while next_day.weekday() >= 5:
                            next_day += timedelta(days=1)
                        fwd_price = await asyncio.to_thread(
                            massive.get_close_on_date,
                            symbol,
                            next_day.strftime("%Y-%m-%d"),
                        )
                    else:
                        fwd_price = await asyncio.to_thread(massive.get_last_price, symbol)

                    if fwd_price is None or fwd_price <= 0:
                        continue

                    return_pct = (fwd_price - signal_price) / signal_price * 100.0
                    store.stamp_horizon(row["id"], col, return_pct)

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[forward_return_stamper] error: {e}", flush=True)

        await asyncio.sleep(60)
