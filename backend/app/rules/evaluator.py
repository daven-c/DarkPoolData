"""Boolean evaluation network for dynamic condition propagation.

Translates nested Condition trees (AND/OR/NOT) into an efficient, flattened
memory structure (EvalNodes) and registers leaf elements into the RuleIndex.
"""

from typing import Any, Dict, List, Set, Tuple
from backend.app.rules.conditions import Condition, Leaf, Composite
from backend.app.rules.index import RuleIndex


class EvalNode:
    def evaluate(self, satisfied_leaves: Set[str]) -> bool:
        raise NotImplementedError


class EvalLeaf(EvalNode):
    def __init__(self, leaf_id: str):
        self.leaf_id = leaf_id

    def evaluate(self, satisfied_leaves: Set[str]) -> bool:
        return self.leaf_id in satisfied_leaves


class EvalAnd(EvalNode):
    def __init__(self, children: List[EvalNode]):
        self.children = children

    def evaluate(self, satisfied_leaves: Set[str]) -> bool:
        # Lazy evaluation: short-circuit if any child is false
        return all(c.evaluate(satisfied_leaves) for c in self.children)


class EvalOr(EvalNode):
    def __init__(self, children: List[EvalNode]):
        self.children = children

    def evaluate(self, satisfied_leaves: Set[str]) -> bool:
        # Lazy evaluation: short-circuit if any child is true
        return any(c.evaluate(satisfied_leaves) for c in self.children)


class EvalNot(EvalNode):
    def __init__(self, child: EvalNode):
        self.child = child

    def evaluate(self, satisfied_leaves: Set[str]) -> bool:
        return not self.child.evaluate(satisfied_leaves)


def compile_evaluator(
    condition: Condition,
    rule_id: str,
    leaf_counter: List[int],
    index: RuleIndex,
    referenced_metrics: Set[Tuple[str, Any]]
) -> EvalNode:
    """Recursively convert a Condition tree into an EvalNode tree, registering leaves into the index."""
    if isinstance(condition, Leaf):
        leaf_id = index.get_or_create_leaf(
            condition.metric,
            condition.window_s,
            condition.cmp,
            condition.value
        )
        referenced_metrics.add((condition.metric, condition.window_s))
        return EvalLeaf(leaf_id)

    elif isinstance(condition, Composite):
        compiled_children = [
            compile_evaluator(c, rule_id, leaf_counter, index, referenced_metrics)
            for c in condition.children
        ]
        if condition.op == "and":
            return EvalAnd(compiled_children)
        elif condition.op == "or":
            return EvalOr(compiled_children)
        elif condition.op == "not":
            return EvalNot(compiled_children[0])
        else:
            raise ValueError(f"Unknown boolean operator: {condition.op}")

    else:
        raise TypeError(f"Unknown condition type: {type(condition)}")
