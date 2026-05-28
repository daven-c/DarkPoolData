"""Composable condition tree — the heart of the rule builder.

A condition is either a leaf comparison `{metric, cmp, value, window_s?}` or a
composite `{op: and|or|not, children: [...]}`. Trees nest arbitrarily and are
fully JSON-serializable, so rules round-trip between the UI, SQLite, and the engine.
"""

import operator
from typing import Any, List, Optional

from backend.app.rules.events import MarketEvent, TickerState
from backend.app.rules.metrics import METRICS, compute_metric

_ORDER_CMP = {">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt}
_EQ_CMP = {"==": operator.eq, "!=": operator.ne}
CMP_OPS = {**_ORDER_CMP, **_EQ_CMP}
BOOL_OPS = {"and", "or", "not"}


class Condition:
    def evaluate(self, event: MarketEvent, state: TickerState) -> bool:
        raise NotImplementedError

    def to_dict(self) -> dict:
        raise NotImplementedError


class Leaf(Condition):
    def __init__(self, metric: str, cmp: str, value: Any, window_s: Optional[float] = None):
        if metric not in METRICS:
            raise ValueError(f"unknown metric: {metric}")
        if cmp not in CMP_OPS:
            raise ValueError(f"unknown comparator: {cmp}")
        self.metric = metric
        self.cmp = cmp
        self.value = value
        self.window_s = window_s

    def evaluate(self, event: MarketEvent, state: TickerState) -> bool:
        params = {"window_s": self.window_s} if self.window_s is not None else {}
        try:
            actual = compute_metric(self.metric, event, state, **params)
        except Exception:
            return False
        op = CMP_OPS[self.cmp]
        try:
            # Ordering comparisons only make sense for numerics; strings use eq/ne.
            if self.cmp in _ORDER_CMP and isinstance(actual, str):
                return False
            return bool(op(actual, self.value))
        except TypeError:
            return False

    def to_dict(self) -> dict:
        d: dict = {"metric": self.metric, "cmp": self.cmp, "value": self.value}
        if self.window_s is not None:
            d["window_s"] = self.window_s
        return d


class Composite(Condition):
    def __init__(self, op: str, children: List[Condition]):
        if op not in BOOL_OPS:
            raise ValueError(f"unknown op: {op}")
        if op == "not" and len(children) != 1:
            raise ValueError("'not' takes exactly one child")
        if op in ("and", "or") and not children:
            raise ValueError(f"'{op}' needs at least one child")
        self.op = op
        self.children = children

    def evaluate(self, event: MarketEvent, state: TickerState) -> bool:
        if self.op == "and":
            return all(c.evaluate(event, state) for c in self.children)
        if self.op == "or":
            return any(c.evaluate(event, state) for c in self.children)
        return not self.children[0].evaluate(event, state)

    def to_dict(self) -> dict:
        return {"op": self.op, "children": [c.to_dict() for c in self.children]}


def compile_condition(node: dict) -> Condition:
    """Build a Condition tree from its JSON dict form."""
    if not isinstance(node, dict):
        raise ValueError("condition node must be an object")
    if "op" in node:
        children = [compile_condition(c) for c in node.get("children", [])]
        return Composite(node["op"], children)
    return Leaf(node["metric"], node["cmp"], node["value"], node.get("window_s"))


def validate_logic(node: dict) -> None:
    """Raise ValueError if the tree is malformed (used by the API before saving)."""
    compile_condition(node)
