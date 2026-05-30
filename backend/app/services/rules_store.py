"""Rules store — SQLite persistence for admin-managed signal rules.

Pattern mirrors dashboard_store.py: stdlib sqlite3, threading.Lock for
thread safety, JSON for the logic tree. Builtin rules are seeded once on
first run and can be mutated freely after that.
"""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from backend.app.rules.builtins import default_rules
from backend.app.rules.rule import Rule

DB_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
)
DB_PATH = os.path.join(DB_DIR, "rules.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rules (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    side_label  TEXT,                          -- 'bull' | 'bear' | NULL (neutral)
    kind        TEXT NOT NULL DEFAULT 'SIGNAL',
    cooldown_s  REAL NOT NULL DEFAULT 300.0,
    logic_json  TEXT NOT NULL,
    is_builtin  INTEGER NOT NULL DEFAULT 0,   -- 1 = ships with platform
    created_at  REAL NOT NULL DEFAULT (unixepoch('now')),
    updated_at  REAL NOT NULL DEFAULT (unixepoch('now'))
);
"""


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["logic"] = json.loads(d.pop("logic_json"))
    d["enabled"] = bool(d["enabled"])
    d["is_builtin"] = bool(d["is_builtin"])
    return d


class RulesStore:
    """CRUD store for signal rules. All mutations return the updated rule dict."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        os.makedirs(DB_DIR, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Drop the deprecated `severity` column from pre-existing DBs."""
        cols = {r[1] for r in conn.execute("PRAGMA table_info(rules)").fetchall()}
        if "severity" in cols:
            conn.execute("ALTER TABLE rules DROP COLUMN severity")

    @contextmanager
    def _connect(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def all_rules(self) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM rules ORDER BY is_builtin DESC, created_at ASC"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_rule(self, rule_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM rules WHERE id = ?", (rule_id,)
            ).fetchone()
        return _row_to_dict(row) if row else None

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0]

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def insert_rule(self, rule: Rule, is_builtin: bool = False) -> dict:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO rules
                   (id, name, enabled, side_label, kind, cooldown_s,
                    logic_json, is_builtin)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rule.id,
                    rule.name,
                    int(rule.enabled),
                    rule.side_label,
                    rule.kind,
                    rule.cooldown_s,
                    json.dumps(rule.logic),
                    int(is_builtin),
                ),
            )
        return self.get_rule(rule.id)

    def update_rule(self, rule_id: str, updates: Dict[str, Any]) -> Optional[dict]:
        """Apply a partial update. Only whitelisted fields are accepted."""
        allowed = {"name", "enabled", "side_label", "kind", "cooldown_s", "logic"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return self.get_rule(rule_id)

        # Coerce types before writing
        if "enabled" in fields:
            fields["enabled"] = int(bool(fields["enabled"]))
        if "logic" in fields:
            fields["logic_json"] = json.dumps(fields.pop("logic"))

        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [rule_id]

        with self._connect() as conn:
            rowcount = conn.execute(
                f"UPDATE rules SET {set_clause}, updated_at = unixepoch('now') WHERE id = ?",
                values,
            ).rowcount
        return self.get_rule(rule_id) if rowcount else None

    def delete_rule(self, rule_id: str) -> bool:
        with self._connect() as conn:
            rowcount = conn.execute(
                "DELETE FROM rules WHERE id = ?", (rule_id,)
            ).rowcount
        return rowcount > 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def seed_builtins(self) -> int:
        """Insert builtin rules if the table is empty. Returns number inserted."""
        if self.count() > 0:
            return 0
        for rule in default_rules():
            self.insert_rule(rule, is_builtin=True)
        n = len(default_rules())
        print(f"[RulesStore] seeded {n} builtin rules", flush=True)
        return n

    def as_rules(self) -> List[Rule]:
        """Load all rules from DB as Rule objects (recompiles condition trees)."""
        return [Rule.from_dict(d) for d in self.all_rules()]
