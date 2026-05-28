"""Pure-logic tests for the rule engine. Run: pytest backend/app/rules/tests"""

from backend.app.rules import MarketEvent, Rule, RuleEngine, compile_condition, validate_logic
from backend.app.rules.events import TickerState


def ev(symbol, ts, price, size, side_seed=None):
    return MarketEvent(symbol=symbol, ts=ts, price=price, size=size, exchange=4)


def test_tickerstate_tick_test_and_totals():
    st = TickerState("X", block_threshold=10_000)
    st.update(ev("X", 0, 10.0, 100))      # first -> ask
    st.update(ev("X", 1, 11.0, 200))      # uptick -> ask
    st.update(ev("X", 2, 10.5, 300))      # downtick -> bid
    assert st.dp_trades == 3
    assert st.at_ask == 10.0 * 100 + 11.0 * 200
    assert st.at_bid == 10.5 * 300
    assert st.net_flow == st.at_ask - st.at_bid


def test_block_trade_counter():
    st = TickerState("X", block_threshold=10_000)
    st.update(ev("X", 0, 5.0, 9_999))
    st.update(ev("X", 1, 5.0, 10_000))
    assert st.block_trades == 1


def test_whale_rule_fires_on_ask_only():
    rule = Rule(
        name="Whale", logic={
            "op": "and",
            "children": [
                {"metric": "trade_notional", "cmp": ">=", "value": 1_000_000},
                {"metric": "side", "cmp": "==", "value": "ask"},
            ],
        }, cooldown_s=0,
    )
    eng = RuleEngine(rules=[rule])
    # uptick, $2M, ask-side -> fires
    eng.process(ev("AAPL", 0, 100.0, 100))           # seed price
    fired = eng.process(ev("AAPL", 1, 200.0, 10_000))  # uptick -> ask, $2M
    assert len(fired) == 1
    assert fired[0].symbol == "AAPL"
    assert fired[0].metadata["side"] == "ask"


def test_whale_rule_skips_bid_side():
    rule = Rule(
        name="Whale", logic={
            "op": "and",
            "children": [
                {"metric": "trade_notional", "cmp": ">=", "value": 1_000_000},
                {"metric": "side", "cmp": "==", "value": "ask"},
            ],
        }, cooldown_s=0,
    )
    eng = RuleEngine(rules=[rule])
    eng.process(ev("AAPL", 0, 200.0, 100))            # seed high price
    fired = eng.process(ev("AAPL", 1, 100.0, 20_000))  # downtick -> bid, $2M
    assert fired == []


def test_cooldown_suppresses_repeat():
    rule = Rule(name="Block", logic={"metric": "trade_size", "cmp": ">=", "value": 1000}, cooldown_s=60)
    eng = RuleEngine(rules=[rule])
    assert len(eng.process(ev("X", 0, 10.0, 5000))) == 1
    assert len(eng.process(ev("X", 30, 10.0, 5000))) == 0   # within cooldown
    assert len(eng.process(ev("X", 61, 10.0, 5000))) == 1   # cooldown elapsed


def test_sweep_window_metric():
    rule = Rule(
        name="Sweep",
        logic={"metric": "trade_count_window", "window_s": 60, "cmp": ">=", "value": 3},
        cooldown_s=0,
    )
    eng = RuleEngine(rules=[rule])
    assert eng.process(ev("X", 0, 10.0, 100)) == []
    assert eng.process(ev("X", 10, 10.0, 100)) == []
    fired = eng.process(ev("X", 20, 10.0, 100))  # 3rd trade in window
    assert len(fired) == 1


def test_price_move_pct():
    rule = Rule(
        name="Breakout",
        logic={"metric": "price_move_pct", "window_s": 300, "cmp": ">=", "value": 2.0},
        cooldown_s=0,
    )
    eng = RuleEngine(rules=[rule])
    eng.process(ev("X", 0, 100.0, 10))
    assert eng.process(ev("X", 10, 101.0, 10)) == []     # +1%
    fired = eng.process(ev("X", 20, 103.0, 10))          # +3% from window start
    assert len(fired) == 1


def test_disabled_rule_does_not_fire():
    rule = Rule(name="X", logic={"metric": "trade_size", "cmp": ">=", "value": 1}, enabled=False, cooldown_s=0)
    eng = RuleEngine(rules=[rule])
    assert eng.process(ev("X", 0, 10.0, 100)) == []


def test_composite_or_and_not():
    eng = RuleEngine(rules=[Rule(name="orrule", cooldown_s=0, logic={
        "op": "or",
        "children": [
            {"metric": "trade_size", "cmp": ">=", "value": 100000},
            {"op": "not", "children": [{"metric": "side", "cmp": "==", "value": "bid"}]},
        ],
    })])
    fired = eng.process(ev("X", 0, 10.0, 5))  # first trade -> ask -> not bid -> True
    assert len(fired) == 1


def test_validate_logic_rejects_bad_metric():
    try:
        validate_logic({"metric": "does_not_exist", "cmp": ">=", "value": 1})
        assert False, "should have raised"
    except ValueError:
        pass


def test_roundtrip_condition_serialization():
    node = {"op": "and", "children": [
        {"metric": "trade_notional", "cmp": ">=", "value": 1000},
        {"metric": "price_move_pct", "window_s": 60, "cmp": ">=", "value": 1.0},
    ]}
    cond = compile_condition(node)
    assert cond.to_dict() == node
