"""RuleEngine — drives state + rule evaluation for both live and backtest paths.

Uses eager metric caching and indexed evaluation trees to scale to thousands
of user conditions under high-frequency market streaming feeds.
"""

import asyncio
import threading
from typing import Any, AsyncIterator, Dict, List, Optional, Set, Tuple

from backend.app.rules.events import MarketEvent, TickerState
from backend.app.rules.rule import Rule, Signal
from backend.app.rules.index import RuleIndex
from backend.app.rules.evaluator import compile_evaluator
from backend.app.rules.metrics import compute_metric


class RuleEngine:
    def __init__(
        self,
        rules: Optional[List[Rule]] = None,
        universe: Optional[List[str]] = None,
        block_threshold: int = 10_000,
        window_max_s: float = 300.0,
        sse_queue_max: int = 1_000,
    ):
        self._states: Dict[str, TickerState] = {}
        self._cooldowns: Dict[Tuple[str, str], float] = {}
        self._block_threshold = block_threshold
        self._window_max_s = window_max_s
        self._sse_queue_max = sse_queue_max
        self._lock = threading.Lock()
        self._subscribers: List[Tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []

        self._index = RuleIndex()
        self._evaluators: Dict[str, Any] = {}
        self._referenced_metrics: Set[Tuple[str, Any]] = set()
        self._rules: List[Rule] = []

        self.set_rules(rules or [])

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
            self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._index.clear()
        self._evaluators.clear()
        self._referenced_metrics.clear()
        for rule in self._rules:
            if not rule.enabled:
                continue
            leaf_counter = [0]
            eval_root = compile_evaluator(
                rule._compiled,
                rule.id,
                leaf_counter,
                self._index,
                self._referenced_metrics
            )
            self._evaluators[rule.id] = eval_root
        self._index.rebuild()

    def rules(self) -> List[Rule]:
        return list(self._rules)

    def set_prior_total(self, symbol: str, total: float) -> None:
        self.state(symbol).prior_day_total = total

    def process(self, event: MarketEvent) -> List[Signal]:
        st = self.state(event.symbol)
        row: Optional[dict] = None
        with self._lock:
            st.update(event)
            fired: List[Signal] = []

            # 1. Eagerly evaluate only the metrics referenced by active rules
            satisfied_leaves: Set[str] = set()
            computed_metrics: Dict[Tuple[str, Any], Any] = {}
            for metric_name, window_s in self._referenced_metrics:
                params = {"window_s": window_s} if window_s is not None else {}
                try:
                    val = compute_metric(metric_name, event, st, **params)
                    computed_metrics[(metric_name, window_s)] = val
                except Exception:
                    computed_metrics[(metric_name, window_s)] = None

            # 2. Get satisfied leaf condition IDs from index
            for (metric_name, window_s), val in computed_metrics.items():
                satisfied_leaves.update(self._index.match(metric_name, window_s, val))

            # 3. Propagate and check each active rule's evaluator
            for rule in self._rules:
                if not rule.enabled:
                    continue
                evaluator = self._evaluators.get(rule.id)
                if evaluator is None:
                    continue

                if evaluator.evaluate(satisfied_leaves):
                    key = (rule.id, event.symbol)
                    last = self._cooldowns.get(key)
                    if last is None or (event.ts - last) >= rule.cooldown_s:
                        self._cooldowns[key] = event.ts
                        fired.append(rule.make_signal(event, st))

            row = st.dashboard_row()

        if row is not None:
            self._notify(row)
        return fired

    def snapshot(self) -> Dict[str, dict]:
        with self._lock:
            return {sym: st.dashboard_row() for sym, st in self._states.items()}

    def universe(self) -> List[str]:
        return sorted(self._states.keys())

    # ------------------------------------------------------------------
    # SSE fan-out (mirrors DashboardAggregator.subscribe pattern)
    # ------------------------------------------------------------------

    def _notify(self, row: dict) -> None:
        """Push a dashboard row to all SSE subscribers (called from WS thread)."""
        for loop, q in list(self._subscribers):
            loop.call_soon_threadsafe(self._safe_put, q, row)

    @staticmethod
    def _safe_put(q: asyncio.Queue, item: dict) -> None:
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            pass

    async def subscribe(self) -> AsyncIterator[dict]:
        """Async generator yielding dashboard rows as they arrive. Cancellation-safe."""
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

