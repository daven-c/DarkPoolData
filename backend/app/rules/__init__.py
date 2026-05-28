"""Rule engine package — the platform core.

A Rule is a composable Condition tree evaluated against a stream of MarketEvents.
The same RuleEngine runs live (WS → alerts) and in backtest (replay → metrics).
"""

from backend.app.rules.conditions import (
    Composite,
    Condition,
    Leaf,
    compile_condition,
    validate_logic,
)
from backend.app.rules.engine import RuleEngine
from backend.app.rules.events import MarketEvent, TickerState
from backend.app.rules.metrics import METRICS, catalog, compute_metric
from backend.app.rules.rule import Rule, Signal
from backend.app.rules.builtins import BUILTIN_RULES, default_rules

__all__ = [
    "MarketEvent",
    "TickerState",
    "Condition",
    "Leaf",
    "Composite",
    "compile_condition",
    "validate_logic",
    "Rule",
    "Signal",
    "RuleEngine",
    "METRICS",
    "catalog",
    "compute_metric",
    "BUILTIN_RULES",
    "default_rules",
]
