"""Metric catalog — the vocabulary the composable rule builder exposes.

Each metric maps `(event, state, **params) -> value`. The `METRICS` registry is
also serialized to the frontend (`GET /rules/metrics`) so the builder can render
the right input fields generically.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from backend.app.rules.events import MarketEvent, TickerState

MetricFn = Callable[..., Any]


@dataclass
class MetricSpec:
    key: str
    label: str
    value_type: str  # "number" | "enum" | "bool"
    fn: MetricFn
    params: List[dict] = field(default_factory=list)  # [{name,type,default}]
    enum_values: Optional[List[str]] = None
    help: str = ""


def _window_slice(state: TickerState, now: float, window_s: float):
    cutoff = now - window_s
    return [r for r in state.recent if r[0] >= cutoff]


# ---- metric implementations ------------------------------------------------

def _trade_notional(event: MarketEvent, state: TickerState, **_):
    return event.notional


def _trade_size(event: MarketEvent, state: TickerState, **_):
    return float(event.size)


def _side(event: MarketEvent, state: TickerState, **_):
    return event.side or "ask"


def _block(event: MarketEvent, state: TickerState, **_):
    return event.size >= state.block_threshold


def _net_flow_notional(event: MarketEvent, state: TickerState, **_):
    return state.net_flow


def _session_total_notional(event: MarketEvent, state: TickerState, **_):
    return state.total_amount


def _block_count(event: MarketEvent, state: TickerState, **_):
    return float(state.block_trades)


def _daily_change_pct(event: MarketEvent, state: TickerState, **_):
    return state.daily_change_pct if state.daily_change_pct is not None else 0.0


def _price_move_pct(event: MarketEvent, state: TickerState, window_s: float = 60, **_):
    sl = _window_slice(state, event.ts, window_s)
    if not sl:
        return 0.0
    start_price = sl[0][1]
    if start_price <= 0:
        return 0.0
    return (event.price / start_price - 1.0) * 100.0


def _trade_count_window(event: MarketEvent, state: TickerState, window_s: float = 60, **_):
    return float(len(_window_slice(state, event.ts, window_s)))


def _notional_window(event: MarketEvent, state: TickerState, window_s: float = 60, **_):
    return sum(r[3] for r in _window_slice(state, event.ts, window_s))


def _ask_notional_window(event: MarketEvent, state: TickerState, window_s: float = 60, **_):
    return sum(r[3] for r in _window_slice(state, event.ts, window_s) if r[4] == "ask")


_WINDOW_PARAM = [{"name": "window_s", "type": "number", "default": 60}]

METRICS: Dict[str, MetricSpec] = {
    m.key: m
    for m in [
        MetricSpec("trade_notional", "Trade $ value", "number", _trade_notional,
                   help="Dollar value (price × size) of the current trade. Whale detection."),
        MetricSpec("trade_size", "Trade size (shares)", "number", _trade_size,
                   help="Share count of the current trade. Block detection."),
        MetricSpec("side", "Trade side", "enum", _side, enum_values=["ask", "bid"],
                   help="Buyer- vs seller-initiated (Lee-Ready tick test)."),
        MetricSpec("is_block", "Is block trade", "bool", _block,
                   help="True if trade size ≥ block threshold."),
        MetricSpec("net_flow_notional", "Session net flow $", "number", _net_flow_notional,
                   help="Cumulative at-ask minus at-bid dollars (bullish if positive)."),
        MetricSpec("session_total_notional", "Session total $", "number", _session_total_notional,
                   help="Cumulative dark-pool dollar volume today."),
        MetricSpec("block_count", "Session block count", "number", _block_count,
                   help="Number of block trades so far today."),
        MetricSpec("daily_change_pct", "Daily $ change %", "number", _daily_change_pct,
                   help="Session total vs prior-day total, percent."),
        MetricSpec("price_move_pct", "Price move % (window)", "number", _price_move_pct,
                   params=_WINDOW_PARAM, help="Percent price change over the trailing window. Price action."),
        MetricSpec("trade_count_window", "Trade count (window)", "number", _trade_count_window,
                   params=_WINDOW_PARAM, help="Number of trades in the trailing window. Sweep detection."),
        MetricSpec("notional_window", "Window $ volume", "number", _notional_window,
                   params=_WINDOW_PARAM, help="Total dollars traded in the trailing window."),
        MetricSpec("ask_notional_window", "Window ask $ volume", "number", _ask_notional_window,
                   params=_WINDOW_PARAM, help="Ask-side dollars in the trailing window. Aggressive buying."),
    ]
}


def compute_metric(key: str, event: MarketEvent, state: TickerState, **params) -> Any:
    spec = METRICS.get(key)
    if spec is None:
        raise KeyError(f"unknown metric: {key}")
    return spec.fn(event, state, **params)


def catalog() -> List[dict]:
    """Serializable metric catalog for the rule-builder UI."""
    return [
        {
            "key": m.key,
            "label": m.label,
            "value_type": m.value_type,
            "params": m.params,
            "enum_values": m.enum_values,
            "help": m.help,
        }
        for m in METRICS.values()
    ]
