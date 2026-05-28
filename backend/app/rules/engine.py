"""RuleEngine — drives state + rule evaluation for both live and backtest paths.

`process(event)` updates the per-symbol `TickerState`, evaluates every active rule,
applies a per-(rule, symbol) cooldown, and returns the `Signal`s that fired.
The same engine instance backs the live dashboard snapshot.
"""

import threading
from typing import Dict, List, Optional, Tuple

from backend.app.rules.events import MarketEvent, TickerState
from backend.app.rules.rule import Rule, Signal


class RuleEngine:
    def __init__(
        self,
        rules: Optional[List[Rule]] = None,
        universe: Optional[List[str]] = None,
        block_threshold: int = 10_000,
        window_max_s: float = 300.0,
    ):
        self._rules: List[Rule] = list(rules or [])
        self._states: Dict[str, TickerState] = {}
        self._cooldowns: Dict[Tuple[str, str], float] = {}
        self._block_threshold = block_threshold
        self._window_max_s = window_max_s
        self._lock = threading.Lock()
        for sym in universe or []:
            self._states[sym] = self._new_state(sym)

    def _new_state(self, symbol: str) -> TickerState:
        return TickerState(
            symbol=symbol,
            block_threshold=self._block_threshold,
            window_max_s=self._window_max_s,
        )

    def state(self, symbol: str) -> TickerState:
        st = self._states.get(symbol)
        if st is None:
            st = self._new_state(symbol)
            self._states[symbol] = st
        return st

    def set_rules(self, rules: List[Rule]) -> None:
        with self._lock:
            self._rules = list(rules)

    def rules(self) -> List[Rule]:
        return list(self._rules)

    def set_prior_total(self, symbol: str, total: float) -> None:
        self.state(symbol).prior_day_total = total

    def process(self, event: MarketEvent) -> List[Signal]:
        st = self.state(event.symbol)
        with self._lock:
            st.update(event)
            fired: List[Signal] = []
            for rule in self._rules:
                if not rule.enabled:
                    continue
                if rule.matches(event, st):
                    key = (rule.id, event.symbol)
                    last = self._cooldowns.get(key)
                    if last is None or (event.ts - last) >= rule.cooldown_s:
                        self._cooldowns[key] = event.ts
                        fired.append(rule.make_signal(event, st))
            return fired

    def snapshot(self) -> Dict[str, dict]:
        with self._lock:
            return {sym: st.dashboard_row() for sym, st in self._states.items()}

    def universe(self) -> List[str]:
        return sorted(self._states.keys())

    def preview(self, draft_rule: Rule) -> List[str]:
        """Symbols whose *current* state would satisfy the draft rule, evaluated
        against a synthetic 'current' event (last price/size of the session)."""
        matches: List[str] = []
        with self._lock:
            for sym, st in self._states.items():
                if st.last_price is None:
                    continue
                probe = MarketEvent(
                    symbol=sym,
                    ts=(st.recent[-1][0] if st.recent else 0.0),
                    price=st.last_price,
                    size=int(st.recent[-1][2]) if st.recent else 0,
                    exchange=4,
                    side=st.last_side,
                )
                try:
                    if draft_rule._compiled.evaluate(probe, st):
                        matches.append(sym)
                except Exception:
                    continue
        return matches
