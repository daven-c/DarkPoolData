"""Rule-based backtesting engine.

Replays historical TRF trades through a fresh RuleEngine — same engine used
live — and produces:
1. Signal log (which rules fired, when, at what price)
2. Forward-return stats: hit rate + avg/median returns at +5m/+30m/+1d
3. Portfolio P&L via backtester.Portfolio (first time it's actually wired)
4. Equity curve for charting

The `run_rule_backtest` function is synchronous; the API endpoint wraps it
in `asyncio.to_thread` so it doesn't block the event loop.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any, Dict, List, Optional

import pandas as pd

from backtester.data import APIDataProvider, MockDataProvider
from backtester.portfolio import Portfolio
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


def _epoch_s(ts: pd.Timestamp) -> float:
    return ts.timestamp()


def run_rule_backtest(
    symbols: List[str],
    start_date: str,
    end_date: str,
    rules: List[Rule],
    api_key: Optional[str] = None,
    notional_per_signal: float = 10_000.0,
    exit_after_min: float = 30.0,
) -> Dict[str, Any]:
    """
    Parameters
    ----------
    symbols           : tickers to replay (max 5 recommended — each fetches all trades)
    start_date        : YYYY-MM-DD
    end_date          : YYYY-MM-DD
    rules             : Rule objects to evaluate (use store.as_rules() for platform rules)
    api_key           : Massive API key; falls back to settings then MockDataProvider
    notional_per_signal: fixed dollar size per BUY order
    exit_after_min    : close position after this many minutes (time-based exit)

    Returns
    -------
    {signals, forward_return_stats, equity_curve, portfolio_metrics}
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

    # Portfolio — using fixed notional sizing, time-based exit
    # Initial cash = enough to fund all potential signals (overestimate is fine)
    initial_cash = notional_per_signal * max(len(symbols) * 20, 100)
    portfolio = Portfolio(initial_cash=initial_cash)
    current_prices: Dict[str, float] = {}

    # open_exits[symbol] = {'exit_ts': float, 'qty': float}
    open_exits: Dict[str, dict] = {}

    equity_curve: List[dict] = []
    _sig_counter = [0]  # mutable counter for unique keys

    for batch in provider.get_data():
        ts: pd.Timestamp = batch["timestamp"]
        ts_epoch = _epoch_s(ts)

        for symbol, price in batch["prices"].items():
            current_prices[symbol] = float(price)
            indicators = batch.get("indicators", {}).get(symbol, {})
            size = int(indicators.get("size", 0))
            is_dark_pool = bool(indicators.get("is_dark_pool", False))

            # ---- resolve pending forward-return horizons ----------------
            for key_s, pend in list(pending.items()):
                if pend["signal"].symbol != symbol:
                    continue
                for label, h_secs in _HORIZONS:
                    if pend["horizons"].get(label) is None:
                        if ts_epoch >= pend["entry_ts"] + h_secs:
                            pend["horizons"][label] = float(price)

            # ---- portfolio time-exits -----------------------------------
            ex = open_exits.get(symbol)
            if ex and ts_epoch >= ex["exit_ts"] and ex["qty"] > 0:
                portfolio.sell(symbol, ex["qty"], float(price), ts)
                del open_exits[symbol]
                portfolio.update_equity(ts, current_prices)
                equity_curve.append({"timestamp": ts.isoformat(), "total_value": portfolio.equity_history[-1]["total_value"]})

            # ---- only feed TRF (dark-pool) trades to engine -------------
            if not is_dark_pool or size <= 0:
                continue

            event = MarketEvent(
                symbol=symbol,
                ts=ts_epoch,
                price=float(price),
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

                # Portfolio: BUY on bull (or neutral) signals
                if sig.side_label != "bear" and symbol not in open_exits:
                    qty = notional_per_signal / sig.price if sig.price > 0 else 0.0
                    if qty > 0:
                        ok = portfolio.buy(symbol, qty, float(sig.price), ts)
                        if ok:
                            open_exits[symbol] = {
                                "exit_ts": ts_epoch + exit_after_min * 60,
                                "qty": qty,
                            }
                            portfolio.update_equity(ts, current_prices)
                            equity_curve.append({"timestamp": ts.isoformat(), "total_value": portfolio.equity_history[-1]["total_value"]})

                # Portfolio: SELL on bear signals
                elif sig.side_label == "bear" and symbol in open_exits:
                    ex2 = open_exits.pop(symbol)
                    if ex2["qty"] > 0:
                        portfolio.sell(symbol, ex2["qty"], float(sig.price), ts)
                        portfolio.update_equity(ts, current_prices)
                        equity_curve.append({"timestamp": ts.isoformat(), "total_value": portfolio.equity_history[-1]["total_value"]})

    # ---- close any remaining open positions at last known price ---------
    final_ts = pd.Timestamp("now", tz="UTC")
    for symbol, ex in open_exits.items():
        price = current_prices.get(symbol)
        if price and ex["qty"] > 0:
            portfolio.sell(symbol, ex["qty"], float(price), final_ts)
    if current_prices:
        portfolio.update_equity(final_ts, current_prices)
        if portfolio.equity_history:
            equity_curve.append({"timestamp": final_ts.isoformat(), "total_value": portfolio.equity_history[-1]["total_value"]})

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
            "severity": s.severity,
            "side_label": s.side_label,
            "price": s.price,
            "message": s.message,
        }
        for s in all_signals
    ]

    portfolio_metrics: Dict[str, Any] = {}
    try:
        portfolio_metrics = portfolio.get_metrics()
        # Convert non-serializable types
        for k, v in list(portfolio_metrics.items()):
            if hasattr(v, "item"):
                portfolio_metrics[k] = v.item()
            elif isinstance(v, dict):
                portfolio_metrics[k] = v  # positions dict
    except Exception as exc:
        portfolio_metrics = {"error": str(exc)}

    return {
        "symbols": symbols,
        "start_date": start_date,
        "end_date": end_date,
        "signal_count": len(all_signals),
        "signals": sig_list,
        "forward_return_stats": fwd_stats,
        "equity_curve": equity_curve,
        "portfolio_metrics": portfolio_metrics,
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
