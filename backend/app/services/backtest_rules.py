"""Rule-based backtesting / signal-validation engine.

Replays historical TRF trades through a fresh RuleEngine — the same engine used
live — and answers one question: **did the signal predict the move?**

It produces:
1. Signal log (which rules fired, when, at what price)
2. Forward-return stats: hit rate + avg/median returns at +5m/+30m/+1d
3. A downsampled price series per symbol so the UI can mark each signal on the
   price graph.

No portfolio simulation — this is a signal-quality tool, not a P&L simulator.

The `run_rule_backtest` function is synchronous; the API endpoint wraps it
in `asyncio.to_thread` so it doesn't block the event loop.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any, Dict, List, Optional

import pandas as pd

from backtester.data import APIDataProvider, MockDataProvider
from backend.app.core.config import settings
from backend.app.rules.engine import RuleEngine
from backend.app.rules.events import MarketEvent
from backend.app.rules.rule import Rule, Signal

# Forward-return horizons used for stats
_HORIZONS = [
    ("5m",   5  * 60),
    ("30m",  30 * 60),
    ("1d",   1  * 24 * 3600),
]

# Max points per symbol in the returned price series (the raw tape can be huge;
# the chart only needs enough points to draw a recognizable price path).
_MAX_PRICE_POINTS = 800


def _epoch_s(ts: pd.Timestamp) -> float:
    return ts.timestamp()


def _downsample(points: List[dict], max_points: int) -> List[dict]:
    """Evenly thin a time-ordered point list down to <= max_points."""
    n = len(points)
    if n <= max_points:
        return points
    step = n / max_points
    out = [points[int(i * step)] for i in range(max_points)]
    # Always keep the final point so the line reaches the end of the window.
    if out[-1] is not points[-1]:
        out.append(points[-1])
    return out


def run_rule_backtest(
    symbols: List[str],
    start_date: str,
    end_date: str,
    rules: List[Rule],
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Parameters
    ----------
    symbols    : tickers to replay (max 5 recommended — each fetches all trades)
    start_date : YYYY-MM-DD
    end_date   : YYYY-MM-DD
    rules      : Rule objects to evaluate (use store.as_rules() for platform rules)
    api_key    : Massive API key; falls back to settings then MockDataProvider

    Returns
    -------
    {signals, signal_count, forward_return_stats, price_series}
    """
    key = api_key or settings.MASSIVE_API_KEY
    if key:
        provider = APIDataProvider(
            api_key=key,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            mode="trades",
        )
    else:
        provider = MockDataProvider(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
        )

    engine = RuleEngine(rules=[r for r in rules if r.enabled])

    all_signals: List[Signal] = []

    # pending[unique_key] = {'signal': sig, 'entry_ts': float, 'horizons': {label: price|None}}
    pending: Dict[str, dict] = {}

    # Full (lit + dark) price path per symbol, for charting + signal markers.
    price_points: Dict[str, List[dict]] = defaultdict(list)

    _sig_counter = [0]  # mutable counter for unique keys

    for batch in provider.get_data():
        ts: pd.Timestamp = batch["timestamp"]
        ts_epoch = _epoch_s(ts)

        for symbol, price in batch["prices"].items():
            price_f = float(price)
            indicators = batch.get("indicators", {}).get(symbol, {})
            size = int(indicators.get("size", 0))
            is_dark_pool = bool(indicators.get("is_dark_pool", False))

            # Record the price path (every trade, lit or dark).
            price_points[symbol].append({"t": ts_epoch, "price": price_f})

            # ---- resolve pending forward-return horizons ----------------
            for key_s, pend in list(pending.items()):
                if pend["signal"].symbol != symbol:
                    continue
                for label, h_secs in _HORIZONS:
                    if pend["horizons"].get(label) is None:
                        if ts_epoch >= pend["entry_ts"] + h_secs:
                            pend["horizons"][label] = price_f

            # ---- only feed TRF (dark-pool) trades to engine -------------
            if not is_dark_pool or size <= 0:
                continue

            event = MarketEvent(
                symbol=symbol,
                ts=ts_epoch,
                price=price_f,
                size=size,
                exchange=4,
                is_dark_pool=True,
            )
            signals = engine.process(event)

            for sig in signals:
                all_signals.append(sig)

                # Track forward returns
                _sig_counter[0] += 1
                pkey = f"{sig.rule_id}:{sig.symbol}:{_sig_counter[0]}"
                pending[pkey] = {
                    "signal": sig,
                    "entry_ts": ts_epoch,
                    "entry_price": sig.price,
                    "horizons": {label: None for label, _ in _HORIZONS},
                }

    # ---- forward-return stats -------------------------------------------
    fwd_stats = _compute_forward_stats(all_signals, pending)

    # ---- serialize signals (keep metadata lightweight) -----------------
    sig_list = [
        {
            "rule_id": s.rule_id,
            "rule_name": s.rule_name,
            "symbol": s.symbol,
            "ts": s.ts,
            "kind": s.kind,
            "side_label": s.side_label,
            "price": s.price,
            "message": s.message,
        }
        for s in all_signals
    ]

    # ---- downsampled price series per symbol ----------------------------
    price_series = {
        sym: _downsample(pts, _MAX_PRICE_POINTS)
        for sym, pts in price_points.items()
    }

    return {
        "symbols": symbols,
        "start_date": start_date,
        "end_date": end_date,
        "signal_count": len(all_signals),
        "signals": sig_list,
        "forward_return_stats": fwd_stats,
        "price_series": price_series,
    }


# ---------------------------------------------------------------------------
# Forward-return stats helpers
# ---------------------------------------------------------------------------

def _compute_forward_stats(
    signals: List[Signal],
    pending: Dict[str, dict],
) -> Dict[str, Any]:
    """Aggregate resolved forward returns per rule, per horizon."""
    # Collect resolved prices keyed by (rule_name, horizon_label)
    buckets: Dict[tuple, List[float]] = defaultdict(list)

    for pend in pending.values():
        sig = pend["signal"]
        entry = pend["entry_price"]
        if entry <= 0:
            continue
        for label, _ in _HORIZONS:
            fwd = pend["horizons"].get(label)
            if fwd is not None and fwd > 0:
                ret = (fwd - entry) / entry * 100.0
                buckets[(sig.rule_name, label)].append(ret)

    stats: Dict[str, Any] = {}
    all_rule_names = {s.rule_name for s in signals}
    for rule_name in all_rule_names:
        rule_stats: Dict[str, Any] = {"signal_count": sum(1 for s in signals if s.rule_name == rule_name)}
        for label, _ in _HORIZONS:
            rets = buckets.get((rule_name, label), [])
            if rets:
                positive = [r for r in rets if r > 0]
                rule_stats[label] = {
                    "count": len(rets),
                    "hit_rate": len(positive) / len(rets),
                    "avg_return_pct": statistics.mean(rets),
                    "median_return_pct": statistics.median(rets),
                    "best_pct": max(rets),
                    "worst_pct": min(rets),
                }
            else:
                rule_stats[label] = None  # horizon not yet resolved in replay window
        stats[rule_name] = rule_stats

    return stats
