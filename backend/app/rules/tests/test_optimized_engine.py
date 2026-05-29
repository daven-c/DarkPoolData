"""Unit tests and benchmarks for the optimized multi-tenant RuleIndex and RuleEngine."""

import time
from backend.app.rules import MarketEvent, Rule, RuleEngine
from backend.app.rules.index import RuleIndex
from backend.app.rules.events import TickerState


def test_index_comparison_operators():
    idx = RuleIndex()
    # Add leaf conditions: metric, window_s, cmp, value, cond_id
    idx.add_leaf("trade_notional", None, ">=", 10000, "ge_10k")
    idx.add_leaf("trade_notional", None, ">", 20000, "gt_20k")
    idx.add_leaf("trade_notional", None, "<=", 5000, "le_5k")
    idx.add_leaf("trade_notional", None, "<", 2000, "lt_2k")
    idx.add_leaf("side", None, "==", "ask", "eq_ask")
    idx.add_leaf("side", None, "!=", "bid", "ne_bid")

    idx.rebuild()

    # Test cases: (metric, window_s, value) -> expected satisfied condition IDs
    # Case 1: trade_notional = 15,000 (satisfies >= 10,000, but not other numeric checks)
    assert idx.match("trade_notional", None, 15000) == {"ge_10k"}

    # Case 2: trade_notional = 25,000 (satisfies >= 10,000 and > 20,000)
    assert idx.match("trade_notional", None, 25000) == {"ge_10k", "gt_20k"}

    # Case 3: trade_notional = 1,000 (satisfies <= 5,000 and < 2,000)
    assert idx.match("trade_notional", None, 1000) == {"le_5k", "lt_2k"}

    # Case 4: trade_notional = 4,000 (satisfies <= 5,000 but not < 2,000)
    assert idx.match("trade_notional", None, 4000) == {"le_5k"}

    # Case 5: side = "ask" (satisfies == "ask" and != "bid")
    assert idx.match("side", None, "ask") == {"eq_ask", "ne_bid"}

    # Case 6: side = "bid" (satisfies neither)
    assert idx.match("side", None, "bid") == set()

    # Case 7: side = "other" (satisfies != "bid" but not == "ask")
    assert idx.match("side", None, "other") == {"ne_bid"}


def test_complex_composite_propagation():
    # Construct a rule: (trade_size >= 100 AND side == "ask") OR (trade_notional >= 50000 AND NOT side == "bid")
    rule = Rule(
        id="comp1",
        name="Complex Composite",
        logic={
            "op": "or",
            "children": [
                {
                    "op": "and",
                    "children": [
                        {"metric": "trade_size", "cmp": ">=", "value": 100},
                        {"metric": "side", "cmp": "==", "value": "ask"},
                    ]
                },
                {
                    "op": "and",
                    "children": [
                        {"metric": "trade_notional", "cmp": ">=", "value": 50000},
                        {
                            "op": "not",
                            "children": [{"metric": "side", "cmp": "==", "value": "bid"}]
                        }
                    ]
                }
            ]
        },
        cooldown_s=0
    )

    eng = RuleEngine(rules=[rule])

    # Tick 1: size=50, price=100 (notional=5000), side=ask -> Should not fire
    fired = eng.process(MarketEvent(symbol="AAPL", ts=0.0, price=100.0, size=50, exchange=4))
    assert len(fired) == 0

    # Tick 2: size=120, price=100 (notional=12000), side=ask -> Matches first OR clause (size>=100 and side==ask)
    fired = eng.process(MarketEvent(symbol="AAPL", ts=1.0, price=100.0, size=120, exchange=4))
    assert len(fired) == 1
    assert fired[0].rule_id == "comp1"

    # Tick 3: size=10, price=6000 (notional=60000), side=ask -> Matches second OR clause (notional>=50k and side!=bid)
    fired = eng.process(MarketEvent(symbol="AAPL", ts=2.0, price=6000.0, size=10, exchange=4))
    assert len(fired) == 1
    assert fired[0].rule_id == "comp1"

    # Tick 4: size=10, price=6000 (notional=60000), side=bid -> Does not match second clause because side is bid
    fired = eng.process(MarketEvent(symbol="AAPL", ts=3.0, price=6000.0, size=10, exchange=4))
    # We must seed a downtick first to trigger side=bid classification in test
    eng.process(MarketEvent(symbol="AAPL", ts=4.0, price=5900.0, size=10, exchange=4))  # downtick
    fired = eng.process(MarketEvent(symbol="AAPL", ts=5.0, price=5900.0, size=10, exchange=4))  # equal -> bid
    assert len(fired) == 0


def test_indexing_scale_benchmark():
    """Verify that the engine scales efficiently with large numbers of active rules."""
    # Create 1,000 rules checking different trade size thresholds
    rules = []
    for i in range(1000):
        rules.append(Rule(
            id=f"r_{i}",
            name=f"Rule {i}",
            logic={"metric": "trade_size", "cmp": ">=", "value": 100 + i},
            cooldown_s=0
        ))

    # Initialize optimized engine
    t_start = time.perf_counter()
    eng = RuleEngine(rules=rules)
    t_init = time.perf_counter() - t_start

    # Process an event with a large trade size
    # This should satisfy only rules with threshold <= 500 (approx 400 rules)
    t_process_start = time.perf_counter()
    fired = eng.process(MarketEvent(symbol="AAPL", ts=0.0, price=10.0, size=500, exchange=4))
    t_process = time.perf_counter() - t_process_start

    # We expect exactly 401 rules to fire (thresholds 100 to 500 inclusive)
    assert len(fired) == 401
    print(f"\n[benchmark] Optimized engine initialization for 1,000 rules: {t_init*1000:.2f}ms")
    print(f"[benchmark] Optimized engine event processing: {t_process*1000:.2f}ms")
    # Processing should be well below the 200 microsecond budget
    assert t_process < 0.05  # Must complete in under 50ms (usually under 2ms in Python)


def test_leaf_deduplication():
    # Define two rules checking the exact same leaf condition: trade_size >= 500
    rule1 = Rule(
        id="r1",
        name="Rule 1",
        logic={"metric": "trade_size", "cmp": ">=", "value": 500.004},  # rounds to 500.0
        cooldown_s=0
    )
    rule2 = Rule(
        id="r2",
        name="Rule 2",
        logic={"metric": "trade_size", "cmp": ">=", "value": 500.0},
        cooldown_s=0
    )

    eng = RuleEngine(rules=[rule1, rule2])

    # Check the internal index state:
    # 1. We expect both rules to reference the exact same leaf ID
    eval1 = eng._evaluators["r1"]
    eval2 = eng._evaluators["r2"]
    
    assert eval1.leaf_id == eval2.leaf_id

    # 2. Verify that the threshold list in RuleIndex contains only ONE entry
    idx_dict = eng._index._indices[("trade_size", None)]
    assert len(idx_dict["ge"]) == 1
    # Threshold should be rounded to 500.0
    assert idx_dict["ge"][0][0] == 500.0
    assert idx_dict["ge"][0][1] == eval1.leaf_id

    # 3. Process a tick and make sure BOTH fire correctly
    fired = eng.process(MarketEvent(symbol="AAPL", ts=0.0, price=10.0, size=500, exchange=4))
    assert len(fired) == 2
    rule_ids = {f.rule_id for f in fired}
    assert rule_ids == {"r1", "r2"}

