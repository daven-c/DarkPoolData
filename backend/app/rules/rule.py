"""Rule + Signal — a named condition tree that fires a Signal when it matches."""

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from backend.app.rules.conditions import Condition, compile_condition
from backend.app.rules.events import MarketEvent, TickerState


@dataclass
class Signal:
    rule_id: str
    rule_name: str
    symbol: str
    ts: float
    kind: str           # e.g. "WHALE", "SWEEP", "BREAKOUT", "SIGNAL"
    severity: str       # "info" | "warning" | "critical"
    side_label: Optional[str]  # "bull" | "bear" | None
    price: float
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Rule:
    name: str
    logic: dict                       # JSON condition tree
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    enabled: bool = True
    severity: str = "info"
    side_label: Optional[str] = None  # "bull" | "bear"
    kind: str = "SIGNAL"
    cooldown_s: float = 300.0

    def __post_init__(self):
        self._compiled: Condition = compile_condition(self.logic)

    def matches(self, event: MarketEvent, state: TickerState) -> bool:
        return self.enabled and self._compiled.evaluate(event, state)

    def make_signal(self, event: MarketEvent, state: TickerState) -> Signal:
        notional = event.notional
        msg = (
            f"{self.name} — {event.symbol} {event.side or ''} "
            f"${notional:,.0f} @ ${event.price:,.2f}"
        )
        return Signal(
            rule_id=self.id,
            rule_name=self.name,
            symbol=event.symbol,
            ts=event.ts,
            kind=self.kind,
            severity=self.severity,
            side_label=self.side_label,
            price=event.price,
            message=msg,
            metadata={
                "trade_notional": notional,
                "trade_size": event.size,
                "side": event.side,
                "session_total": state.total_amount,
                "net_flow": state.net_flow,
                "dp_trades": state.dp_trades,
                "block_trades": state.block_trades,
            },
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "severity": self.severity,
            "side_label": self.side_label,
            "kind": self.kind,
            "cooldown_s": self.cooldown_s,
            "logic": self.logic,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Rule":
        return cls(
            name=d["name"],
            logic=d["logic"],
            id=d.get("id", uuid.uuid4().hex[:12]),
            enabled=d.get("enabled", True),
            severity=d.get("severity", "info"),
            side_label=d.get("side_label"),
            kind=d.get("kind", "SIGNAL"),
            cooldown_s=d.get("cooldown_s", 300.0),
        )
