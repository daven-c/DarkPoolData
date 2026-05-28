"""Seed rules expressed as composable condition trees.

These ship enabled by default so the platform fires useful tickers out of the box;
users can disable/tune/clone them in the Strategy Lab.
"""

from backend.app.rules.rule import Rule

BUILTIN_RULES = [
    Rule(
        id="builtin_whale_buy",
        name="Whale Buy",
        kind="WHALE",
        severity="critical",
        side_label="bull",
        cooldown_s=300,
        logic={
            "op": "and",
            "children": [
                {"metric": "trade_notional", "cmp": ">=", "value": 1_000_000},
                {"metric": "side", "cmp": "==", "value": "ask"},
            ],
        },
    ),
    Rule(
        id="builtin_block_trade",
        name="Block Trade",
        kind="BLOCK",
        severity="warning",
        cooldown_s=120,
        logic={"metric": "trade_size", "cmp": ">=", "value": 10_000},
    ),
    Rule(
        id="builtin_bullish_sweep",
        name="Bullish Sweep",
        kind="SWEEP",
        severity="critical",
        side_label="bull",
        cooldown_s=300,
        logic={
            "op": "and",
            "children": [
                {"metric": "trade_count_window", "window_s": 60, "cmp": ">=", "value": 5},
                {"metric": "ask_notional_window", "window_s": 60, "cmp": ">=", "value": 2_000_000},
            ],
        },
    ),
    Rule(
        id="builtin_price_breakout",
        name="Price Breakout",
        kind="BREAKOUT",
        severity="warning",
        side_label="bull",
        cooldown_s=300,
        logic={"metric": "price_move_pct", "window_s": 300, "cmp": ">=", "value": 2.0},
    ),
    Rule(
        id="builtin_bearish_flow",
        name="Bearish Net Flow",
        kind="FLOW",
        severity="info",
        side_label="bear",
        cooldown_s=600,
        logic={"metric": "net_flow_notional", "cmp": "<=", "value": -5_000_000},
    ),
]


def default_rules():
    """Fresh Rule instances (recompiled) for seeding an empty store."""
    return [Rule.from_dict(r.to_dict()) for r in BUILTIN_RULES]
