"""Index structure for fast leaf condition matching.

Organizes leaf conditions by metric and comparator to avoid linear scans.
Numeric comparisons (>, >=, <, <=) use sorted lists with binary search (bisect).
Equality and inequality (==, !=) use Hash Maps.
"""

import bisect
from typing import Any, Dict, List, Set, Tuple


class RuleIndex:
    def __init__(self):
        # Maps (metric, window_s) -> index structure
        # Index structure is a dict:
        # {
        #   "ge": [(threshold, cond_id)],  # sorted ascending, used for >= and >
        #   "le": [(threshold, cond_id)],  # sorted ascending, used for <= and <
        #   "eq": {value: [cond_id]},
        #   "ne": {value: [cond_id]},
        #   "all_ne": set(cond_id)
        # }
        self._indices: Dict[Tuple[str, Any], dict] = {}
        # Maps (metric, window_s, cmp, rounded_value) -> leaf_id
        self._leaf_keys: Dict[Tuple[str, Any, str, Any], str] = {}
        self._leaf_counter = 0
        self._is_dirty = False

    def clear(self) -> None:
        self._indices.clear()
        self._leaf_keys.clear()
        self._leaf_counter = 0
        self._is_dirty = False

    def get_or_create_leaf(self, metric: str, window_s: Any, cmp: str, value: Any) -> str:
        """Get an existing leaf ID or create and register a new one, rounding floats to 2 decimals."""
        if isinstance(value, (int, float)):
            rounded_value = round(float(value), 2)
        else:
            rounded_value = value

        key = (metric, window_s, cmp, rounded_value)
        if key in self._leaf_keys:
            return self._leaf_keys[key]

        leaf_id = f"l_{self._leaf_counter}"
        self._leaf_counter += 1
        self._leaf_keys[key] = leaf_id
        self.add_leaf(metric, window_s, cmp, rounded_value, leaf_id)
        return leaf_id

    def _get_or_create_index(self, metric: str, window_s: Any) -> dict:
        key = (metric, window_s)
        if key not in self._indices:
            self._indices[key] = {
                "ge": [],      # For >= and >: contains (threshold, cond_id, is_strict)
                "le": [],      # For <= and <: contains (threshold, cond_id, is_strict)
                "eq": {},      # value -> list of cond_id
                "ne": {},      # value -> list of cond_id
                "all_ne": set()  # set of all cond_ids with != operator for this metric
            }
        return self._indices[key]

    def add_leaf(self, metric: str, window_s: Any, cmp: str, value: Any, cond_id: str) -> None:
        idx = self._get_or_create_index(metric, window_s)
        self._is_dirty = True

        if cmp in (">=", ">"):
            is_strict = (cmp == ">")
            idx["ge"].append((float(value), cond_id, is_strict))
        elif cmp in ("<=", "<"):
            is_strict = (cmp == "<")
            idx["le"].append((float(value), cond_id, is_strict))
        elif cmp == "==":
            if value not in idx["eq"]:
                idx["eq"][value] = []
            idx["eq"][value].append(cond_id)
        elif cmp == "!=":
            if value not in idx["ne"]:
                idx["ne"][value] = []
            idx["ne"][value].append(cond_id)
            idx["all_ne"].add(cond_id)

    def rebuild(self) -> None:
        """Sort the threshold lists so they are ready for binary search."""
        if not self._is_dirty:
            return
        for idx in self._indices.values():
            # Sort ge list by threshold ascending
            idx["ge"].sort(key=lambda item: item[0])
            # Sort le list by threshold ascending
            idx["le"].sort(key=lambda item: item[0])
        self._is_dirty = False

    def match(self, metric: str, window_s: Any, actual_value: Any) -> Set[str]:
        """Return the set of condition IDs that are satisfied by actual_value."""
        if self._is_dirty:
            self.rebuild()

        key = (metric, window_s)
        idx = self._indices.get(key)
        if idx is None or actual_value is None:
            return set()

        satisfied: Set[str] = set()

        # 1. Equality matching (==)
        eq_map = idx["eq"]
        if actual_value in eq_map:
            satisfied.update(eq_map[actual_value])

        # 2. Inequality matching (!=)
        # All != conditions are satisfied except the ones that are equal to actual_value
        ne_map = idx["ne"]
        all_ne = idx["all_ne"]
        if ne_map:
            satisfied.update(all_ne)
            if actual_value in ne_map:
                satisfied.difference_update(ne_map[actual_value])

        # 3. Numeric comparisons (>, >=, <, <=)
        # If actual_value is a string, it cannot be compared numerically
        if isinstance(actual_value, (int, float)):
            actual_float = float(actual_value)

            # --- >= and > checks ---
            # We want all thresholds <= actual_float (for >=) and < actual_float (for >)
            ge_list = idx["ge"]
            if ge_list:
                # Binary search for the insertion point of actual_float
                # ge_list is sorted by threshold (item[0])
                keys = [item[0] for item in ge_list]
                
                # bisect_right gives index of first threshold > actual_float
                # All thresholds up to this index are <= actual_float
                pos = bisect.bisect_right(keys, actual_float)
                for i in range(pos):
                    thresh, cond_id, is_strict = ge_list[i]
                    if is_strict:
                        if actual_float > thresh:
                            satisfied.add(cond_id)
                    else:
                        if actual_float >= thresh:
                            satisfied.add(cond_id)

            # --- <= and < checks ---
            # We want all thresholds >= actual_float (for <=) and > actual_float (for <)
            le_list = idx["le"]
            if le_list:
                keys = [item[0] for item in le_list]
                
                # bisect_left gives index of first threshold >= actual_float
                pos = bisect.bisect_left(keys, actual_float)
                # All thresholds from this index to the end are >= actual_float
                for i in range(pos, len(le_list)):
                    thresh, cond_id, is_strict = le_list[i]
                    if is_strict:
                        if actual_float < thresh:
                            satisfied.add(cond_id)
                    else:
                        if actual_float <= thresh:
                            satisfied.add(cond_id)

        return satisfied
