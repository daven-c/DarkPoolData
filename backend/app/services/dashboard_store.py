import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Dict, Iterable, Optional

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
DB_PATH = os.path.normpath(os.path.join(DB_DIR, "dashboard_cache.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dashboard_daily (
    ticker TEXT NOT NULL,
    date   TEXT NOT NULL,
    total_amount REAL NOT NULL,
    PRIMARY KEY (ticker, date)
);
"""


class DashboardStore:
    """Tiny SQLite-backed cache. Currently used only for prior-day TOTAL AMOUNT
    so the dashboard can compute DAILY AMOUNT CHANGE.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def upsert_totals(self, date: str, totals: Dict[str, float]) -> None:
        rows = [(ticker, date, float(amount)) for ticker, amount in totals.items()]
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO dashboard_daily (ticker, date, total_amount) VALUES (?, ?, ?)",
                rows,
            )

    def get_totals(self, date: str, tickers: Optional[Iterable[str]] = None) -> Dict[str, float]:
        with self._connect() as conn:
            if tickers is None:
                cur = conn.execute(
                    "SELECT ticker, total_amount FROM dashboard_daily WHERE date = ?",
                    (date,),
                )
            else:
                tickers = list(tickers)
                if not tickers:
                    return {}
                placeholders = ",".join("?" for _ in tickers)
                cur = conn.execute(
                    f"SELECT ticker, total_amount FROM dashboard_daily WHERE date = ? AND ticker IN ({placeholders})",
                    [date, *tickers],
                )
            return {row[0]: row[1] for row in cur.fetchall()}
