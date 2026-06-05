"""Tests for the off-hours MockStreamer synthetic-tape driver.

Run: pytest backend/app/rules/tests/test_mock_streamer.py
"""

import sys
import types

# stream.py imports the `massive` SDK at module load. Stub it ONLY when the real
# SDK is absent (e.g. CI sandbox) so MockStreamer — which is pure Python — stays
# importable. When the SDK is installed this block is skipped and the real one wins.
try:  # pragma: no cover - import guard
    import massive  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - import guard
    _massive = types.ModuleType("massive")
    _massive.WebSocketClient = object
    _ws = types.ModuleType("massive.websocket")
    _models = types.ModuleType("massive.websocket.models")
    _models.Feed = type("Feed", (), {"RealTime": "realtime", "Delayed": "delayed"})
    _models.Market = type("Market", (), {"Stocks": "stocks"})
    sys.modules["massive"] = _massive
    sys.modules["massive.websocket"] = _ws
    sys.modules["massive.websocket.models"] = _models

from backend.app.rules import Rule, RuleEngine
from backend.app.services.stream import MockStreamer


def test_step_ingests_every_trade_into_engine():
    universe = ["AAPL", "MSFT"]
    engine = RuleEngine(rules=[], universe=universe)
    ms = MockStreamer(universe, engine, seed=7, block_prob=0.0)

    for _ in range(50):
        ms.step()

    snap = engine.snapshot()
    total_trades = sum(row.get("dp_trades", 0) for row in snap.values())
    assert total_trades == 50
    # Every traded symbol should have a positive last price from the random walk.
    assert all(row.get("dp_trades", 0) == 0 or row.get("total_amount", 0) > 0 for row in snap.values())


def test_seeded_streamer_is_deterministic():
    universe = ["AAPL", "MSFT", "TSLA"]
    a = MockStreamer(universe, RuleEngine(rules=[], universe=universe), seed=123)
    b = MockStreamer(universe, RuleEngine(rules=[], universe=universe), seed=123)

    seq_a = [(e.symbol, e.size, e.price) for e in (a._next_event() for _ in range(25))]
    seq_b = [(e.symbol, e.size, e.price) for e in (b._next_event() for _ in range(25))]
    assert seq_a == seq_b


def test_block_probability_controls_block_trades():
    universe = ["AAPL"]

    blocky = MockStreamer(universe, RuleEngine(rules=[], universe=universe), seed=1, block_prob=1.0)
    for _ in range(30):
        ev = blocky._next_event()
        assert ev.size >= 10_000          # block_prob=1.0 → always block-sized

    eng_none = RuleEngine(rules=[], universe=universe)
    quiet = MockStreamer(universe, eng_none, seed=1, block_prob=0.0)
    for _ in range(30):
        quiet.step()
    assert eng_none.snapshot()["AAPL"]["block_trades"] == 0


def test_alert_callback_receives_fired_signals():
    universe = ["AAPL"]
    # trade_notional >= 0 is always true, cooldown 0 → one signal per event.
    rule = Rule(name="Any", logic={"metric": "trade_notional", "cmp": ">=", "value": 0}, cooldown_s=0)
    engine = RuleEngine(rules=[rule], universe=universe)

    fired = []
    ms = MockStreamer(universe, engine, alert_callback=fired.extend, seed=2)
    for _ in range(10):
        ms.step()

    assert len(fired) == 10


def test_empty_universe_falls_back_to_default():
    engine = RuleEngine(rules=[], universe=[])
    ms = MockStreamer([], engine, seed=0)
    assert ms.universe == MockStreamer.DEFAULT_UNIVERSE
    # And it can still produce events without error.
    ev = ms._next_event()
    assert ev.symbol in MockStreamer.DEFAULT_UNIVERSE
